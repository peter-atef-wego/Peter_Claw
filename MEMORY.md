# MEMORY.md - Long-Term Memory

## Jira-Confluence-GitHub Documentation Sync

### Setup Date: 2026-06-10

Created comprehensive skill to automate documentation lifecycle:

**Skill:** `jira-confluence-documentation-sync`
- Searches Confluence for existing process docs in "AI & Automation 2026" folder
- Creates pages from Jira tickets (business + technical perspective)
- Updates documentation from GitHub commit history and diffs
- Location: `~/.openclaw/workspace/skills/jira-confluence-documentation-sync/`

### How It Works

**Trigger 1: Create Confluence Page**
```
User: "Create confluence page for process [X]"
Flow:
1. Search Confluence for existing page
2. If not found → Search Jira for matching ticket
3. Extract business summary + technical details
4. Generate page with template (Process Overview, Architecture, Dependencies, Owner, Recent Updates)
5. Create in "AI & Automation 2026" folder
```

**Trigger 2: Update from GitHub**
```
User: "Update confluence page [X] from github"
Flow:
1. Find Confluence page
2. Fetch recent GitHub commits with related keywords
3. Extract changes from diffs
4. Insert as "Recent Updates" section in page
5. Update metadata (last synced timestamp)
```

### Configuration

**Credentials (in TOOLS.md, not committed):**
- Jira URL: https://peter-atef.atlassian.net
- Confluence URL: https://peter-atef.atlassian.net/wiki
- Space: "Data, Marketing and Growth Homepage"
- Folder: "AI & Automation 2026"
- API tokens stored in environment variables

**Manual Setup Needed:**
1. Get Confluence Space ID for "Data, Marketing and Growth Homepage"
2. Find/create folder "AI & Automation 2026" and get its page ID
3. Store folder ID in: `AI_AUTOMATION_2026_FOLDER_ID` env var

### Example Usage

```
"Create confluence page for customer segmentation process"
→ Searches Jira for matching ticket
→ Creates page with sections: Business Summary, Technical Architecture, Dependencies, Owner, Status
→ Returns link to created page

"Update confluence page customer segmentation from github"
→ Finds page
→ Gets recent commits
→ Adds update section with commit hash, message, changed files
→ Updates last sync timestamp
```

### Related Skills
- `jira-confluence-api` - REST API integration reference
- `github` - GitHub CLI integration
- `skill-creator` - For skill creation/modification

### Status
✅ Skill created and applied
⏳ Waiting for: Jira instance reactivation, Confluence folder ID setup

## Task Attempt: "test process" (2026-06-10 10:57 UTC)

**User Request:** Create Confluence page for "test process" Jira ticket

**Status:** 🔴 BLOCKED - Jira instance suspended (HTTP 503)

**What Would Happen (Once Jira Reactivated):**
1. Search Jira for "test process" ticket
2. Extract business summary + technical details
3. Create Confluence page in "AI & Automation 2026" folder
4. Return link to created page

**Blocker:** Jira instance deactivated due to inactivity
- Solution: Reactivate at https://www.atlassian.com/company/contact/purchasing-licensing
- Once active: Re-run "Create confluence page for test process"

**Documentation:** See `TEST_PROCESS_TASK.md` for full workflow that will execute
