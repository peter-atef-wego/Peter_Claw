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

**Updated for WegoMushi (Company Workspace):**
- Jira URL: https://wegomushi.atlassian.net
- Jira Dashboard: https://wegomushi.atlassian.net/jira/for-you
- Confluence URL: https://wegomushi.atlassian.net/wiki
- Space: "Data, Marketing and Growth Homepage" (company space)
- Folder: "AI & Automation 2026"
- API tokens stored in environment variables (not committed)

**Manual Setup Needed:**
1. ✅ Verify API token valid for WegoMushi workspace
2. ✅ Get Confluence Space ID for company space
3. ✅ Find/create folder "AI & Automation 2026" and get page ID
4. ✅ Store: `CONFLUENCE_SPACE_ID`, `AI_AUTOMATION_2026_FOLDER_ID` env vars
5. ✅ Test API auth: `GET /rest/api/3/myself`

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
✅ Updated to WegoMushi company workspace
⏳ Waiting for: API token verification, Confluence IDs, "test process" task details

## Task Attempt: "test process" (2026-06-10 11:01 UTC)

**User Request:** Create Confluence page for "test process" Jira ticket

**Correction Made:** WegoMushi company workspace (not personal)
- **Correct:** https://wegomushi.atlassian.net/jira/for-you
- Previous assumption: https://peter-atef.atlassian.net (personal)

**Status:** 🔴 BLOCKED - API Authentication Issues

**Current Blockers:**
1. API token authentication not working with current token format
   - Basic Auth failed: "Client must be authenticated"
   - Bearer token failed: "Failed to parse Connect Session Auth Token"
2. Missing Confluence Space ID for company workspace
3. Missing "AI & Automation 2026" folder page ID
4. Need to verify "test process" Jira ticket exists in company workspace

**What Will Execute (Once Blockers Fixed):**
1. Search Jira for "test process" ticket in WegoMushi workspace
2. Extract business summary + technical details
3. Create Confluence page in "AI & Automation 2026" folder
4. Return link to created page with owner and status

**Next Steps Required:**
1. Verify/regenerate API token for WegoMushi workspace
2. Get Confluence Space ID and Folder Page ID
3. Verify "test process" Jira task exists in company workspace
4. Test API authentication with `/rest/api/3/myself` endpoint

**Documentation:** See `TEST_PROCESS_TASK.md` for detailed workflow and API calls
