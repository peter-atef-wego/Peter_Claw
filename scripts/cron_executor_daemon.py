#!/usr/bin/env python3
"""
Daemon wrapper for cron_executor.py
Runs the executor every 60 seconds to check and execute scheduled jobs.
"""

import subprocess
import logging
import time
import sys
from pathlib import Path

LOG_FILE = Path("/home/openclaw/.openclaw/workspace/logs/cron_executor_daemon.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("cron_executor_daemon")

EXECUTOR_SCRIPT = "/home/openclaw/.openclaw/workspace/scripts/cron_executor.py"
POLL_INTERVAL = 60  # Run every 60 seconds


def main():
    log.info("========== CRON EXECUTOR DAEMON STARTED ==========")
    log.info(f"Poll interval: {POLL_INTERVAL}s")
    log.info(f"Executor script: {EXECUTOR_SCRIPT}")
    
    iteration = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10
    
    while True:
        iteration += 1
        try:
            # Run the executor
            result = subprocess.run(
                ["/usr/bin/python3", EXECUTOR_SCRIPT],
                capture_output=True,
                text=True,
                timeout=55,  # Must complete in <60s
            )
            
            # Log output
            if result.stdout:
                log.debug(f"[Iter {iteration}] STDOUT:\n{result.stdout}")
            if result.stderr and result.returncode != 0:
                log.warning(f"[Iter {iteration}] STDERR:\n{result.stderr}")
            
            if result.returncode == 0:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                log.error(f"Executor returned non-zero ({result.returncode}). Error count: {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}")
                
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.critical(f"Too many consecutive errors ({consecutive_errors}). Exiting daemon.")
                    sys.exit(1)
        
        except subprocess.TimeoutExpired:
            log.error(f"[Iter {iteration}] Executor timed out (>55s). Skipping this cycle.")
            consecutive_errors += 1
        
        except Exception as e:
            log.error(f"[Iter {iteration}] Exception running executor: {e}")
            consecutive_errors += 1
        
        # Sleep until next poll
        log.debug(f"[Iter {iteration}] Sleeping for {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Daemon interrupted by user")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Unhandled exception in daemon: {e}")
        sys.exit(1)
