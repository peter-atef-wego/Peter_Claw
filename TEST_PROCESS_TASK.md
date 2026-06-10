# Test Process - Task Documentation

## 📋 Corrected Workspace Information

**Company:** WegoMushi
**Jira URL:** https://wegomushi.atlassian.net/jira/for-you
**Confluence:** https://wegomushi.atlassian.net/wiki
**REST API Base:** https://wegomushi.atlassian.net/rest/api/3/

---

## Current Status

**Task:** Create Confluence page for "test process" Jira ticket
**Requested:** 2026-06-10 11:01 UTC
**Status:** 🔴 BLOCKED - API Authentication Issue

### Issue Encountered

The Jira API token authentication is not working with the current setup:

```
❌ Basic Auth Failed: "Client must be authenticated to access this resource"
❌ Bearer Token Failed: "Failed to parse Connect Session Auth Token"
```

This could mean:
1. API token format needs adjustment for this workspace
2. Confluence space/folder IDs need to be retrieved first
3. API token permissions may be limited to specific scopes

---

## ✅ What We Know

- ✅ Company workspace: **WegoMushi** (not personal)
- ✅ Jira accessible at: https://wegomushi.atlassian.net/jira/for-you
- ✅ Confluence accessible at: https://wegomushi.atlassian.net/wiki
- ✅ SSL connection verified ✓
- ❌ API authentication needs verification

---

## 🔄 Workflow (Once API Auth is Fixed)

### Step 1: Get List of All Issues to Find "test process"

```bash
curl -X GET \
  -H "Authorization: Bearer {API_TOKEN}" \
  "https://wegomushi.atlassian.net/rest/api/3/search?jql=summary~\"test process\""
```

**Expected to find:**
- Issue key (e.g., PROJ-123, DATA-456, etc.)
- Summary: "test process"
- Description: [Details about the process]
- Assignee: [Owner name]
- Status: [Current status]
- Labels/Tags: [Related tags]

### Step 2: Get Confluence Space & Folder IDs

```bash
# Get spaces
curl -X GET \
  -H "Authorization: Bearer {API_TOKEN}" \
  "https://wegomushi.atlassian.net/wiki/api/v2/spaces"

# Get folder structure
curl -X GET \
  -H "Authorization: Bearer {API_TOKEN}" \
  "https://wegomushi.atlassian.net/wiki/api/v2/spaces/{spaceId}/pages"
```

**Need to find:**
- Space ID for "Data, Marketing and Growth Homepage" (or equivalent)
- Folder ID for "AI & Automation 2026" (or equivalent)

### Step 3: Search Confluence for Existing Page

```bash
curl -X GET \
  -H "Authorization: Bearer {API_TOKEN}" \
  "https://wegomushi.atlassian.net/wiki/api/v2/pages?title=test%20process"
```

**Check:** Does "test process" page already exist?

### Step 4: Create Confluence Page from Jira Data

```bash
curl -X POST \
  -H "Authorization: Bearer {API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "spaceId": "{space_id}",
    "parentId": "{folder_id}",
    "title": "test process - AI/Automation Process",
    "body": {
      "representation": "storage",
      "value": "<h2>Business Summary</h2><p>[From Jira]</p>..."
    }
  }' \
  "https://wegomushi.atlassian.net/wiki/api/v2/pages"
```

### Step 5: Return Success

```
✅ Created: "test process - AI/Automation Process"
📄 Location: [Confluence workspace] → [Folder]
🔗 Jira Ticket: {ISSUE_KEY} (Link)
👤 Owner: [Owner from Jira]
⏱️ Status: [Status from Jira]
📝 Created: 2026-06-10 11:01 UTC
```

---

## 🔑 Prerequisites to Fix

### 1. Verify API Token Format
- Current: Bearer token format (`ATATT3...`) 
- May need: Different format for WegoMushi workspace
- Action: Check if token needs to be regenerated for this workspace

### 2. Find Confluence Space & Folder IDs
- Need: Get all spaces in this Confluence instance
- Find: "Data, Marketing and Growth Homepage" or equivalent name
- Get: Space ID and "AI & Automation 2026" folder page ID
- Store: As environment variables

### 3. Test API Connection
```bash
# Quick test
curl -X GET \
  -H "Authorization: Bearer {API_TOKEN}" \
  "https://wegomushi.atlassian.net/rest/api/3/myself"

# Should return: User info (name, email, etc.)
```

---

## 📝 Next Steps Required

**For You (Manual Steps):**

1. **Verify API Token**
   - Go to: https://id.atlassian.com/manage-profile/security/api-tokens
   - Check if token is valid for WegoMushi workspace
   - Regenerate if needed

2. **Get Confluence Details**
   - Open: https://wegomushi.atlassian.net/wiki
   - Navigate to target space (e.g., "Data, Marketing and Growth Homepage")
   - Create or find "AI & Automation 2026" folder
   - Extract Confluence Space ID and Folder Page ID from URLs
   - Share with agent for configuration

3. **Verify Jira Task Exists**
   - Open: https://wegomushi.atlassian.net/jira/for-you
   - Search for or create "test process" task
   - Verify it has sufficient details (summary, description, assignee)

**For Agent (Once Prerequisites Met):**

1. Test API authentication
2. Search for "test process" Jira ticket
3. Extract business + technical details
4. Create Confluence page in correct location
5. Return link to created page

---

## 🛠️ Configuration Needed

```bash
# Updated for WegoMushi workspace
export JIRA_URL="https://wegomushi.atlassian.net"
export JIRA_EMAIL="[EMAIL]"
export ATLASSIAN_API_TOKEN="***"
export CONFLUENCE_URL="https://wegomushi.atlassian.net/wiki"
export CONFLUENCE_SPACE_ID="???"  # Need to find
export AI_AUTOMATION_2026_FOLDER_ID="???"  # Need to find
```

---

## 📊 Current Blockers

| Blocker | Status | Action |
|---------|--------|--------|
| API Token Format | 🔴 Unknown | Verify/regenerate token |
| Confluence Space ID | 🔴 Unknown | Get from Confluence |
| AI Automation Folder ID | 🔴 Unknown | Get from Confluence |
| "test process" Jira Task | ❓ Unknown | Verify exists in Jira |

---

## 🔗 Files Updated

- `TOOLS.md` - Updated to WegoMushi workspace
- `TEST_PROCESS_TASK.md` - This file (you're reading it!)
- `MEMORY.md` - Pending update with correct workspace

---

## 📚 Related Documentation

- `JIRA_CONFLUENCE_WORKFLOW.md` - Complete workflow guide
- `JIRA_CONFLUENCE_QUICK_REF.md` - Quick reference
- `jira-confluence-documentation-sync` skill - Implementation
