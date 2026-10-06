"""
model_router.py - openclaw-nova Smart 5-Level Model Router
Auto-escalation based on query complexity scoring.
Updated: 2026-04-14 per Nikhil Gupta instruction.
"""

from dataclasses import dataclass
from typing import Optional

# Updated 2026-08-11: Opus 4.7 retired. The old L5 (Opus 4.8) is now L4 and the old
# L6 (GPT-5.5) is now L5 — a 5-tier ladder. L4 inherits the retired tier's keyword
# routing and is the auto-escalation target from L3; L5 stays manual-only.
# Updated 2026-06-16: Haiku REMOVED. L1 is now Sonnet 4.6 (same model as L3); chip
# differentiation indicates SURFACE (DM vs channel), not model. Haiku was too
# unreliable for tier self-identification — Nikhil decision.
MODELS = {
    "l1":      "anthropic/claude-sonnet-4-6",
    "l2":      "openai/gpt-4o-mini",
    "l3":      "anthropic/claude-sonnet-4-6",
    "l4":      "anthropic/claude-opus-4-8",
    "l5":      "openai/gpt-5.5",
    "fallback": "openai/gpt-4o",
}

PROVIDER_FALLBACK = {
    "openai/gpt-4o-mini":                   "openai/gpt-4o",
    "anthropic/claude-sonnet-4-6":          "openai/gpt-4o",
    "anthropic/claude-opus-4-8":            "anthropic/claude-sonnet-4-6",
    "openai/gpt-5.5":                       "anthropic/claude-opus-4-8",
    "openai/gpt-4o":                        None,
}

L1_KEYWORDS = [
    "git pull", "git push", "git sync", "git mirror", "git commit",
    "run script", "run python", "execute script", "cron", "exit code",
    "extract json", "file copy", "nova_claw_pull", "fireflies_sync",
    "openclaw_nova_mirror",
]

L4_IMMEDIATE_KEYWORDS = [
    "architecture", "system design", "redesign", "strategic",
    "ceo report", "coo report", "exec report", "board prep",
    "weekly report", "intelligence briefing", "think hard",
    "deep dive", "most intelligent", "crisis", "p0 incident",
    "roadmap", "planning decision", "trade-off analysis",
    "cross-system design", "platform migration",
]

PIPELINE_TASKS = [
    "iax weekly report", "netsuite intelligence briefing",
    "automation health report", "ceo weekly", "exec weekly",
    "weekly strategic review",
]

COMPLEXITY_SIGNALS = {
    "error":           3,
    "traceback":       3,
    "stack trace":     3,
    "exception":       2,
    "n8n":             2,
    "netsuite":        2,
    "robot framework": 2,
    "bigquery":        2,
    "bq query":        2,
    "airflow":         2,
    "alphabot":        2,
    "build":           2,
    "debug":           2,
    "fix this":        2,
    "code review":     2,
    "workflow":        1,
    "integration":     1,
    "deploy":          1,
    "automate":        1,
}

L3_THRESHOLD = 4

# Channel floor: these channels always get at least L3 regardless of query complexity
CHANNEL_L3_FLOOR = {
    "C08N2T0CARE",  # netsuite_ap
    "C08N2SY3HFS",  # netsuite_ar
    "C08MCK3NJTX",  # netsuite_gl_and_reporting
    "C08MCK8936Z",  # netsuite_adminsupport
    "C08LZTG1YR5",  # netsuite_ota
    "C08T81REV6Y",  # alphabot-masters
}


@dataclass
class RouteResult:
    level: str
    model_id: str
    complexity_score: int = 0
    pipeline: bool = False
    stage1_model: Optional[str] = None
    stage2_model: Optional[str] = None
    rationale: str = ""
    auto_escalate_enabled: bool = True


def score_complexity(task: str) -> int:
    task_lower = task.lower()
    score = 0
    word_count = len(task.split())
    if word_count > 30:
        score += 1
    if word_count > 60:
        score += 1
    if "```" in task or "def " in task or "import " in task:
        score += 2
    for signal, points in COMPLEXITY_SIGNALS.items():
        if signal in task_lower:
            score += points
    tools = ["n8n", "netsuite", "airflow", "bigquery", "alphabot",
             "robot framework", "jira", "slack", "fireflies", "github"]
    tools_count = sum(1 for t in tools if t in task_lower)
    if tools_count >= 2:
        score += 2
    if tools_count >= 3:
        score += 2
    return score


def route(task_description: str, channel_id: str = None) -> RouteResult:
    """
    Route a query to the appropriate model level.

    Args:
        task_description: The query or task text.
        channel_id: Optional Slack channel ID. If the channel has a defined floor,
                    the result will never drop below that floor level.
    """
    task_lower = task_description.lower()

    for pt in PIPELINE_TASKS:
        if pt in task_lower:
            return RouteResult(
                level="l4_pipeline",
                model_id=MODELS["l4"],
                pipeline=True,
                stage1_model=MODELS["l3"],
                stage2_model=MODELS["l4"],
                rationale="2-stage pipeline: Sonnet for data, Opus 4.8 for narrative"
            )

    if any(kw in task_lower for kw in L4_IMMEDIATE_KEYWORDS):
        return RouteResult(
            level="l4_premium",
            model_id=MODELS["l4"],
            rationale="Immediate L4: premium signal keyword detected"
        )

    for kw in L1_KEYWORDS:
        if kw in task_lower:
            return RouteResult(
                level="l1_nano",
                model_id=MODELS["l1"],
                rationale=f"L1 mechanical: {kw}"
            )

    score = score_complexity(task_description)

    # Apply channel floor BEFORE scoring decision
    channel_floor_active = channel_id and channel_id in CHANNEL_L3_FLOOR

    if score >= L3_THRESHOLD or channel_floor_active:
        floor_note = " (channel floor)" if channel_floor_active and score < L3_THRESHOLD else ""
        return RouteResult(
            level="l3_standard",
            model_id=MODELS["l3"],
            complexity_score=score,
            auto_escalate_enabled=True,
            rationale=f"L3: complexity score {score}{floor_note}"
        )

    return RouteResult(
        level="l2_fast",
        model_id=MODELS["l2"],
        complexity_score=score,
        auto_escalate_enabled=True,
        rationale=f"L2: score {score} below threshold - generic query"
    )


def should_escalate_after_response(unknowns: int, systems: int, impact: str, confidence: str) -> bool:
    if unknowns >= 3:
        return True
    if systems >= 3:
        return True
    if impact == "high" and unknowns >= 1:
        return True
    if confidence in ("low", "uncertain"):
        return True
    return False


def get_fallback(model_id: str) -> Optional[str]:
    return PROVIDER_FALLBACK.get(model_id)


def get_cron_model(job_name: str) -> str:
    CRON_MAP = {
        "nova_claw_pull_sync":     MODELS["l1"],
        "fireflies_sync":          MODELS["l1"],
        "openclaw_nova_mirror":    MODELS["l1"],
        "fireflies_daily_digest":  MODELS["l2"],
        "jira_heartbeat":          MODELS["l2"],
        "slack_scan":              MODELS["l2"],
        "meeting_prep_briefing":   MODELS["l2"],
        "contact_doc_update":      MODELS["l3"],
        "evening_wrap":            MODELS["l3"],
        "decisions_extract":       MODELS["l3"],
        "iax_weekly_report":       MODELS["l4"],
        "crisis_report":           MODELS["l4"],
        "exec_weekly_report":      MODELS["l4"],
    }
    return CRON_MAP.get(job_name, MODELS["l3"])


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 model_router.py '<task>'")
        print("Cron:  python3 model_router.py --cron <job_name>")
        sys.exit(1)
    if sys.argv[1] == "--cron":
        job = sys.argv[2] if len(sys.argv) > 2 else ""
        print(f"Cron '{job}' -> {get_cron_model(job)}")
    else:
        task = " ".join(sys.argv[1:])
        r = route(task)
        print(f"Level:  {r.level}")
        print(f"Model:  {r.model_id}")
        if r.pipeline:
            print(f"Stage1: {r.stage1_model}")
            print(f"Stage2: {r.stage2_model}")
        print(f"Score:  {r.complexity_score}")
        print(f"Reason: {r.rationale}")
