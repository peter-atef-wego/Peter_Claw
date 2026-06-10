# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → [IP_ADDRESS], user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## GitHub

- **Username:** peter-atef-wego
- **Status:** ✅ Connected via PAT (stored locally, not in repo)

## Atlassian (Jira + Confluence)

- **Email:** [EMAIL]
- **Company Workspace:** WegoMushi
- **Jira URL:** https://wegomushi.atlassian.net
- **Jira Dashboard:** https://wegomushi.atlassian.net/jira/for-you
- **Confluence URL:** https://wegomushi.atlassian.net/wiki
- **API Token:** (stored securely in environment, not in repo)
- **Status:** ✅ API token configured

To use with Jira/Confluence REST APIs:
```bash
export ATLASSIAN_API_TOKEN=***
export JIRA_EMAIL=***
export JIRA_URL="https://wegomushi.atlassian.net"
export CONFLUENCE_URL="https://wegomushi.atlassian.net/wiki"
```

Endpoints:
- Jira: `https://wegomushi.atlassian.net/rest/api/3/`
- Confluence: `https://wegomushi.atlassian.net/wiki/api/v2/`

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Related

- [Agent workspace](/concepts/agent-workspace)
