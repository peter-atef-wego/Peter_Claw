"""
slack_listener.py — AlphaBot Slack Listener
Polls every configured channel in CHANNELS for trigger messages:
  - #proj-alphabot-testing  (C090HF85F2P)  — internal team testing
  - #finance-automation-claw (C0AVB4VR708) — finance team production
Lives at: /config/rpa/openclaw/Finance/Supplier/LCC/slack_listener.py

How it works:
1. Polls Slack channel every POLL_INTERVAL seconds.
2. Only processes messages newer than startup time, from real users (not bots).
3. Two ways to trigger a reco:
     a) Post raw JSON: {"action": "<supplier>", "start_date": "...", "end_date": "..."}
     b) Post natural language + xlsx attachment ("run jazeera reco from 18 to 19 april") —
        listener uses a regex pre-parser; OpenAI gpt-4o-mini is the fallback.
4. Downloads xlsx file from Slack.
5. Calls nova_api /trigger/<supplier> with file + dates.
6. Polls job status until done.
7. Uploads Final_Summary back to the user's thread.
8. Posts completion message.

================================================================================
CHANGES vs current AlphaBot main (test_py copy — for review/deployment):

  Polling alignment (earlier):
    • POLL_INTERVAL 30 → 10 (channel check cadence).
    • poll_job() max_polls 60 → 90 (15-min cap, aligned with nova_api).

  NL → JSON parsing (OpenAI gpt-4o-mini, with a regex pre-parser in front):
    • Regex pre-parser tries first (free, instant, deterministic) — handles
      the common phrasings (jazeera + ISO/DD-MM-YYYY/"18 april 2026" / "18 to
      19 april" / etc.). 9/9 tested.
    • LLM falls back only when regex can't pin both supplier and dates
      (e.g. "last month", relative dates, unusual phrasing).
    • OpenAI Chat Completions API is hit directly via `requests` (no new
      pip dep). Uses response_format={"type": "json_object"} so the model
      MUST return valid JSON — eliminates a class of parse errors.
    • Few-shot prompt baked in — see test_py/prompt_eng.md for the full
      scenario reference and how to extend coverage.

  Trigger filters (NEW — required to act):
    1. Message must @-mention this bot. Bot user_id is discovered at startup
       via auth.test (or set BOT_USER_ID env var to pin it).
    2. Message must include at least one .xlsx, .xls, or .csv attachment.
       The first supported file wins; original extension is preserved when
       saved to /config/Downloads/ and a matching MIME type is sent to
       nova_api.
    3. <@Uxxx> mention tokens are stripped from text before the LLM call so
       they don't pollute parsing.

  Auto-cleanup of agent hallucinations (NEW):
    Listener polls the bridge channel (root messages + active threads) on
    every cycle. Any bot-authored message containing one of the verbatim
    hallucinated phrases ("AlphaBot offline", "Port 3002 unreachable",
    "Testing connectivity", "Attempting trigger", "Service still down",
    "Infrastructure issue", "Let me retry", "Health check", etc.) is
    deleted via chat.delete. The listener never produces these phrases
    itself, so the content filter is sound — anything matching is by
    construction the agent posting noise. Within ~10s of the agent
    posting nonsense, it's gone.

  Failure UX:
    • @mention + no file        → "Please attach an xlsx or csv ..."
    • @mention + file + no text → "Got the file. Which supplier and dates?"
    • LLM error / bad parse     → in-thread error + JSON-template copy hint
    No silent drops; every actionable message gets a reply in the user's thread.

  Credentials come from the environment, never from source: SLACK_TOKEN reads
  SLACK_BOT_TOKEN_NETSUITE_CHAMPION / SLACK_BOT_TOKEN and exits if unset;
  OPENAI_API_KEY is fetched from AWS Secrets Manager at startup (see
  initialize_openai_client) or read from the env for local dev. BOT_USER_ID is
  hardcoded to U0AHNGSDQ3W with auth.test as a fallback.
================================================================================
"""

import os
import re
import json
import time
import base64
import logging
import requests
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import boto3
from botocore.exceptions import ClientError

# ── Config ─────────────────────────────────────────────────
# Never hardcode the token — it lands in git history. Source of truth is
# /home/openclaw/.openclaw/cron/openclaw.env; export it before running:
#   export SLACK_BOT_TOKEN_NETSUITE_CHAMPION=xoxb-...
SLACK_TOKEN = (
    os.environ.get("SLACK_BOT_TOKEN_NETSUITE_CHAMPION")
    or os.environ.get("SLACK_BOT_TOKEN")
    or ""
)
if not SLACK_TOKEN:
    raise SystemExit(
        "SLACK_BOT_TOKEN_NETSUITE_CHAMPION (or SLACK_BOT_TOKEN) is not set — "
        "export it from /home/openclaw/.openclaw/cron/openclaw.env before running."
    )

# Channels the listener watches. Each one is processed independently
# every poll cycle. Adding a channel = invite the bot to it on Slack +
# add the ID here.
CHANNELS = {
    "C090HF85F2P": "proj-alphabot-testing",      # internal team testing (Peter + automation team)
    "C0AVB4VR708": "finance-automation-claw",    # finance team production (daily use)
}
CHANNEL_IDS = list(CHANNELS.keys())

API_BASE          = "http://localhost:3002"               # nova_api running locally
POLL_INTERVAL     = 10                                    # channel poll cadence (s)
LOGS_DIR          = "/config/rpa/openclaw/logs"
SUPPLIERS_CFG     = "/config/rpa/openclaw/Finance/Supplier/LCC/suppliers.json"

# Job-status poll: 10s sleep × 90 polls = 15 min cap.
JOB_POLL_SLEEP    = 10
JOB_POLL_MAX      = 90

# OpenAI — natural-language → JSON parsing (LLM fallback when regex can't pin)
# Key is loaded at startup from AWS Secrets Manager (see initialize_openai_client
# below). For local dev / smoke tests you can also export OPENAI_API_KEY in the
# shell — that takes precedence and skips the AWS call.
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL      = "gpt-4o-mini"                        # cheap + fast; ~$0.00015 / parse
OPENAI_URL        = "https://api.openai.com/v1/chat/completions"
OPENAI_TIMEOUT    = 15
NL_PARSE_ENABLED  = bool(OPENAI_API_KEY) and OPENAI_API_KEY.startswith("sk-") and len(OPENAI_API_KEY) > 20

# AWS Secrets Manager — where the OpenAI key lives in production.
# Secret JSON is expected to contain a base64-encoded value under
# AWS_SECRET_KEY_OPENAI. The ECS task role (wego-ecs-task-common) needs
# secretsmanager:GetSecretValue on this secret's ARN.
AWS_SECRET_NAME       = "alphabot-production"
AWS_SECRET_REGION     = "us-east-1"
AWS_SECRET_KEY_OPENAI = "data_team_alphabot"

# ── Logger ─────────────────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
log_path = f"{LOGS_DIR}/slack_listener.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("slack_listener")

# ── AWS Secrets Manager bootstrap ──────────────────────────
# Fetch the OpenAI key from Secrets Manager at startup. Pattern matches
# the existing alphabot helpers: secret JSON has a base64-encoded value
# at the configured key, decoded once and cached in OPENAI_API_KEY +
# os.environ['OPENAI_API_KEY']. If OPENAI_API_KEY is already set in the
# environment (e.g. local dev), AWS is skipped.

def get_secret_values(secret_name, region_name):
    """Pull a secret JSON object from AWS Secrets Manager. Returns dict or None."""
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        logger.error(f"Could not retrieve secret '{secret_name}': {e}")
        return None
    if "SecretString" in get_secret_value_response:
        return json.loads(get_secret_value_response["SecretString"])
    binary_secret_data = get_secret_value_response["SecretBinary"]
    return json.loads(binary_secret_data.decode("utf-8"))


def decode_key(encoded_key):
    """Base64-decode a secret value back to a plain string."""
    return base64.b64decode(encoded_key.encode("utf-8")).decode("utf-8")


def initialize_openai_client():
    """Populate OPENAI_API_KEY (module global + env var) from AWS Secrets
    Manager. Returns True on success, False otherwise. NL_PARSE_ENABLED
    is recomputed so downstream code reflects the current key state."""
    global OPENAI_API_KEY, NL_PARSE_ENABLED

    # If a key is already set (env var, e.g. local dev), keep it.
    if OPENAI_API_KEY:
        NL_PARSE_ENABLED = OPENAI_API_KEY.startswith("sk-") and len(OPENAI_API_KEY) > 20
        logger.info("OpenAI key      : using OPENAI_API_KEY from environment (skip AWS)")
        return bool(NL_PARSE_ENABLED)

    secrets = get_secret_values(AWS_SECRET_NAME, AWS_SECRET_REGION)
    if not secrets:
        logger.error(f"OpenAI key      : failed to load from AWS secret '{AWS_SECRET_NAME}'")
        NL_PARSE_ENABLED = False
        return False

    encoded = (secrets.get(AWS_SECRET_KEY_OPENAI) or "").strip('"')
    if not encoded:
        logger.error(
            f"OpenAI key      : key '{AWS_SECRET_KEY_OPENAI}' missing in secret "
            f"'{AWS_SECRET_NAME}'"
        )
        NL_PARSE_ENABLED = False
        return False

    try:
        OPENAI_API_KEY = decode_key(encoded)
    except Exception as e:
        logger.error(f"OpenAI key      : failed to base64-decode: {e}")
        NL_PARSE_ENABLED = False
        return False

    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
    NL_PARSE_ENABLED = OPENAI_API_KEY.startswith("sk-") and len(OPENAI_API_KEY) > 20
    logger.info(
        f"OpenAI key      : loaded from AWS secret '{AWS_SECRET_NAME}.{AWS_SECRET_KEY_OPENAI}'"
    )
    return bool(NL_PARSE_ENABLED)


# ── State ──────────────────────────────────────────────────
processed_ts = set()
STARTUP_TS   = str(time.time())

ISO_DATE_RE  = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MENTION_RE   = re.compile(r"<@U[A-Z0-9]+>")

MONTH_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
MONTH_NAMES = "|".join(sorted(MONTH_NUM.keys(), key=len, reverse=True))

# Hardcoded bot user_id for "Data Automation's Claw" (= "@Data Automation's Claw"
# in Slack). The listener triggers ONLY when this exact user is @-mentioned.
# Mentions of any other user / bot are ignored. Override with env var if needed.
BOT_USER_ID  = os.environ.get("BOT_USER_ID", "U0AHNGSDQ3W")

# Files we accept on a trigger message. .xlsb (Excel Binary, often macro-
# enabled) is accepted because some supplier robots (e.g. Dnata BH) have
# a "Convert XLSB files to XLSX" step that reads the file from the
# supplier's raw/ folder. The download_path_template in suppliers.json
# routes the upload directly to that folder so the converter picks it up.
SUPPORTED_EXTS = (".xlsx", ".xls", ".xlsb", ".csv")
MIME_BY_EXT = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".xlsb": "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    ".csv":  "text/csv",
}

# ── Auto-cleanup of agent hallucinations ───────────────────
# The OpenClaw agent shares this bot's Slack identity, so any post containing
# any of these substrings (case-insensitive) is by definition the agent
# hallucinating — the listener itself never produces these phrases. Any
# matching message authored by this bot gets auto-deleted within one poll
# cycle.
HALLUCINATED_SUBSTRINGS = (
    # ── AlphaBot offline / down / unavailable, all word orderings ──
    "alphabot offline",
    "alphabot is offline",
    "alphabot still offline",
    "alphabot service offline",
    "alphabot down",
    "alphabot is down",
    "alphabot's down",
    "alphabot unavailable",
    "alphabot is unavailable",
    "alphabot unreachable",
    "alphabot is unreachable",
    "alphabot back online",
    "bring alphabot",
    "couldn't reach alphabot",
    "cannot reach alphabot",
    "alphabot api unreachable",
    "alphabot service",         # "AlphaBot service still..." / "AlphaBot service offline"

    # ── Raw + rendered emoji forms preceding the AlphaBot status ──
    ":x: alphabot",
    "❌ alphabot",
    ":warning: alphabot",
    "⚠️ alphabot",
    ":rotating_light:",
    ":no_entry_sign:",

    # ── Port 3002 — every variant we've seen or might see ──
    "port 3002 unreachable",
    "port 3002 unresponsive",
    "port 3002 not responding",
    "port 3002 timed out",
    "port 3002 down",
    "3002 unreachable",
    "3002 unresponsive",

    # ── Connectivity / trigger narration ──
    "testing connectivity",
    "connectivity test",
    "attempting trigger",
    "re-attempting trigger",
    "connection timed out",
    "connection timeout",
    "timeout again",

    # ── Service status hallucinations ──
    "service still down",
    "service unreachable",
    "service has been down",
    "service needs to be",
    "service is down",
    "service offline",
    "down for ~",               # "down for ~6 hours"

    # ── Infrastructure / retry narration ──
    "infrastructure issue",
    "infrastructure intervention",
    "infrastructure problem",
    "infrastructure support",
    "requires infrastructure",
    "need infrastructure",
    "needs to be restarted",
    "needs to be restarted or debugged",
    "let me retry",
    "let me try",
    "health check",
    "health check timed out",

    # ── Fabricated timestamps / attempt counters ──
    "after ~",                  # "(after ~2.5 hour gap)"
    "hour gap",                 # "(after ~2.5 hour gap)"
    "hours later",              # "(2+ hours later)"
    "th attempt",               # "6th attempt", "10th attempt"
    "rd attempt",               # "3rd attempt"
    "nd attempt",               # "2nd attempt"
    "st attempt",               # "1st attempt"

    # ── Agent narration / status reports / meta-commentary ──
    # The agent (OpenClaw) shares this bot's Slack identity and posts verbose
    # narrative messages about its own thinking ("Let me check...",
    # "I see Nik has...", "Now posting the JSON...", "Trigger queued
    # (message ID: ...)"). The listener never produces any of these phrases,
    # so each is safe to delete on sight.
    "trigger posted",           # "✅ AJet trigger posted (message ID: ...)"
    "trigger queued",           # "✅ Air Arabia trigger queued"
    "trigger for",              # "AJet trigger for 2026-04-08 to 08 was already submitted"
    "request confirmed",        # "Nik's request confirmed (11:48:33 UTC)"
    "new request from",         # "**New request from Likith (11:50:00 UTC):**"
    "request from likith",
    "request from nik",
    "request from finance",
    "action taken:",            # "**Action taken:** Verify..."
    "let me check",             # "Let me check the suppliers configuration"
    "let me process",           # "Let me process this one as well"
    "let me verify",
    "let me attempt",
    "let me see",
    "i see nik",                # "I see Nik has mentioned me"
    "i see this is",            # "I see this is a duplicate/clarification"
    "i see the recent",         # "I see the recent message history"
    "i see the message",
    "i see the new",
    "i see likith",
    "no additional action",     # "No additional action needed at this time"
    "duplicate/clarification",
    "duplicate / clarification",
    "now posting",              # "Now posting the JSON trigger"
    "posting the json",         # "Posting the JSON trigger to bridge..."
    "posting json trigger",
    "posting trigger",          # "Posting AJet trigger:"
    "posting ajet trigger",
    "posting jazeera trigger",
    "actively monitored",       # "Both requests are now queued and actively monitored"
    "queued and actively",
    "job is active",            # "The job is active and waiting for AlphaBot"
    "ready and waiting",
    "verified (row",            # "✅ Air Arabia verified (row 6, action key: ...)"
    "action key:",              # "(row 6, action key: air_arabia)"
    "message id:",              # "(message ID: 1777376910.954649)"
    "reconciliation status:",   # "AJet reconciliation status:"
    "already submitted",        # "AJet trigger for 2026-04-08 was already submitted at..."
    "already posted",           # "Trigger already posted for..."
    "already queued",
    "both requests are",        # "Both requests are now queued and actively monitored"
    "both jobs are",
    "queued for processing",
    "recent context",           # "Let me check the recent context"
    "recent message history",   # "I see the recent message history"
    "mentioned me",             # "I see Nik has mentioned me"
    "noted, processing",
    "noted — processing",
    "configuration:",           # "Let me check the suppliers configuration:"
    "suppliers configuration",
    "suppliers.md",             # agent narrates checking suppliers.md
    "channel: #proj-alphabot",  # agent restates channel as a status detail

    # ── Conversation-mode agent (treats reco trigger as chat) ──
    "i see you",                # "I see you've uploaded" / "I see you're asking"
    "i see you're",
    "i see you've",
    "i see you have",
    "how can i help",
    "how can i assist",
    "what would you like",
    "what do you want to do",
    "here are some options",
    "here are a few options",
    "extract & analyze",
    "extract and analyze",
    "convert to csv",
    "convert to json",
    "reconciliation work",      # agent's section header in conversation mode
    "validate entries",
    "compare against",
    "flag discrepancies",
    "i can help structure",
    "would you like to do",

    # ── Step-by-step narration of own actions ──
    "let me trigger",
    "let me ping",
    "let me notify",
    "let me use",
    "let me start",
    "let me confirm",
    "let me look",
    "let me handle",
    "let me query",
    "let me search",
    "i'll trigger",
    "i'll check the thread",
    "i'll post",
    "i'll need",
    "i need to verify",
    "now i'll",
    "json posted",
    "json post",
    "background polling",
    "polling loop",
    "polling for the alphabot",
    "polling for the response",
    "every 15 seconds",
    "check the thread every",
    "is configured (action key",

    # ── Status / monitoring summaries ──
    "queued and polling",
    "queued and waiting",
    "active reconciliations summary",
    "active reconciliations",
    "monitoring all jobs",
    "monitoring jobs",
    "all jobs for ✅",
    "all jobs for ✅/❌",

    # ── Bot-authored raw JSON post ──
    # The listener never posts pure JSON. It only quotes JSON inside its
    # error templates ("Use this format: `{...}`"), which are already
    # whitelisted via LISTENER_PROTECTED_SUBSTRINGS ("use this format",
    # "couldn't parse json", etc.). So any bot post containing this
    # substring without one of the listener-protected phrases is by
    # construction the agent posting a trigger as itself.
    '{"action":',

    # ── Agent's "Got it. Triggering / Running / Processing" prefix ──
    # Listener never uses "Got it." in this context; its templates start with
    # ⚙️/🤖/✅/❌ + supplier name. The "Got the file" template is in the
    # listener whitelist and would short-circuit cleanup if a real listener
    # ack ever overlapped — so these phrases only ever match agent posts.
    "got it. triggering",
    "got it. running",
    "got it. processing",
    "got it. let me",
    "triggering ",              # "Triggering Jazeera reconciliation" — listener uses "triggered!"
    "polling for results",      # listener uses "polling for completion"
    "polling for",              # broad catch — listener's "Polling for completion..." is always
                                # in the same message as "🤖 Robot started!", which is in
                                # LISTENER_PROTECTED_SUBSTRINGS, so the listener template still
                                # short-circuits cleanup on the protected check.
    "polling the bridge",
    "i'm reading",
    "i'm polling",
    "i'm checking",
    "reading the reconciliation",
    "reading the request",
    "let me parse",
    "trigger the supplier reconciliation",
    "trigger the supplier",
    "should have results",
    "have results in a few",
    "results in a few minutes",
    "in a few minutes",         # listener never promises a time-window

    # ── Duplicate-detection narrative ──
    "this is a duplicate",
    "duplicate request from",
    "duplicate request",
    "duplicate / clarification",
    "exact same reconciliation",
    "the exact same",
    "already triggered at",
    "already running",
    "already submitted",
    "already in flight",
    "request from nik",         # "request from Nik (12:39:32 UTC)"
    "(message-id:",
    "(message id:",
    "message-id:",
    "message id:",

    # ── Agent commentary about prior / current files ──
    "this appears to be",       # "This appears to be FitsAir_SReco_RAW_..."
    "this looks like a",
    "this looks like it",
    "this seems to be",
    "this is a different",      # "This is a different date range from the earlier..."
    "this is the same",         # "This is the same date range as the earlier request"
    "earlier request",          # "earlier AJet request"
    "earlier ajet request",
    "previous request",
    "previous ajet request",
    "supplier reconciliation file for",  # agent describing the upload
    "supplier reconciliation file from",
    "binary content",           # "I see you've uploaded a file with binary content"
    "untrusted external content",
    "for binary files",
)

CLEANUP_LOOKBACK_LIMIT  = 10     # messages to scan per channel poll (was 20)
CLEANUP_THREAD_LIMIT    = 10     # replies to scan per active thread (was 20)
CLEANUP_INTERVAL_SECS   = 15     # don't re-run cleanup for the same channel more often than this
RATELIMIT_BACKOFF_SECS  = 30     # default sleep on "ratelimited" if Retry-After is absent

# Per-channel timestamp of the last cleanup pass — used to throttle
# conversations.history + conversations.replies calls so we stay under
# Slack's Tier-3 rate limits, AND to skip re-walking threads that
# haven't seen new activity since the previous pass.
_last_cleanup_per_channel = {}

# Threads marked "complete" by the listener — once the listener posts its
# terminal message in a thread, any further bot reply is by definition the
# agent posting noise. Cleanup deletes them after a 2s grace period.
# Maps user_thread_ts → completion timestamp (time.time()).
completed_threads = {}
COMPLETED_GRACE_SECONDS  = 2
COMPLETED_RETENTION_SECS = 3600   # drop entries older than 1 hour

# Listener's own message templates. Any bot post whose text contains one of
# these substrings (case-insensitive) is protected from deletion — even if
# it arrives in a completed thread, even if Slack delivers it slower than
# the grace period (the file-share message from files_upload_v2 can lag
# the API return by 3–5s, which would otherwise trip post-completion
# cleanup against our own success message). The hallucination filter only
# matches phrases the listener never produces, so no overlap.
LISTENER_PROTECTED_SUBSTRINGS = (
    "reconciliation complete",   # ✅ *<Supplier>* reconciliation complete!
    "reco complete",             # short variant when no output file
    "reco failed",               # ❌ *<Supplier>* reco failed!
    "reco triggered",            # ⚙️ *<Supplier>* reco triggered!
    "robot started",             # 🤖 Robot started! Job ID: ...
    # "polling for completion" — REMOVED. The agent narrates this phrase too
    # ("polling for completion...") in long-paragraph messages, so protecting
    # it caused agent commentary to slip through cleanup. The listener's
    # message that uses this string ("🤖 Robot started! Job ID: ...\nPolling
    # for completion...") is already protected by "robot started" above.
    "running now...",
    "missing dates",
    "missing or unknown supplier",
    "multiple suppliers",
    "unknown supplier",
    "couldn't parse json",
    "couldn't reach llm",
    "couldn't parse the request",
    "no file found in message",
    "no xlsx or csv file found",
    "no supported file found",
    "please attach an *xlsx*",
    "got the file",              # "Got the file. Which supplier..."
    "dates must be yyyy-mm-dd",
    "is after end_date",
    "use this format",           # JSON_TEMPLATE_HINT
)


def is_listener_post(text):
    """True if text matches one of the listener's own message templates.
    Used to whitelist legitimate listener posts from cleanup deletion."""
    if not text:
        return False
    t = text.lower()
    return any(s in t for s in LISTENER_PROTECTED_SUBSTRINGS)


def load_suppliers():
    """Load supplier config."""
    with open(SUPPLIERS_CFG, "r") as f:
        return json.load(f)["suppliers"]


def slack_client():
    return WebClient(token=SLACK_TOKEN)


def discover_bot_user_id():
    """Get this bot's Slack user ID via auth.test (so we can detect @mentions)."""
    try:
        result = slack_client().auth_test()
        uid = result.get("user_id", "")
        if uid:
            return uid
    except SlackApiError as e:
        logger.error(f"auth.test failed: {e.response['error']}")
    return ""


def has_bot_mention(text):
    """True if the message text @-mentions this bot."""
    return bool(BOT_USER_ID) and (f"<@{BOT_USER_ID}>" in text)


def strip_mentions(text):
    """Remove all <@Uxxx> mentions from text before sending to LLM."""
    return MENTION_RE.sub("", text).strip()


def first_supported_file(files):
    """Return the first file dict whose name ends with .xlsx / .xls / .xlsb / .csv, else None."""
    for f in files or []:
        name = (f.get("name") or "").lower()
        if name.endswith(SUPPORTED_EXTS):
            return f
    return None


# ── Hallucination cleanup ──────────────────────────────────

def is_hallucinated(text):
    """True if a bot message looks like an agent hallucination."""
    if not text:
        return False
    t = text.lower()
    return any(s in t for s in HALLUCINATED_SUBSTRINGS)


def _try_delete(client, channel_id, ts, label=""):
    """Attempt chat.delete on a single message. Logs and swallows errors."""
    try:
        client.chat_delete(channel=channel_id, ts=ts)
        logger.warning(
            f"Deleted hallucinated agent post {ts} in "
            f"#{CHANNELS.get(channel_id, channel_id)}{label}"
        )
    except SlackApiError as e:
        # message_not_found is fine (already deleted by someone), others log.
        err = e.response.get("error", "")
        if err not in ("message_not_found",):
            logger.error(f"chat.delete failed for {ts}: {err}")


def _gc_completed_threads():
    """Drop completion markers older than COMPLETED_RETENTION_SECS so the dict
    doesn't grow without bound."""
    now = time.time()
    expired = [k for k, v in completed_threads.items() if now - v > COMPLETED_RETENTION_SECS]
    for k in expired:
        completed_threads.pop(k, None)


def _slack_retry_after(api_error):
    """Pull Retry-After (seconds) from a SlackApiError response, or None."""
    try:
        hdr = api_error.response.headers.get("Retry-After")
        return int(hdr) if hdr else None
    except (AttributeError, TypeError, ValueError):
        return None


def cleanup_hallucinations(channel_id):
    """
    Scan one bridge channel (root + active threads) and delete unwanted
    bot posts. Two delete rules:

      a) Hallucination match — bot post whose text contains any of
         HALLUCINATED_SUBSTRINGS. Always deleted.

      b) Post-completion silence — once the listener posts its terminal
         message in a thread (✅/❌), the thread is "complete". Any bot
         reply arriving after a 2-second grace is deleted regardless of
         content. (The listener doesn't post in the same thread again
         after completion; agent posts in completed threads are by
         construction unwanted.)

    Throttled to once per CLEANUP_INTERVAL_SECS per channel — the
    underlying conversations.history + conversations.replies calls are
    Slack Tier-3 (about 50 req/min total), and running cleanup every
    10 s on two channels × ~10 threads each was tripping ratelimited
    errors. Thread completion markers use only thread_ts as key —
    Slack ts values are globally unique across channels.
    """
    now = time.time()
    last = _last_cleanup_per_channel.get(channel_id, 0.0)
    if now - last < CLEANUP_INTERVAL_SECS:
        return  # throttle: this channel's cleanup ran recently

    # Capture the previous bookmark BEFORE updating, so we can skip threads
    # whose latest_reply is older than it (no new activity since last pass).
    prev_bookmark = last
    _last_cleanup_per_channel[channel_id] = now
    _gc_completed_threads()

    client = slack_client()
    try:
        result = client.conversations_history(channel=channel_id, limit=CLEANUP_LOOKBACK_LIMIT)
        messages = result.get("messages", [])
    except SlackApiError as e:
        err = e.response.get("error", "") if hasattr(e, "response") else ""
        if err == "ratelimited":
            wait = _slack_retry_after(e) or RATELIMIT_BACKOFF_SECS
            logger.warning(
                f"cleanup history rate-limited in #{CHANNELS.get(channel_id, channel_id)}; "
                f"backing off {wait}s"
            )
            time.sleep(wait)
        else:
            logger.error(
                f"cleanup history error in #{CHANNELS.get(channel_id, channel_id)}: {err}"
            )
        return

    for msg in messages:
        ts   = msg.get("ts")
        text = msg.get("text", "") or ""
        is_bot_msg = bool(msg.get("subtype") == "bot_message" or msg.get("bot_id"))
        is_dac_msg = msg.get("user") == BOT_USER_ID

        # 1a) Default-deny for any Data Automation's Claw root post that
        #     isn't a listener template. This replaces the old
        #     substring-whitelist approach: instead of chasing every new
        #     agent hallucination variant (raw JSON dumps, "Run Parameters"
        #     blocks, free-form narration, etc.), we trust is_listener_post
        #     to whitelist legitimate listener output and delete everything
        #     else from BOT_USER_ID. Human messages (no bot_id, user !=
        #     BOT_USER_ID) are never touched, so a fresh reco request
        #     posted mid-window survives.
        if is_dac_msg and not is_listener_post(text):
            _try_delete(client, channel_id, ts, label=" (root, non-listener DAC post)")
            continue  # parent gone, nothing to walk

        # 1b) Other bots (CI, Slackbot, etc.) — keep the narrower
        #     hallucination-substring rule so we never wipe an unrelated
        #     bot's legitimate post.
        if is_bot_msg and not is_dac_msg and is_hallucinated(text) and not is_listener_post(text):
            _try_delete(client, channel_id, ts, label=" (root, other bot)")
            continue  # parent gone, nothing to walk

        # 2) Walk replies of ANY parent that has them — the parent is
        #    typically the user's trigger message (human, not bot), and
        #    every status post inside it is a candidate.
        if msg.get("reply_count", 0) > 0:
            # Skip threads with no new activity since our last cleanup
            # pass — saves a conversations.replies call per quiet thread.
            # Always walk threads we've explicitly marked complete (we
            # want to enforce post-completion silence on them even when
            # the agent's noise was edited rather than newly posted).
            try:
                latest_reply = float(msg.get("latest_reply", "0") or "0")
            except (TypeError, ValueError):
                latest_reply = 0.0
            in_completed = ts in completed_threads
            if not in_completed and latest_reply <= prev_bookmark and prev_bookmark > 0:
                continue

            try:
                replies = client.conversations_replies(
                    channel=channel_id, ts=ts, limit=CLEANUP_THREAD_LIMIT
                ).get("messages", [])
            except SlackApiError as e:
                err = e.response.get("error", "") if hasattr(e, "response") else ""
                if err == "ratelimited":
                    # Slack told us to back off — sleep and abort this cleanup
                    # pass entirely. The next poll cycle (after CLEANUP_INTERVAL_SECS)
                    # will re-run if needed.
                    wait = _slack_retry_after(e) or RATELIMIT_BACKOFF_SECS
                    logger.warning(
                        f"cleanup replies rate-limited in "
                        f"#{CHANNELS.get(channel_id, channel_id)}; "
                        f"backing off {wait}s"
                    )
                    time.sleep(wait)
                    return
                logger.error(
                    f"cleanup replies error in #{CHANNELS.get(channel_id, channel_id)}: {err}"
                )
                continue

            completed_at = completed_threads.get(ts)

            for reply in replies:
                rts   = reply.get("ts")
                rtext = reply.get("text", "") or ""
                if rts == ts:
                    continue  # skip parent
                if not (reply.get("subtype") == "bot_message" or reply.get("bot_id")):
                    continue

                # PROTECTION: never delete a listener-template message,
                # regardless of timing. files_upload_v2's actual file-share
                # message can land in Slack 3–5s after the API returns; if
                # we marked the thread complete just before that, we'd
                # otherwise wipe our own success message + output file.
                if is_listener_post(rtext):
                    continue

                # 2a) Always delete hallucination-substring matches.
                if is_hallucinated(rtext):
                    _try_delete(client, channel_id, rts, label=" (thread reply, hallucinated)")
                    continue

                # 2b) Post-completion silence: in a completed thread,
                #     any bot reply later than completion + grace gets
                #     deleted regardless of content. (Listener templates
                #     already short-circuited above, so this only catches
                #     unrecognised agent variants.)
                if completed_at is not None:
                    try:
                        rts_float = float(rts)
                    except (TypeError, ValueError):
                        continue
                    if rts_float > completed_at + COMPLETED_GRACE_SECONDS:
                        _try_delete(client, channel_id, rts, label=" (post-completion noise)")


# ── Regex pre-parser (no LLM call) ─────────────────────────
# Handles the common cases deterministically. The LLM is only invoked when
# regex can't extract both a supplier and at least one date.

def build_phrase_map(suppliers):
    """Map lowercase phrases → supplier_key. Includes the keys (with underscores
    swapped for spaces), the human-readable names, and the slack_trigger_phrases
    from suppliers.json."""
    phrase_map = {}
    for key, conf in suppliers.items():
        # the key itself, both forms
        phrase_map[key.lower()] = key
        phrase_map[key.replace("_", " ").lower()] = key
        # human-readable name
        name = (conf.get("name") or "").lower()
        if name:
            phrase_map[name] = key
        # configured trigger phrases
        for p in conf.get("slack_trigger_phrases", []) or []:
            phrase_map[p.lower()] = key
    return phrase_map


def regex_match_supplier(text, phrase_map):
    """Find longest matching supplier phrase in text. Returns key or None.
    Returns ('multiple', None) if more than one distinct supplier matches."""
    text_l = " " + text.lower() + " "
    found = set()
    longest = (0, None)
    for phrase, key in phrase_map.items():
        # word-boundary-ish: surround with spaces; works for short keys too
        if f" {phrase} " in text_l or text_l.startswith(f"{phrase} ") or text_l.endswith(f" {phrase}"):
            found.add(key)
            if len(phrase) > longest[0]:
                longest = (len(phrase), key)
    if len(found) > 1:
        return "MULTIPLE"
    return longest[1]


def regex_parse_dates(text, default_year):
    """Extract up to 2 dates. Returns list of YYYY-MM-DD strings in order of appearance."""
    text_l = text.lower()
    hits = []  # (position, iso_date)
    used_spans = []  # list of (start, end) ranges already consumed

    def overlaps(start, end):
        return any(not (end <= s or start >= e) for s, e in used_spans)

    # 1) ISO 2026-04-18
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text_l):
        if overlaps(m.start(), m.end()):
            continue
        y, mo, d = m.groups()
        try:
            iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            datetime.strptime(iso, "%Y-%m-%d")  # validate
            hits.append((m.start(), iso))
            used_spans.append((m.start(), m.end()))
        except ValueError:
            pass

    # 2) DD-MM-YYYY or DD/MM/YYYY (Wego is MENA → DD first)
    for m in re.finditer(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", text_l):
        if overlaps(m.start(), m.end()):
            continue
        d, mo, y = m.groups()
        try:
            iso = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            datetime.strptime(iso, "%Y-%m-%d")
            hits.append((m.start(), iso))
            used_spans.append((m.start(), m.end()))
        except ValueError:
            pass

    # 2.5) Shared-month range: "18 to 19 april 2026" / "18-19 april 2026"
    pat25 = re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:to|-|–|—|through|till|until|and|&)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_NAMES})[a-z]*\s*,?\s*(\d{{4}})?\b"
    )
    for m in pat25.finditer(text_l):
        if overlaps(m.start(), m.end()):
            continue
        d1, d2, mo_str, y = m.groups()
        mo_num = MONTH_NUM.get(mo_str)
        if not mo_num:
            continue
        y = int(y) if y else default_year
        try:
            iso1 = f"{y:04d}-{mo_num:02d}-{int(d1):02d}"
            iso2 = f"{y:04d}-{mo_num:02d}-{int(d2):02d}"
            datetime.strptime(iso1, "%Y-%m-%d"); datetime.strptime(iso2, "%Y-%m-%d")
            hits.append((m.start(), iso1))
            hits.append((m.start() + 1, iso2))  # +1 so sort order is preserved
            used_spans.append((m.start(), m.end()))
        except ValueError:
            pass

    # 3) "18 april 2026" or "18 apr" or "18th april 2026"
    pat3 = re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_NAMES})[a-z]*\s*,?\s*(\d{{4}})?\b"
    )
    for m in pat3.finditer(text_l):
        if overlaps(m.start(), m.end()):
            continue
        d, mo_str, y = m.groups()
        mo_num = MONTH_NUM.get(mo_str)
        if not mo_num:
            continue
        y = int(y) if y else default_year
        try:
            iso = f"{y:04d}-{mo_num:02d}-{int(d):02d}"
            datetime.strptime(iso, "%Y-%m-%d")
            hits.append((m.start(), iso))
            used_spans.append((m.start(), m.end()))
        except ValueError:
            pass

    # 4) "april 18 2026" / "april 18, 2026"
    pat4 = re.compile(
        rf"\b({MONTH_NAMES})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})?\b"
    )
    for m in pat4.finditer(text_l):
        if overlaps(m.start(), m.end()):
            continue
        mo_str, d, y = m.groups()
        mo_num = MONTH_NUM.get(mo_str)
        if not mo_num:
            continue
        y = int(y) if y else default_year
        try:
            iso = f"{y:04d}-{mo_num:02d}-{int(d):02d}"
            datetime.strptime(iso, "%Y-%m-%d")
            hits.append((m.start(), iso))
            used_spans.append((m.start(), m.end()))
        except ValueError:
            pass

    # Sort by position, return the iso strings (preserve order they appeared)
    hits.sort(key=lambda x: x[0])
    return [iso for _, iso in hits]


def regex_parse(text, suppliers, phrase_map):
    """
    Try regex parsing. Returns dict {action, start_date, end_date} on success;
    returns None if it can't extract enough; returns {"error": "..."} for
    definitive failures (e.g. multiple suppliers).
    """
    cleaned   = strip_mentions(text)
    today     = datetime.utcnow()
    default_y = today.year

    action = regex_match_supplier(cleaned, phrase_map)
    if action == "MULTIPLE":
        return {"error": "multiple suppliers"}
    if not action:
        return None  # let LLM try

    dates = regex_parse_dates(cleaned, default_y)
    if not dates:
        return None  # let LLM try (might be 'last month', 'today', etc.)

    sd = dates[0]
    ed = dates[1] if len(dates) >= 2 else dates[0]
    if sd > ed:
        sd, ed = ed, sd

    return {"action": action, "start_date": sd, "end_date": ed}


def slack_post_message(channel, text, thread_ts=None):
    client = slack_client()
    try:
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        client.chat_postMessage(**payload)
    except SlackApiError as e:
        logger.error(f"Slack post error: {e.response['error']}")


def slack_upload_file(channel, file_path, filename, thread_ts=None, comment=""):
    client = slack_client()
    try:
        with open(file_path, "rb") as f:
            response = client.files_upload_v2(
                channel=channel,
                file=f,
                filename=filename,
                title=filename,
                initial_comment=comment,
                thread_ts=thread_ts
            )
        if response["ok"]:
            logger.info(f"File uploaded: {filename}")
        else:
            logger.error(f"Upload failed: {response.get('error')}")
        return response
    except SlackApiError as e:
        logger.error(f"SlackApiError: {e.response['error']}")
        return None


def download_slack_file(file_url, dest_path):
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    # stream=True + iter_content guarantees a byte-for-byte write even on a
    # large or partial response — no risk of an in-memory copy being
    # truncated. Matters for xlsb files where a single missing byte
    # corrupts the zip-based internal structure.
    with requests.get(file_url, headers=headers, timeout=60, stream=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    logger.info(f"Downloaded file to {dest_path} ({os.path.getsize(dest_path)} bytes)")


# ── xlsb structure check ──────────────────────────────────
# pyxlsb (used by Dnata's `convert_and_rename_xlsb_files`) requires the
# internal file `xl/_rels/workbook.bin.rels` inside the xlsb zip. Files
# that have been opened-then-resaved by LibreOffice (and some other
# tools) drop that rels file, producing a confusing
#   KeyError: "There is no item named 'xl/_rels/workbook.bin.rels' …"
# 30s later inside the robot. We validate at the listener so the user
# gets a clear, actionable Slack reply immediately.

import zipfile  # stdlib — no requirements bump

XLSB_REQUIRED_INTERNAL = "workbook.bin.rels"


def validate_xlsb_structure(path):
    """Return (ok, reason).
    ok=True  → file is a valid zip and contains the rels file pyxlsb needs.
    ok=False → reason is a short human-readable string ready to drop into
               a Slack message."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        return False, "the file isn't a valid xlsb (zip header is broken)"
    if not any(n.endswith(XLSB_REQUIRED_INTERNAL) for n in names):
        return False, (
            "the xlsb is missing `xl/_rels/workbook.bin.rels` — usually "
            "happens when the file was opened and resaved by LibreOffice. "
            "Re-download the original from Dnata's email and upload it "
            "without opening it first."
        )
    return True, ""


# ── NL → JSON parsing (Claude) ─────────────────────────────

def parse_nl_to_trigger(text, supplier_keys):
    """
    Convert natural-language reco request into {action, start_date, end_date}.
    Returns the dict on success, or {"error": "<reason>"} otherwise.

    Uses OpenAI Chat Completions API (gpt-4o-mini) with response_format=json_object
    so the model is forced to return valid JSON. Full scenario reference and how
    to extend the prompt: test_py/prompt_eng.md.
    """
    today      = datetime.utcnow().strftime("%Y-%m-%d")
    today_year = today[:4]
    keys_csv   = ", ".join(sorted(supplier_keys))

    system_prompt = f"""You convert finance supplier reconciliation requests into strict JSON.

Today's date: {today}.
Default year when missing: {today_year}.
Available supplier keys (lowercase, exact match — never invent a new key):
{keys_csv}

Output rules:
- Output ONLY a JSON object with keys: action, start_date, end_date — no prose, no code fences.
- Dates are YYYY-MM-DD.
- start_date <= end_date (swap silently if the user reverses them).
- If the user gives one date, set both start and end to it.
- "today" / "yesterday" = that single date.
- "this week" = Monday of current week to today.
- "last week" = Monday to Sunday of last week.
- "this month" = first of this month to today.
- "last month" = first to last day of last month.
- Year missing → use {today_year}. Day-only with month → assume same year.
- Numeric format ambiguity (e.g. 04/05/2026): treat as DD/MM/YYYY (Wego is in Asia/MENA).

Supplier matching:
- Map common phrasings to the exact key (jazeera reco → jazeera; air arabia → air_arabia; spice jet / spicejet → spicejet; fly dubai → flydubai).
- Multi-variant suppliers: only emit a key if the user disambiguated. Otherwise return error.
  Belair: belair_travel | belair_inr | belair_sgd
  Chamwings: chamwings_ae | chamwings_int | chamwings_om
  Dnata: dnata_bh | dnata_gold | dnata_om
  Kanoo: kanoo_sar | kanoo_egypt | kanoo_aed | kanoo_bhd
  Monde: monde_cad | monde_usd
  Flyin: flyin_egp | flyin_eg_lc | flyin_sar

Failure modes:
- Supplier missing, ambiguous, or not in the list → {{"error": "missing or unknown supplier"}}.
- Cannot pin down BOTH dates → {{"error": "missing dates"}}.
- Multiple suppliers mentioned → {{"error": "multiple suppliers"}}.

Examples:

User: run jazeera reco from 18 to 19 april 2026
Output: {{"action": "jazeera", "start_date": "2026-04-18", "end_date": "2026-04-19"}}

User: jaz reco for 27 april
Output: {{"action": "jazeera", "start_date": "{today_year}-04-27", "end_date": "{today_year}-04-27"}}

User: indigo reco 18-04-2026 to 19-04-2026
Output: {{"action": "indigo", "start_date": "2026-04-18", "end_date": "2026-04-19"}}

User: please run flydubai reconciliation yesterday to today
Output: {{"action": "flydubai", "start_date": "<yesterday-iso>", "end_date": "{today}"}}

User: belair reco for april 18
Output: {{"error": "missing or unknown supplier"}}

User: run reco for 18 april
Output: {{"error": "missing or unknown supplier"}}

User: jazeera reco
Output: {{"error": "missing dates"}}

User: run jazeera and flydubai reco for april
Output: {{"error": "multiple suppliers"}}
"""

    # Slack converts @mentions to <@Uxxx>; strip them so the model doesn't
    # treat the mention token as part of a supplier name.
    cleaned = strip_mentions(text)

    body = {
        "model": OPENAI_MODEL,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": cleaned},
        ],
        # Force JSON output — model must return a JSON object.
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type":  "application/json",
    }

    resp = requests.post(OPENAI_URL, headers=headers, json=body, timeout=OPENAI_TIMEOUT)
    if resp.status_code != 200:
        logger.error(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
        return {"error": f"LLM HTTP {resp.status_code}"}

    raw = resp.json()["choices"][0]["message"]["content"].strip()
    s, e = raw.find("{"), raw.rfind("}") + 1
    if s == -1 or e == 0:
        return {"error": "model returned no JSON"}
    try:
        return json.loads(raw[s:e])
    except json.JSONDecodeError:
        return {"error": "model returned invalid JSON"}


def validate_trigger(trigger, supplier_keys):
    """(ok, reason) — strict validation before triggering robot."""
    if "error" in trigger:
        return False, trigger["error"]
    action = (trigger.get("action") or "").lower()
    if action not in supplier_keys:
        return False, f"unknown supplier '{action}'"
    sd = trigger.get("start_date", "")
    ed = trigger.get("end_date", "")
    if not ISO_DATE_RE.match(sd) or not ISO_DATE_RE.match(ed):
        return False, "dates must be YYYY-MM-DD"
    if sd > ed:
        return False, f"start_date {sd} is after end_date {ed}"
    return True, ""


JSON_TEMPLATE_HINT = (
    "Use this format (or just attach an xlsx with text like "
    "`run jazeera reco for 18 april 2026`):\n"
    '`{"action": "<supplier_key>", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}`'
)


# ── Robot trigger / job polling ────────────────────────────

def trigger_supplier(supplier_key, file_path, start_date, end_date):
    ext = os.path.splitext(file_path)[1].lower()
    mime = MIME_BY_EXT.get(ext, "application/octet-stream")
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{API_BASE}/trigger/{supplier_key}",
            files={"file": (os.path.basename(file_path), f, mime)},
            data={"start_date": start_date, "end_date": end_date},
            timeout=30
        )
    if r.status_code != 202:
        raise Exception(f"Trigger failed: {r.text}")
    return r.json()["job_id"]


def poll_job(job_id, max_polls=JOB_POLL_MAX):
    for i in range(max_polls):
        time.sleep(JOB_POLL_SLEEP)
        r = requests.get(f"{API_BASE}/status/{job_id}", timeout=5)
        status = r.json()["status"]
        logger.info(f"Job {job_id} status: {status}")
        if status in ("success", "failed", "timeout", "error"):
            return status
    return "timeout"


def find_output_file(supplier_config):
    """Latest Final_Summary file by modification time."""
    base = supplier_config["output_folder"]
    if not os.path.exists(base):
        return None
    latest_file, latest_time = None, 0
    for folder in os.listdir(base):
        folder_path = os.path.join(base, folder)
        if not os.path.isdir(folder_path):
            continue
        for f in os.listdir(folder_path):
            if f.startswith("Final_Summary") and f.endswith(".xlsx"):
                full_path = os.path.join(folder_path, f)
                mtime = os.path.getmtime(full_path)
                if mtime > latest_time:
                    latest_time, latest_file = mtime, full_path
    logger.info(f"Found output file: {latest_file}")
    return latest_file


# ── Failure diagnostics ────────────────────────────────────
# nova_api writes per-job logs to /config/rpa/openclaw/logs/job_<id>.log
# (matches nova_api.LOGS_DIR). Listener and nova_api share this filesystem,
# so we read the file directly instead of curl'ing /logs/<id>.

JOB_LOG_DIR = "/config/rpa/openclaw/logs"

# Strip the "[YYYY-MM-DD HH:MM:SS] " prefix nova_api adds to every log line.
_TS_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s+")

# Patterns ordered by how informative they are. First hit wins.
_PYTHON_EXC_RE   = re.compile(r"^[A-Z]\w*(Error|Exception):\s.+", re.MULTILINE)
_TRACEBACK_RE    = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)


def _strip_ts(line):
    return _TS_PREFIX_RE.sub("", line).rstrip()


def read_job_log_tail(job_id, tail_lines=300):
    """Read up to the last `tail_lines` lines of a job's log file.
    Returns the joined text, or None if the file is missing/unreadable."""
    path = f"{JOB_LOG_DIR}/job_{job_id}.log"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-tail_lines:]) if lines else ""
    except OSError as e:
        logger.warning(f"could not read job log {path}: {e}")
        return None


def extract_failure_reason(log_text):
    """Pull the most likely root-cause line from a robot job log tail.
    Strategy (first hit wins):
      1. Python exception line (KeyError, ValueError, TypeError, ...)
      2. Last 'Traceback (most recent call last):' block (next non-empty line)
      3. Robot's '| FAIL |' marker (last occurrence)
      4. Last non-empty line as fallback
    Returns a single-line string, or None if nothing useful is found."""
    if not log_text:
        return None

    stripped_lines = [_strip_ts(ln) for ln in log_text.splitlines()]
    flat = "\n".join(stripped_lines)

    # 1) Python exception
    m = _PYTHON_EXC_RE.search(flat)
    if m:
        return m.group(0).strip()

    # 2) Traceback — return next meaningful line
    if _TRACEBACK_RE.search(flat):
        seen_traceback = False
        for line in stripped_lines:
            if not seen_traceback:
                if line.startswith("Traceback (most recent call last):"):
                    seen_traceback = True
                continue
            if line and not line.startswith("  ") and not line.startswith("File "):
                return line.strip()

    # 3) Robot FAIL marker
    for line in reversed(stripped_lines):
        if "| FAIL |" in line:
            return line.strip()

    # 4) Last non-empty line
    for line in reversed(stripped_lines):
        if line.strip():
            return line.strip()

    return None


def analyse_failure_with_llm(log_text, supplier_name):
    """Ask OpenAI to summarise a robot job failure into 3 short fields.

    Returns a dict with keys {root_cause, where, fix} on success, or None
    on any failure (network, auth, malformed response). Caller MUST be
    prepared to fall back to the regex extractor.

    Cost: ~10K input tokens × $0.15/1M = ~$0.0015 per failure. Failures
    are rare; cost is negligible.
    """
    if not NL_PARSE_ENABLED or not log_text:
        return None

    # Cap input — gpt-4o-mini handles 128K tokens but the interesting
    # part of a robot log is always near the bottom (last ~150 lines).
    tail_lines = log_text.splitlines()[-200:]
    capped = "\n".join(tail_lines)
    if len(capped) > 15000:
        capped = capped[-15000:]

    system_prompt = (
        "You are a Robot Framework / Python failure analyst for a "
        "finance supplier reconciliation pipeline. You will be given the "
        "tail of a failed robot job log. Your job is to produce a brief, "
        "plain-language failure summary for a Slack message read by a "
        "non-technical finance team.\n\n"
        "Rules:\n"
        "1. Be PRECISE. Quote exact identifiers (column names, exception "
        "types, file paths) when present in the log.\n"
        "2. Do NOT invent details. If the log doesn't show a clear root "
        "cause, say so honestly.\n"
        "3. Each field is ONE short sentence (<= 200 chars). No bullet "
        "points, no markdown headers, no log-line copy-paste.\n"
        "4. 'fix' should be actionable for a finance user (e.g. 'verify "
        "input file column headers', 'check the supplier portal is up') "
        "— not a developer instruction. Empty string if no obvious fix.\n\n"
        'Respond with JSON: {"root_cause": "...", "where": "...", "fix": "..."}'
    )

    body = {
        "model": OPENAI_MODEL,
        "max_tokens": 350,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Supplier: {supplier_name}\n\nLog tail:\n{capped}"},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        resp = requests.post(OPENAI_URL, headers=headers, json=body, timeout=OPENAI_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(f"LLM failure-analysis HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s == -1 or e == 0:
            return None
        parsed = json.loads(raw[s:e])
        if not isinstance(parsed, dict):
            return None
        # Coerce + truncate to keep Slack message bounded.
        return {
            "root_cause": str(parsed.get("root_cause") or "").strip()[:300],
            "where":      str(parsed.get("where")      or "").strip()[:300],
            "fix":        str(parsed.get("fix")        or "").strip()[:300],
        }
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.warning(f"LLM failure-analysis exception: {e}")
        return None


def post_failure_report(channel_id, thread_ts, supplier, job_id, final_status):
    """Send a clean, AI-summarised failure message — no log dump, no file
    attachment. Falls back to regex-extracted error if LLM is disabled,
    unreachable, or returns nothing usable. Final fallback is a generic
    'inspect log on server' message so the user is never left silent."""
    log_text = read_job_log_tail(job_id, tail_lines=500)

    body_lines = [
        f"❌ *{supplier['name']}* reco failed!",
        f"Job ID: `{job_id}` | Status: `{final_status}`",
        "",
    ]

    summary = analyse_failure_with_llm(log_text, supplier["name"]) if log_text else None

    if summary and summary.get("root_cause"):
        body_lines.append(f"*What went wrong:* {summary['root_cause']}")
        if summary.get("where"):
            body_lines.append(f"*Where:* {summary['where']}")
        if summary.get("fix"):
            body_lines.append(f"*Likely fix:* {summary['fix']}")
    else:
        # LLM unavailable / returned nothing useful — use deterministic
        # regex extractor as backup so the user always gets *something*.
        reason = extract_failure_reason(log_text) if log_text else None
        if reason:
            body_lines.append(f"*Error:* `{reason}`")
        else:
            body_lines.append(
                f"_Could not determine specific failure reason. "
                f"Inspect `/config/rpa/openclaw/logs/job_{job_id}.log` on the server._"
            )

    slack_post_message(channel_id, "\n".join(body_lines), thread_ts)


# ── Trigger handling ───────────────────────────────────────

def execute_trigger(message, suppliers, trigger, channel_id):
    """
    Run the full pipeline given a validated trigger dict, in the
    channel where the user posted the request. `message` is the original
    Slack message; it must already carry `_matched_file` (set by
    poll_channel after the @mention + file checks).
    """
    ts        = message.get("ts")
    thread_ts = message.get("thread_ts", ts)

    action     = trigger["action"].lower()
    start_date = trigger["start_date"]
    end_date   = trigger["end_date"]
    supplier   = suppliers[action]

    # Acknowledge
    slack_post_message(channel_id,
        f"⚙️ *{supplier['name']}* reco triggered!\n"
        f"📅 Period: `{start_date}` → `{end_date}`\n"
        f"Running now...",
        thread_ts)

    # Resolve the supported file picked by poll_channel
    matched = message.get("_matched_file") or first_supported_file(message.get("files") or [])
    if not matched:
        slack_post_message(channel_id,
            "❌ No supported file found in this message. "
            "Attach an *xlsx*, *xls*, *xlsb*, or *csv*.", thread_ts)
        return
    file_url  = matched.get("url_private_download")
    orig_name = matched.get("name") or "upload.xlsx"
    ext       = os.path.splitext(orig_name)[1].lower() or ".xlsx"
    if ext not in SUPPORTED_EXTS:
        ext = ".xlsx"

    # Preserve the ORIGINAL Slack filename (with light sanitisation).
    # Many supplier robots derive downstream filenames by extracting a
    # token from the source name — e.g. Dnata BH's `convert_and_rename_
    # xlsb_files` keyword turns "Wego PTE LTD BAH-DTM409-Settlement
    # Detail.xlsb" into "DTM409.xlsx", and the next step then looks for
    # `DTM409.xlsx` literally. Renaming to <supplier>_upload_<ts> stripped
    # that token and broke the chain. We replace spaces / unsafe shell
    # chars with underscores; the meaningful tokens (DTM409, BAH, etc.)
    # are preserved. Fallback to the old name if sanitisation produces
    # something empty.
    safe_name = re.sub(r"[^\w\-.]+", "_", orig_name).strip("_")
    if not safe_name or safe_name == ext.lstrip("."):
        safe_name = f"{action}_upload_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
    dest_path = f"/config/Downloads/{safe_name}"
    download_slack_file(file_url, dest_path)

    # Catch broken xlsb uploads BEFORE handing off to nova_api, otherwise
    # the robot crashes 30s later with an opaque pyxlsb traceback. The
    # most common cause: file was opened/resaved by LibreOffice on the
    # user's desktop before they dragged it into Slack, which strips the
    # `xl/_rels/workbook.bin.rels` internal file pyxlsb requires.
    if ext == ".xlsb":
        ok, reason = validate_xlsb_structure(dest_path)
        if not ok:
            logger.error(f"xlsb validation failed for {dest_path}: {reason}")
            slack_post_message(channel_id,
                f"❌ *{supplier['name']}* reco failed before robot start — {reason}",
                thread_ts)
            completed_threads[thread_ts] = time.time()
            return

    # Trigger robot
    job_id = trigger_supplier(action, dest_path, start_date, end_date)
    logger.info(f"Job created: {job_id}")
    slack_post_message(channel_id,
        f"🤖 Robot started! Job ID: `{job_id}`\nPolling for completion...",
        thread_ts)

    # Poll
    final_status = poll_job(job_id)

    if final_status == "success":
        output_file = find_output_file(supplier)
        if output_file:
            slack_upload_file(
                channel_id,
                output_file,
                os.path.basename(output_file),
                thread_ts,
                f"✅ *{supplier['name']}* reconciliation complete!\n"
                f"📅 Period: `{start_date}` → `{end_date}`"
            )
        else:
            slack_post_message(channel_id,
                f"✅ *{supplier['name']}* reco complete!",
                thread_ts)
    else:
        post_failure_report(channel_id, thread_ts, supplier, job_id, final_status)

    # Mark this thread as complete. Cleanup will delete any bot reply
    # that arrives here after the 2-second grace period. Slack ts values
    # are globally unique so the marker doesn't need the channel_id.
    completed_threads[thread_ts] = time.time()
    logger.info(
        f"Thread {thread_ts} in #{CHANNELS.get(channel_id, channel_id)} "
        f"marked complete; future bot posts will be cleaned."
    )


def process_json_trigger(message, suppliers, channel_id):
    """Path 1 — message contains a literal JSON object with 'action'."""
    ts        = message.get("ts")
    text      = message.get("text", "")
    thread_ts = message.get("thread_ts", ts)

    try:
        s, e = text.find("{"), text.rfind("}") + 1
        if s == -1 or e == 0:
            return
        trigger = json.loads(text[s:e])
    except json.JSONDecodeError:
        slack_post_message(channel_id,
            f"❌ Couldn't parse JSON. {JSON_TEMPLATE_HINT}", thread_ts)
        return

    ok, reason = validate_trigger(trigger, set(suppliers.keys()))
    if not ok:
        slack_post_message(channel_id,
            f"❌ {reason}. Available: {sorted(suppliers.keys())[:6]}…", thread_ts)
        return

    try:
        execute_trigger(message, suppliers, trigger, channel_id)
    except Exception as ex:
        logger.error(f"Execute error: {ex}")
        slack_post_message(channel_id, f"❌ Error: {ex}", thread_ts)


def process_nl_trigger(message, suppliers, channel_id):
    """
    Path 2 — natural language with file attached. Strategy:
      1. Try the regex pre-parser first (fast, free, no LLM call).
      2. If regex returns a usable trigger → validate → run.
      3. If regex returns None (couldn't extract supplier+dates) → fall back to LLM.
      4. If LLM also fails → ask the user to clarify.
    """
    ts         = message.get("ts")
    text       = message.get("text", "")
    thread_ts  = message.get("thread_ts", ts)
    keys_set   = set(suppliers.keys())
    phrase_map = build_phrase_map(suppliers)

    # ── Stage 1: regex
    regex_result = regex_parse(text, suppliers, phrase_map)

    if isinstance(regex_result, dict) and "error" not in regex_result:
        # Got a candidate from regex
        ok, reason = validate_trigger(regex_result, keys_set)
        if ok:
            logger.info(f"regex parsed → {regex_result}")
            try:
                execute_trigger(message, suppliers, regex_result, channel_id)
            except Exception as ex:
                logger.error(f"Execute error: {ex}")
                slack_post_message(channel_id, f"❌ Error: {ex}", thread_ts)
            return
        # regex got something but it didn't validate — fall through to LLM

    if isinstance(regex_result, dict) and "error" in regex_result:
        # Definitive regex error (e.g. "multiple suppliers") — don't bother LLM
        slack_post_message(channel_id,
            f"❓ {regex_result['error']}. {JSON_TEMPLATE_HINT}", thread_ts)
        return

    # ── Stage 2: LLM fallback (regex returned None — couldn't pin both fields)
    if not NL_PARSE_ENABLED:
        slack_post_message(channel_id,
            f"❓ Couldn't parse the request and the LLM key isn't configured. "
            f"{JSON_TEMPLATE_HINT}",
            thread_ts)
        return

    try:
        trigger = parse_nl_to_trigger(text, keys_set)
    except Exception as ex:
        logger.error(f"LLM call failed: {ex}")
        slack_post_message(channel_id,
            f"❌ LLM unavailable ({ex}). Try posting raw JSON: {JSON_TEMPLATE_HINT}",
            thread_ts)
        return

    ok, reason = validate_trigger(trigger, keys_set)
    if not ok:
        slack_post_message(channel_id,
            f"❓ {reason}. {JSON_TEMPLATE_HINT}", thread_ts)
        return

    logger.info(f"LLM parsed → {trigger}")
    try:
        execute_trigger(message, suppliers, trigger, channel_id)
    except Exception as ex:
        logger.error(f"Execute error: {ex}")
        slack_post_message(channel_id, f"❌ Error: {ex}", thread_ts)


# ── OpenAI key self-test ───────────────────────────────────

def test_openai_key():
    """Ping the OpenAI API at startup with a tiny call. Returns (ok, msg)."""
    if not NL_PARSE_ENABLED:
        return False, "no key set (placeholder)"
    body = {
        "model": OPENAI_MODEL,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type":  "application/json",
    }
    try:
        r = requests.post(OPENAI_URL, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            return True, "OK"
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
    except Exception as e:
        return False, str(e)


# ── Channel poll loop ──────────────────────────────────────

def _process_channel(channel_id, suppliers):
    """One pass over a single channel: cleanup, then process new triggers."""
    # Sweep agent hallucinations first so noise is gone before we process new triggers.
    cleanup_hallucinations(channel_id)

    client = slack_client()
    try:
        result   = client.conversations_history(channel=channel_id, limit=10)
        messages = result.get("messages", [])
    except SlackApiError as e:
        logger.error(
            f"history error in #{CHANNELS.get(channel_id, channel_id)}: "
            f"{e.response['error']}"
        )
        return

    for message in messages:
        ts   = message.get("ts")
        text = message.get("text", "") or ""

        if not ts or float(ts) < float(STARTUP_TS):
            continue
        # processed_ts is a single global set; ts is globally unique across channels
        if ts in processed_ts:
            continue
        # skip messages from any bot (including this listener's own posts)
        if message.get("subtype") == "bot_message" or message.get("bot_id"):
            continue

        # ── Required filters: must @mention this bot AND attach xlsx/csv ──
        if not has_bot_mention(text):
            # not addressed to us; ignore silently (channel may have unrelated chatter)
            continue

        matched_file = first_supported_file(message.get("files") or [])
        if not matched_file:
            # mentioned but no usable file — nudge the user once
            processed_ts.add(ts)
            slack_post_message(channel_id,
                "Please attach an *xlsx*, *xls*, *xlsb*, or *csv* file with your "
                "reconciliation request (and tell me which supplier + which dates).",
                message.get("thread_ts", ts))
            continue

        # Stash for execute_trigger
        message["_matched_file"] = matched_file

        # Path 1: explicit JSON in the message body
        if '"action"' in text:
            logger.info(f"JSON trigger {ts} in #{CHANNELS.get(channel_id, channel_id)}")
            processed_ts.add(ts)
            process_json_trigger(message, suppliers, channel_id)
            continue

        # Path 2: natural language → LLM parse
        if text.strip():
            logger.info(
                f"NL trigger candidate {ts} in #{CHANNELS.get(channel_id, channel_id)}: "
                f"{strip_mentions(text)[:120]}"
            )
            processed_ts.add(ts)
            process_nl_trigger(message, suppliers, channel_id)
        else:
            # @mention + file but no actual text — ask for the request
            processed_ts.add(ts)
            slack_post_message(channel_id,
                "Got the file. Which supplier and which dates? "
                "(e.g. `run jazeera reco for 18 april 2026`)",
                message.get("thread_ts", ts))


def poll_channel():
    """One full poll cycle — process every configured channel independently."""
    try:
        suppliers = load_suppliers()
    except Exception as e:
        logger.error(f"load_suppliers error: {e}")
        return

    for channel_id in CHANNEL_IDS:
        try:
            _process_channel(channel_id, suppliers)
        except SlackApiError as e:
            logger.error(
                f"Slack API error in #{CHANNELS.get(channel_id, channel_id)}: "
                f"{e.response['error']}"
            )
        except Exception as e:
            logger.error(
                f"Poll error in #{CHANNELS.get(channel_id, channel_id)}: {e}"
            )


def main():
    global BOT_USER_ID

    # Pull the OpenAI key from AWS Secrets Manager before anything else
    # tries to use it (banner self-test, NL parse, failure analyser).
    initialize_openai_client()

    # If hardcoded value got cleared somehow, try to discover via auth.test.
    if not BOT_USER_ID:
        BOT_USER_ID = discover_bot_user_id()

    logger.info("=" * 50)
    logger.info("AlphaBot Slack Listener starting")
    logger.info(f"Channels       : {len(CHANNEL_IDS)} configured")
    for cid, cname in CHANNELS.items():
        logger.info(f"  - {cid}  #{cname}")
    logger.info(f"Channel poll   : every {POLL_INTERVAL}s (each channel)")
    logger.info(f"Cleanup pass   : at most once every {CLEANUP_INTERVAL_SECS}s per channel "
                f"(rate-limit-safe; back-off on ratelimited)")
    logger.info(f"Job poll       : every {JOB_POLL_SLEEP}s, cap {JOB_POLL_MAX} polls "
                f"({JOB_POLL_SLEEP * JOB_POLL_MAX // 60} min)")
    logger.info(f"API            : {API_BASE}")
    logger.info(f"Bot user ID    : {BOT_USER_ID or 'UNKNOWN — fix BOT_USER_ID or auth.test'}")
    logger.info(f"Required filter: @mention to bot ({BOT_USER_ID}) + xlsx/xls/xlsb/csv attached")
    logger.info(f"Auto-cleanup   : ON (deletes bot posts containing hallucination phrases)")
    logger.info(f"Parser         : regex first (free, instant), LLM fallback")
    logger.info(f"LLM provider   : OpenAI")
    logger.info(f"LLM model      : {OPENAI_MODEL if NL_PARSE_ENABLED else 'disabled (placeholder key)'}")
    if NL_PARSE_ENABLED:
        ok, msg = test_openai_key()
        if ok:
            logger.info(f"OpenAI key     : valid ✓")
        else:
            logger.error(f"OpenAI key     : INVALID — {msg}")
            logger.error("LLM fallback will fail. Regex-only requests still work; "
                         "anything regex can't parse will get an LLM-failed reply.")
    logger.info(f"Startup TS     : {STARTUP_TS}")
    logger.info("=" * 50)

    if not BOT_USER_ID:
        logger.error("Bot user_id is empty — every message will be ignored. "
                     "Set BOT_USER_ID or fix Slack token, then restart.")

    while True:
        try:
            poll_channel()
        except Exception as e:
            logger.error(f"Main loop error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()