---
name: itops
description: Internal IT operations automation and support practices. Use for monitoring, incident response workflows, access management, and infrastructure automation guidance.
---

# IT Ops

This skill covers internal IT operations automation, reliability patterns, and incident workflows relevant to Wego’s automation environment.

## 1) Monitoring & alerting

- Define clear SLOs (availability, latency, error rate).
- Monitor upstream dependencies (APIs, DBs).
- Alerts must be actionable (include owner, impact, and next step).

## 2) Incident response

- Triage quickly: scope, severity, blast radius.
- Use runbooks with step‑by‑step actions.
- Keep a post‑incident review log (root cause + prevention).

## 3) Access management

- Follow least‑privilege principle.
- Use approval workflows for access changes.
- Audit access regularly.

## 4) Automation hygiene

- Prefer idempotent scripts and clear rollback paths.
- Use versioned configs and infrastructure as code when possible.
- Log all automation actions for traceability.

## 5) Change management

- Announce changes with impact and rollback plan.
- Avoid deploying risky changes during peak hours.
- Validate changes in staging before production.

## 6) Reliability patterns

- Retry with exponential backoff for transient failures.
- Fail safe: better to stop than silently corrupt.
- Use health checks for critical services.

## 7) Security baseline

- Patch regularly.
- Rotate secrets.
- Centralize audit logs.

## Official references

- Google SRE Book: https://sre.google/sre-book/
- NIST IT operations guidance: https://www.nist.gov/
- OWASP operations guidance: https://owasp.org/
