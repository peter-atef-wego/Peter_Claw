#!/usr/bin/env python3
"""
Smoke test — verify cron daemon fires on schedule.
Simply writes to a file to prove execution.
"""

import os
from datetime import datetime, timezone

timestamp = datetime.now(timezone.utc).isoformat()
msg = f"✅ CRON DAEMON SMOKE TEST PASSED at {timestamp}\n"

# Write proof
with open("/tmp/cron_daemon_smoke_test.txt", "w") as f:
    f.write(msg)

print(msg)
exit(0)
