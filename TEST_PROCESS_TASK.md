# Test Process - Task Documentation

## Status: ⏳ Waiting for Jira Reactivation

### Issue Encountered
**Jira Instance Status:** 🔴 SUSPENDED (HTTP 503)
- Current: Instance is deactivated due to inactivity
- Expected to be reactivated soon
- Once reactivated, this workflow will execute

---

## 📋 Task Details

**Jira Ticket:** "test process" (pending creation/discovery)
**Requested Action:** Create Confluence page for "test process"
**Target Confluence:** Data, Marketing and Growth Homepage → AI & Automation 2026

---

## 🔄 Workflow That Will Execute (Once Jira is Active)

### Step 1: Search Jira for "test process"

```bash
GET https://peter-atef.atlassian.net/rest/api/3/search
?jql=summary~"test process" OR description~"test process"
&orderBy=created DESC
&maxResults=5
```

**Expected Response:** Jira ticket details including:
- `fields.summary` → Business summary
- `fields.description` → Objective
- `fields.customfield_*` → Technical details
- `fields.assignee` → Owner
- `fields.status` → Current status
- `fields.labels` → Tags

### Step 2: Search Confluence for Existing Page

```bash
GET https://peter-atef.atlassian.net/wiki/api/v2/pages
?spaceId=DATA_MARKETING_GROWTH
&title=test process
```

**Expected:** Check if "test process" page already exists

### Step 3: Extract Data from Jira

**Business Perspective:**
- Summary: [From Jira summary field]
- Objective: [From Jira description]
- Owner: [From Jira assignee]
- Status: [From Jira status]

**Technical Perspective:**
- Acceptance Criteria: [From custom fields]
- Technical Specification: [From technical notes field]
- Dependencies: [From linked issues]
- Architecture: [From technical details]

### Step 4: Create Confluence Page

**Page Structure:**

```html
<ac:structured-macro ac:name="panel">
  <ac:parameter ac:name="title">Test Process - AI/Automation Process</ac:parameter>
  <ac:rich-text-body>
    
    <h2>Process Overview</h2>
    <p>[Business summary from Jira]</p>
    
    <h2>Objective</h2>
    <p>[Key business goal]</p>
    
    <h2>Technical Architecture</h2>
    <ul>
      <li>[Component 1]</li>
      <li>[Component 2]</li>
    </ul>
    
    <h2>Dependencies</h2>
    <ul>
      <li>[System dependencies]</li>
      <li>[Team dependencies]</li>
    </ul>
    
    <h2>Owner & Status</h2>
    <p>Owner: [From Jira assignee]</p>
    <p>Status: [From Jira status]</p>
    <p>Jira Ticket: [Link to ticket]</p>
    
    <h2>Recent Updates</h2>
    <p>Page created: [timestamp]</p>
    <!-- GitHub commits will be added here during updates -->
    
  </ac:rich-text-body>
</ac:structured-macro>
```

**API Call:**
```bash
POST https://peter-atef.atlassian.net/wiki/api/v2/pages
{
  "spaceId": "DATA_MARKETING_GROWTH",
  "parentId": "AI_AUTOMATION_2026_FOLDER_ID",
  "title": "test process - AI/Automation Process",
  "body": {
    "representation": "storage",
    "value": "[html content above]"
  },
  "metadata": {
    "labels": [
      {"name": "ai-automation"},
      {"name": "process-2026"},
      {"name": "test"}
    ]
  }
}
```

### Step 5: Return Result

**Success Response:**
```
✅ Created: "test process - AI/Automation Process"
📄 Location: Data, Marketing and Growth Homepage → AI & Automation 2026
🔗 Jira Ticket: [Link to JIRA ticket]
👤 Owner: [Owner name]
⏱️ Status: [Current status]
📝 Page created: [timestamp]

You can now update this page using:
"Update confluence page test process from github"
```

---

## 🔑 Prerequisites for Execution

- [ ] ✅ Jira instance reactivated (SUSPENDED → ACTIVE)
- [ ] ✅ Confluence folder ID found: `AI_AUTOMATION_2026_FOLDER_ID=12345`
- [ ] ✅ API tokens configured:
  - `ATLASSIAN_API_TOKEN` (provided ✓)
  - `JIRA_EMAIL` (set ✓)
  - `JIRA_URL` (set ✓)
- [ ] ✅ Jira ticket "test process" exists or will be created

---

## 📊 What We Know About "test process"

**Source:** Your chat request at 2026-06-10 10:57 UTC
**Description:** "test process" - a new task/ticket for testing the workflow
**Action:** Initialize Confluence documentation page
**Destination:** AI & Automation 2026 folder in Confluence

---

## 🔄 Next Steps

### Immediate (You)
1. Reactivate Jira instance at: https://www.atlassian.com/company/contact/purchasing-licensing
2. Find "test process" Jira ticket (or create it if it doesn't exist)
3. Note the ticket key (e.g., PROJ-123)

### Once Jira is Active (Agent)
1. Run skill: `jira-confluence-documentation-sync`
2. Search for "test process" Jira ticket
3. Extract business + technical details
4. Create Confluence page in "AI & Automation 2026"
5. Return link to newly created page

### After Page Creation (You)
1. Review page in Confluence
2. Verify details are correct
3. Update with: "Update confluence page test process from github"
4. Page will sync with latest GitHub commits

---

## 💾 Task State

**Created:** 2026-06-10 10:57 UTC
**Status:** ⏳ PENDING (Jira suspension)
**Blocker:** Jira instance is suspended (503 Service Unavailable)
**Owner:** Agent (Peter_Claw)
**Action Items:** 
- [ ] Reactivate Jira
- [ ] Verify "test process" ticket exists
- [ ] Re-run: "Create confluence page for test process"
- [ ] Verify page created in Confluence
- [ ] Test update workflow with GitHub

---

## 📝 Skill Used

**Skill:** `jira-confluence-documentation-sync`
**Trigger:** User chat request - "test process on JIRA initialize a confluence page"
**Expected Behavior:** 
1. Search Jira for "test process"
2. Extract details
3. Create Confluence page
4. Return link

**Documentation:** See `JIRA_CONFLUENCE_WORKFLOW.md` for full details

---

## 🔗 Related

- `JIRA_CONFLUENCE_WORKFLOW.md` - Complete workflow documentation
- `JIRA_CONFLUENCE_QUICK_REF.md` - Quick reference guide
- `MEMORY.md` - Skill setup notes
- `jira-confluence-api` skill - REST API integration

---

## 📌 Summary

When Jira is back online, execute:
```
"Create confluence page for test process"
```

This will automatically:
- ✅ Find the "test process" Jira ticket
- ✅ Extract business + technical details
- ✅ Create a formatted Confluence page
- ✅ Place it in "AI & Automation 2026" folder
- ✅ Return the page link

**Current Blocker:** Jira instance suspended 🔴
**Action:** Reactivate Jira instance ➜ Then re-run request
