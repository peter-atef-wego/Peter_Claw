# Wego Slack Channel Map

Use this mapping to resolve channel name → ID, and to load the correct knowledge base doc when a query originates from that channel.

## Channel → ID → KB Doc

| Channel Name | Channel ID | Primary KB Doc(s) |
|---|---|---|
| alphabot-masters | C08T81REV6Y | `skills/automation-hub/SKILL.md` + `skills/wego-coding-automation-style/SKILL.md` |
| data-marketing-reports | C07EGK6JU8Y | `knowledge/company/wego-business.md` |
| netsuite_ota | C08LZTG1YR5 | `skills/wego-netsuite/knowledge_base/integrations.md` |
| netsuite_ar | C08N2SY3HFS | `skills/wego-netsuite/knowledge_base/ar_operations.md` |
| netsuite_gl_and_reporting | C08MCK3NJTX | `skills/wego-netsuite/knowledge_base/gl_reporting.md` |
| netsuite_ap | C08N2T0CARE | `skills/wego-netsuite/knowledge_base/ap_operations.md` |
| netsuite_adminsupport | C08MCK8936Z | `skills/wego-netsuite/knowledge_base/admin_config.md` |
| netsuite_learning_hub | C0AR2B27A3U | `skills/wego-netsuite/SKILL.md` (training, R&D, troubleshooting) |

## Usage Rules

1. When a query arrives with a source channel ID, look up the channel ID in this table first.
2. Load ONLY the KB doc(s) mapped to that channel — do not load the entire `wego-netsuite/SKILL.md` or all docs.
3. Load `wego-netsuite/SKILL.md` base config (account details, auth, subsidiaries) as a secondary reference only if the channel-specific doc does not answer the query.
4. If no channel ID is present in context, fall back to keyword-based loading (see MANIFEST.md).

## Escalation Fallback

If a query spans multiple channels (e.g., AP + AR issue), load both mapped docs rather than loading everything.
