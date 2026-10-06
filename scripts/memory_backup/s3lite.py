#!/usr/bin/env python3
"""s3lite.py — minimal S3 client, Python STDLIB ONLY (no boto3, no aws CLI).

Built because the openclaw pod image has python3 but no AWS tooling.
Supports exactly what the memory backup needs: PUT / GET / LIST on one
bucket, with SigV4 signing and credentials resolved from (in order):

  1. env:            AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY [/ AWS_SESSION_TOKEN]
  2. ~/.aws/credentials  ([default] profile)
  3. IRSA web identity:  AWS_ROLE_ARN + AWS_WEB_IDENTITY_TOKEN_FILE -> STS
  4. EC2/node IMDSv2:    instance-profile credentials (last resort — node role)

Usage as CLI (for quick tests):
  python3 s3lite.py whoami
  python3 s3lite.py ls   <bucket> <prefix>
  python3 s3lite.py put  <bucket> <key> <local_file>
  python3 s3lite.py get  <bucket> <key> <local_file>
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REGION = os.environ.get("AWS_REGION", "us-east-1")


class Creds:
    def __init__(self, key, secret, token=None, source="env"):
        self.key, self.secret, self.token, self.source = key, secret, token, source


def _http(url, method="GET", data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout)


def resolve_creds():
    """Try each credential source; return Creds or raise RuntimeError."""
    # 1. plain env keys
    k, s = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if k and s:
        return Creds(k, s, os.environ.get("AWS_SESSION_TOKEN"), "env")

    # 2. ~/.aws/credentials [default]
    path = os.path.expanduser("~/.aws/credentials")
    if os.path.exists(path):
        vals, in_default = {}, False
        for line in open(path):
            line = line.strip()
            if line.startswith("["):
                in_default = line == "[default]"
            elif in_default and "=" in line:
                a, b = line.split("=", 1)
                vals[a.strip()] = b.strip()
        if vals.get("aws_access_key_id"):
            return Creds(vals["aws_access_key_id"], vals["aws_secret_access_key"],
                         vals.get("aws_session_token"), "~/.aws/credentials")

    # 3. IRSA (AssumeRoleWithWebIdentity — unsigned STS call)
    role, tok_file = os.environ.get("AWS_ROLE_ARN"), os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")
    if role and tok_file and os.path.exists(tok_file):
        token = open(tok_file).read().strip()
        q = urllib.parse.urlencode({
            "Action": "AssumeRoleWithWebIdentity", "Version": "2011-06-15",
            "RoleArn": role, "RoleSessionName": "memory-backup",
            "WebIdentityToken": token, "DurationSeconds": "3600"})
        with _http(f"https://sts.{REGION}.amazonaws.com/?{q}",
                   headers={"Accept": "application/json"}) as r:
            body = json.loads(r.read())
        c = body["AssumeRoleWithWebIdentityResponse"]["AssumeRoleWithWebIdentityResult"]["Credentials"]
        return Creds(c["AccessKeyId"], c["SecretAccessKey"], c["SessionToken"], "irsa")

    # 4. IMDSv2 (node instance profile)
    try:
        imds = "http://169.254.169.254"
        with _http(f"{imds}/latest/api/token", method="PUT",
                   headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"}, timeout=3) as r:
            t = r.read().decode()
        h = {"X-aws-ec2-metadata-token": t}
        with _http(f"{imds}/latest/meta-data/iam/security-credentials/", headers=h, timeout=3) as r:
            role_name = r.read().decode().strip().splitlines()[0]
        with _http(f"{imds}/latest/meta-data/iam/security-credentials/{role_name}",
                   headers=h, timeout=3) as r:
            c = json.loads(r.read())
        return Creds(c["AccessKeyId"], c["SecretAccessKey"], c["Token"], f"imds:{role_name}")
    except Exception:
        pass

    raise RuntimeError(
        "NO_AWS_CREDENTIALS: none of env keys / ~/.aws/credentials / IRSA / IMDS "
        "yielded credentials. Ask infra (Andy) for either an IRSA annotation to "
        "EnterpriseAgentDevRole, or an access key scoped to the Appendix-A policy "
        "injected as WegoClaw env vars (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY).")


def _sign(creds, method, host, path, query="", payload=b"", extra_headers=None,
          service="s3"):
    """SigV4-sign and execute one AWS request (S3 by default; `service` is
    parameterised so the same signer can serve other AWS APIs if ever needed).
    Returns (status, body_bytes)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    scope_date = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload).hexdigest()

    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    if creds.token:
        headers["x-amz-security-token"] = creds.token
    for k, v in (extra_headers or {}).items():
        headers[k.lower()] = v

    signed_names = ";".join(sorted(headers))
    canonical = "\n".join([
        method, urllib.parse.quote(path, safe="/-_.~"), query,
        "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
        signed_names, payload_hash])
    scope = f"{scope_date}/{REGION}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])

    def hm(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k = hm(hm(hm(hm(("AWS4" + creds.secret).encode(), scope_date), REGION), service),
           "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={creds.key}/{scope}, "
        f"SignedHeaders={signed_names}, Signature={sig}")

    url = f"https://{host}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, data=payload if method in ("PUT", "POST") else None,
                                 method=method,
                                 headers={k: v for k, v in headers.items() if k != "host"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _host(bucket):
    return f"{bucket}.s3.{REGION}.amazonaws.com"


def put_object(creds, bucket, key, body_bytes):
    status, body = _sign(creds, "PUT", _host(bucket), f"/{key}", payload=body_bytes)
    if status not in (200, 201):
        raise RuntimeError(f"S3 PUT failed HTTP {status}: {body[:300].decode(errors='replace')}")
    return True


def get_object(creds, bucket, key):
    status, body = _sign(creds, "GET", _host(bucket), f"/{key}")
    if status != 200:
        raise RuntimeError(f"S3 GET failed HTTP {status}: {body[:300].decode(errors='replace')}")
    return body


def list_objects(creds, bucket, prefix):
    q = urllib.parse.urlencode({"list-type": "2", "prefix": prefix})
    # canonical query must be sorted — urlencode of this dict already is.
    status, body = _sign(creds, "GET", _host(bucket), "/", query=q)
    if status != 200:
        raise RuntimeError(f"S3 LIST failed HTTP {status}: {body[:300].decode(errors='replace')}")
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    root = ET.fromstring(body)
    out = []
    for c in root.findall("s3:Contents", ns):
        out.append({"key": c.find("s3:Key", ns).text,
                    "size": int(c.find("s3:Size", ns).text),
                    "modified": c.find("s3:LastModified", ns).text})
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami"
    creds = resolve_creds()
    if cmd == "whoami":
        print(f"credentials OK (source: {creds.source})")
    elif cmd == "ls":
        for o in list_objects(creds, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""):
            print(f"{o['modified']}  {o['size']:>12}  {o['key']}")
    elif cmd == "put":
        put_object(creds, sys.argv[2], sys.argv[3], open(sys.argv[4], "rb").read())
        print(f"OK put s3://{sys.argv[2]}/{sys.argv[3]}")
    elif cmd == "get":
        open(sys.argv[5 - 1], "wb").write(get_object(creds, sys.argv[2], sys.argv[3]))
        print(f"OK get -> {sys.argv[4]}")
    else:
        sys.exit(f"unknown cmd {cmd}")
