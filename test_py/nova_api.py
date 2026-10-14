"""
nova_api.py — NOVA AlphaBot Trigger API
Flask API running inside the AlphaBot container.
Lives at: /config/rpa/openclaw/Finance/Supplier/LCC/nova_api.py
Logs at:  /config/rpa/openclaw/logs/

Endpoints:
    GET  /health                      — confirm API is alive
    POST /trigger/test                — run test_nova_connection.robot
    POST /trigger/<supplier>          — trigger any supplier robot
    GET  /status/<job_id>             — check job status
    GET  /logs/<job_id>               — get full logs for a job
    GET  /jobs                        — list all jobs (history)

================================================================================
CHANGES vs current AlphaBot main (test_py copy — for review/deployment):
  • run_robot(): process.wait(timeout) raised 600 → 900 (10 min → 15 min).
    Aligns with slack_listener poll cap and OpenClaw poll cap. Some larger
    supplier robots were exceeding 10 min and being killed mid-run.
  • Skip-keyword strategy: --skip → --prerunmodifier skip_keywords.py.
    Reason: in the supplier .robot files, "Download the report from the
    web portal" and "Send the excel file to the management" are keyword
    calls inside ONE big test case, not separate test cases. Robot's
    --skip flag matches test names only, never keyword calls — that's
    why nothing was being skipped before. The new pre-run modifier walks
    the test body in memory and removes the named keyword calls without
    touching the .robot file on disk (so the scheduled job that uses the
    same file still runs the full flow).
  • Per-supplier upload directory via download_path_template (NEW):
    For Gmail-download suppliers (43 of them, audited from
    Supplier_Reco_*/*.robot in AlphaBot), the robot's "Download the
    report from Gmail" keyword writes to a supplier-specific path
    like /config/Finance_Files/AirIndia_Express_SReco/<DD-MM-YYYY>/raw/.
    Now that we skip that keyword via --prerunmodifier, the input file
    has to land there ourselves so the rest of the robot finds it.
    nova_api now reads `download_path_template` from suppliers.json
    (with `{date}` placeholder), resolves it to today's DD-MM-YYYY,
    creates the directory tree, and saves. Suppliers without the
    field (web-portal automations, atlas_lc which uses ~/Downloads)
    keep saving to /config/Downloads/. Backward compatible.
    Per-supplier path mappings: see test_py/gmail_download_paths.md.
================================================================================
"""

import os
import re
import uuid
import json
import subprocess
import threading
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request

app = Flask(__name__)

# ── Paths ──────────────────────────────────────────────────
BASE_DIR        = "/config/rpa/openclaw"
LOGS_DIR        = f"{BASE_DIR}/logs"
ROBOT_CMD       = "/usr/local/bin/robot"
WORKDIR         = "/config"
TEST_ROBOT      = f"{BASE_DIR}/test_nova_connection.robot"
SUPPLIERS_CFG   = f"{BASE_DIR}/Finance/Supplier/LCC/suppliers.json"
SKIP_KW_MODULE  = f"{BASE_DIR}/Finance/Supplier/LCC/skip_keywords.py"

# Robot subprocess hard timeout (seconds). 15 min = aligned with poll caps.
ROBOT_TIMEOUT_SECONDS = 900   # CHANGED from 600

# Create logs directory on startup
os.makedirs(LOGS_DIR, exist_ok=True)

# ── API-level logger ───────────────────────────────────────
api_log_path = f"{LOGS_DIR}/nova_api.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(api_log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nova_api")

# ── In-memory job store ────────────────────────────────────
jobs = {}


def load_suppliers():
    """Load supplier config from JSON."""
    with open(SUPPLIERS_CFG, "r") as f:
        return json.load(f)["suppliers"]


# Matches the supplier robot's date offset definition, e.g.
#   ${date_offset}    -0
#   ${date_offset}=   -2
#   ${date_offset} =   2
# Anchored to line start so usage lines (`... increment=${date_offset} day`)
# and commented-out lines (`# ${date_offset} ...`) never match. The greedy
# \s* backtracks so it works whether or not an `=` is present.
_DATE_OFFSET_RE = re.compile(
    r"^\s*\$\{date_offset\}\s*=?\s+(-?\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def get_date_offset(supplier):
    """Read ${date_offset} straight from the supplier's .robot file so the
    robot stays the single source of truth (no drift vs suppliers.json).

    The robot derives its date folder as `Get Current Date` + ${date_offset}
    days; nova_api must save the uploaded file into that SAME folder. Each
    robot can carry a different offset (0, -2, ...), so we parse it per run.

    Resolution order:
      1. Parse ${date_offset} from the .robot file at robot_path.
      2. Fall back to 0 (with a warning) if the file is missing, unreadable,
         or doesn't define ${date_offset}.
    """
    robot_path = supplier.get("robot_path")
    if not robot_path or not os.path.exists(robot_path):
        logger.warning(
            f"robot file not found for date_offset lookup "
            f"({robot_path}); defaulting offset to 0"
        )
        return 0
    try:
        with open(robot_path, "r", errors="replace") as f:
            content = f.read()
    except OSError as e:
        logger.warning(f"could not read robot file {robot_path}: {e}; defaulting offset to 0")
        return 0
    m = _DATE_OFFSET_RE.search(content)
    if not m:
        logger.warning(
            f"${{date_offset}} not defined in {robot_path}; defaulting offset to 0"
        )
        return 0
    offset = int(m.group(1))
    logger.info(f"date_offset parsed from {os.path.basename(robot_path)}: {offset}")
    return offset


def get_job_log_path(job_id):
    return f"{LOGS_DIR}/job_{job_id}.log"


def write_job_log(job_id, message):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    with open(get_job_log_path(job_id), "a") as f:
        f.write(line)
    logger.info(f"[Job {job_id}] {message}")


def run_robot(job_id, cmd, cwd=WORKDIR):
    """Run robot in a background thread."""
    jobs[job_id]["status"]     = "running"
    jobs[job_id]["started_at"] = datetime.utcnow().isoformat()

    write_job_log(job_id, "▶ Starting robot execution")
    write_job_log(job_id, f"Command: {' '.join(cmd)}")
    write_job_log(job_id, f"Working dir: {cwd}")
    write_job_log(job_id, "-" * 50)

    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in process.stdout:
            write_job_log(job_id, line.rstrip())

        process.wait(timeout=ROBOT_TIMEOUT_SECONDS)
        exit_code = process.returncode

        write_job_log(job_id, "-" * 50)
        write_job_log(job_id, f"Exit code: {exit_code}")

        if exit_code == 0:
            jobs[job_id]["status"] = "success"
            write_job_log(job_id, "✅ Robot execution PASSED")
        else:
            jobs[job_id]["status"] = "failed"
            write_job_log(job_id, "❌ Robot execution FAILED")

        jobs[job_id]["exit_code"]   = exit_code
        jobs[job_id]["finished_at"] = datetime.utcnow().isoformat()

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"]      = "timeout"
        jobs[job_id]["finished_at"] = datetime.utcnow().isoformat()
        write_job_log(job_id, f"⏰ Job TIMED OUT after {ROBOT_TIMEOUT_SECONDS} seconds")

    except Exception as e:
        jobs[job_id]["status"]      = "error"
        jobs[job_id]["error"]       = str(e)
        jobs[job_id]["finished_at"] = datetime.utcnow().isoformat()
        write_job_log(job_id, f"💥 Unexpected error: {e}")


# ── ENDPOINTS ──────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    running = len([j for j in jobs.values() if j["status"] == "running"])
    return jsonify({
        "status":      "ok",
        "message":     "NOVA AlphaBot API is running",
        "active_jobs": running,
        "total_jobs":  len(jobs),
        "logs_dir":    LOGS_DIR
    })


@app.route("/trigger/test", methods=["POST"])
def trigger_test():
    """Phase 1 test — runs test_nova_connection.robot."""
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id":      job_id,
        "type":        "test",
        "status":      "queued",
        "created_at":  datetime.utcnow().isoformat(),
        "started_at":  None,
        "finished_at": None,
        "exit_code":   None
    }

    write_job_log(job_id, "Job created — type: test")
    cmd    = [ROBOT_CMD, TEST_ROBOT]
    thread = threading.Thread(target=run_robot, args=(job_id, cmd))
    thread.daemon = True
    thread.start()

    return jsonify({
        "job_id":   job_id,
        "status":   "queued",
        "message":  "Test robot triggered.",
        "poll_url": f"/status/{job_id}",
        "logs_url": f"/logs/{job_id}"
    }), 202


@app.route("/trigger/<supplier_key>", methods=["POST"])
def trigger_supplier(supplier_key):
    """Generic supplier trigger — reads config from suppliers.json."""

    # Load supplier config
    suppliers = load_suppliers()
    if supplier_key not in suppliers:
        return jsonify({
            "error": f"Supplier '{supplier_key}' not found in config",
            "available": list(suppliers.keys())
        }), 404

    supplier = suppliers[supplier_key]

    # Get dates
    start_date = request.form.get("start_date")
    end_date   = request.form.get("end_date")

    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date are required"}), 400

    # Handle file upload
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Decide where to save the uploaded file.
    #
    # If the supplier has `download_path_template` in suppliers.json
    # (e.g. Gmail-download suppliers like airindia_express, flydubai,
    # belair_*, etc.), save the file directly into the path the
    # robot's "Download the report from Gmail" keyword would have
    # written to. The keyword is skipped via --prerunmodifier; the
    # file already being there means the rest of the robot flow
    # ("Get the dates from the report downloaded", BQ upload,
    # excel processing, summary generation) finds the input where
    # it expects.
    #
    # `{date}` is the only template placeholder; resolved to today's
    # date in DD-MM-YYYY format (matching the robot's ${DateForToday}).
    #
    # Suppliers without the field (web-portal automations, the special
    # atlas_lc which uses ~/Downloads, etc.) fall back to the
    # historical /config/Downloads/ path — backward compatible.
    template = supplier.get("download_path_template")
    if template:
        # The robot computes its date folder as `Get Current Date` (LOCAL
        # server time) shifted by ${date_offset} days. nova_api must land the
        # uploaded file in that SAME folder, or the robot's
        # "Placing the file in its path" step lists an empty directory and
        # crashes on ${req}[0] (IndexError). We read the offset dynamically
        # from the robot file itself (single source of truth — no drift) and
        # use datetime.now() (NOT utcnow) to match the robot's local clock.
        offset      = get_date_offset(supplier)
        folder_date = (datetime.now() + timedelta(days=offset)).strftime("%d-%m-%Y")
        save_dir    = template.format(date=folder_date)
    else:
        save_dir = "/config/Downloads"

    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, file.filename)
    file.save(file_path)

    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id":      job_id,
        "type":        supplier_key,
        "supplier":    supplier["name"],
        "status":      "queued",
        "created_at":  datetime.utcnow().isoformat(),
        "started_at":  None,
        "finished_at": None,
        "exit_code":   None
    }

    write_job_log(job_id, f"Job created — supplier: {supplier['name']}")
    write_job_log(job_id, f"File saved: {file_path}")
    if template:
        write_job_log(job_id, f"Download path template: {template} → {save_dir}")
    write_job_log(job_id, f"Start date: {start_date} | End date: {end_date}")
    write_job_log(job_id, f"Robot: {supplier['robot_path']}")
    write_job_log(job_id, f"Skipping keywords: {supplier['skip_tests']}")

    # Build robot command. The list under "skip_tests" in suppliers.json is
    # actually a list of KEYWORD CALL names inside the supplier's single test
    # case (e.g. "Download the report from the web portal"), not test case
    # names. Robot's --skip only matches test names, so we use a pre-run
    # modifier that removes the keyword calls in memory before execution.
    # The .robot file on disk is untouched, so the existing scheduled job
    # still runs the full flow.
    cmd = [ROBOT_CMD]

    skip_kws = supplier.get("skip_tests") or []
    if skip_kws:
        # Each colon-separated arg after the module path is one keyword name.
        # Spaces are fine; Robot's argv handling preserves them.
        modifier_arg = SKIP_KW_MODULE + ":" + ":".join(skip_kws)
        cmd += ["--prerunmodifier", modifier_arg]

    # Add variables
    cmd += ["--variable", f"start_date:{start_date}"]
    cmd += ["--variable", f"end_date:{end_date}"]

    # Add robot path
    cmd.append(supplier["robot_path"])

    thread = threading.Thread(target=run_robot, args=(job_id, cmd))
    thread.daemon = True
    thread.start()

    logger.info(f"{supplier['name']} job {job_id} queued")
    return jsonify({
        "job_id":    job_id,
        "status":    "queued",
        "supplier":  supplier["name"],
        "message":   f"{supplier['name']} robot triggered. Poll /status/{job_id} to check.",
        "poll_url":  f"/status/{job_id}",
        "logs_url":  f"/logs/{job_id}"
    }), 202


@app.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": f"Job {job_id} not found"}), 404
    job = jobs[job_id]
    return jsonify({
        "job_id":      job["job_id"],
        "type":        job["type"],
        "status":      job["status"],
        "created_at":  job["created_at"],
        "started_at":  job["started_at"],
        "finished_at": job["finished_at"],
        "exit_code":   job.get("exit_code"),
        "logs_url":    f"/logs/{job_id}"
    })


@app.route("/logs/<job_id>", methods=["GET"])
def get_logs(job_id):
    if job_id not in jobs:
        return jsonify({"error": f"Job {job_id} not found"}), 404

    log_path = get_job_log_path(job_id)
    if not os.path.exists(log_path):
        return jsonify({"job_id": job_id, "logs": "No logs yet"}), 200

    with open(log_path, "r") as f:
        content = f.read()

    return jsonify({
        "job_id":   job_id,
        "status":   jobs[job_id]["status"],
        "log_file": log_path,
        "logs":     content
    })


@app.route("/jobs", methods=["GET"])
def list_jobs():
    return jsonify({
        "total": len(jobs),
        "jobs": [
            {
                "job_id":      j["job_id"],
                "type":        j["type"],
                "status":      j["status"],
                "created_at":  j["created_at"],
                "finished_at": j.get("finished_at")
            }
            for j in sorted(jobs.values(), key=lambda x: x["created_at"], reverse=True)
        ]
    })


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("NOVA AlphaBot API starting on port 3002")
    logger.info(f"Base dir       : {BASE_DIR}")
    logger.info(f"Logs dir       : {LOGS_DIR}")
    logger.info(f"Suppliers cfg  : {SUPPLIERS_CFG}")
    logger.info(f"Robot timeout  : {ROBOT_TIMEOUT_SECONDS}s")
    logger.info("=" * 50)
    app.run(host="0.0.0.0", port=3002, debug=False)