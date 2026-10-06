---
name: team-ops
triggers: [team, ayush, likith, peter, akansha, assign, capacity, onboarding]
load: always
version: 1.0
---

# Team Ops Skill

## Purpose
This skill manages team capacity, task assignment, blocker tracking, and Akansha's onboarding progress. It provides the context needed to assign work correctly — accounting for what each person is currently focused on and what blockers they're carrying.

---

## Team Quick Reference

| Name | Location | Current Focus | Blockers | Available Capacity |
|---|---|---|---|---|
| Ayush Raj | Bangalore | Hotels ops, HCN pipelines, training Akansha | None known | Medium (training overhead) |
| Likith | Bangalore | Bel Air GDS dev, finance automations, supplier recos | None known | Medium-High |
| Peter Atef | Cairo | HR Contract Renewal (deploy pending), Offline Disputes | **BLOCKED: Offline Disputes credentials from Kero** | Low-Medium |
| Akansha | Bangalore | n8n/Any10 training with Ayush, NetSuite onboarding | Still ramping — limited independent capacity | Low (onboarding) |

---

## Assignment Rules

1. **Ayush**: Best for Hotels/HCN work, Airflow/BQ pipelines, AlphaBot builds. Currently has training overhead — don't overload.
2. **Likith**: Best for Finance automations, GDS, supplier work, n8n workflows. Highest independent capacity right now.
3. **Peter**: Cairo-based — best for HR automations, Cairo-specific escalations, and disputes work. Currently blocked on Offline Disputes; prioritise unblocking him.
4. **Akansha**: Assign learning tasks only. No production ownership until 2 live automations completed. NetSuite ownership transfer comes after April 2026 milestone.
5. **Unassigned tasks**: Route to Likith if Finance/GDS. Route to Ayush if Hotels/data. Route to Nikhil if strategic or cross-cutting.
6. **Cross-location work**: Bangalore ↔ Cairo async. Allow 24h response window for Peter on non-urgent items.

---

## Active Blockers to Track

| Person | Blocker | Since | Resolution Path |
|---|---|---|---|
| Peter | Offline Disputes credentials | Unknown — pre Apr 2026 | Kero (Payments) to provide. Nikhil to escalate if no movement by EOW. |
| Peter | HR Contract Renewal not yet deployed | Ready since ~Apr 2026 | Deploy to Marwa's system. Confirm date with Marwa/Peter. |
| Akansha | Limited NetSuite context | Ongoing | Li Ping coordinating handover. Ayush doing n8n training. |

---

## Akansha Onboarding Tracker

| Milestone | Target Date | Status | Owner |
|---|---|---|---|
| Start n8n/Any10 training | Week of Apr 7 2026 | In progress | Ayush |
| First n8n automation (live) | Apr 20 2026 | Not started | Akansha + Ayush |
| Second n8n automation (live) | Apr 30 2026 | Not started | Akansha + Ayush |
| NetSuite orientation with Li Ping | Apr 2026 | In progress | Li Ping + Akansha |
| NetSuite ownership transfer | May 2026 (tentative) | Not started | Li Ping coordinating |

**Note**: Target is 2 live automations by end of April 2026. Flag to Nikhil if Ayush has not logged a training session update by mid-April.

---

## Quick Commands

- `team status` — current focus, blockers, and capacity for all 4 members.
- `assign [task]` — recommend best assignee given current load.
- `check Peter blockers` — status on Offline Disputes and HR Contract Renewal.
- `akansha progress` — onboarding milestone status.
- `who is available for [X]` — capacity check for a specific task type.
- `update blocker [person] [status]` — log blocker resolution in action_tracker.md.
