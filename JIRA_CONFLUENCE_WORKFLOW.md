# Jira → Confluence → GitHub Documentation Sync Workflow

## 🎯 Overview

This workflow automates documentation management for AI & Automation processes by connecting three systems:
- **Jira:** Process requirements & tickets
- **Confluence:** Central documentation hub
- **GitHub:** Implementation tracking & version history

---

## 📋 Quick Start Guide

### Setup (One-Time)

1. **Get Confluence Folder ID:**
   ```bash
   # Navigate to Confluence "Data, Marketing and Growth Homepage" → "AI & Automation 2026"
   # URL will show: /wiki/spaces/...?pageId=12345
   # Store the pageId as: AI_AUTOMATION_2026_FOLDER_ID
   ```

2. **Store in environment:**
   ```bash
   export JIRA_URL="https://peter-atef.atlassian.net"
   export JIRA_EMAIL="[EMAIL]"
   export ATLASSIAN_API_TOKEN="***"
   export CONFLUENCE_SPACE_ID="DATA_MARKETING_GROWTH"
   export AI_AUTOMATION_2026_FOLDER_ID="12345"
   export GITHUB_TOKEN="***"
   export GITHUB_REPO="peter-atef-wego/my-repo"
   ```

---

## 🚀 Usage Scenarios

### Scenario 1: Create Documentation for New Process

**You:** "Create confluence page for customer segmentation AI process"

**Agent Flow:**
```
┌─────────────────────────┐
│ Search Confluence       │
│ For existing page       │
└──────────┬──────────────┘
           │
       NOT FOUND
           │
           ▼
┌─────────────────────────┐
│ Search Jira for         │
│ "customer segmentation" │
└──────────┬──────────────┘
           │
        FOUND
           │
           ▼
┌─────────────────────────┐
│ Extract from Jira:      │
│ • Summary               │
│ • Description           │
│ • Acceptance Criteria   │
│ • Assignee              │
│ • Labels                │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Build Confluence Page:  │
│ • Business Summary      │
│ • Technical Architecture│
│ • Dependencies          │
│ • Owner & Status        │
│ • Jira Link             │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Create in Confluence    │
│ "AI & Automation 2026"  │
└──────────┬──────────────┘
           │
           ▼
    ✅ Page Created
    Link: https://...
```

**Result:**
```
✅ Created: "Customer Segmentation AI Process"
📄 Location: Data, Marketing and Growth Homepage → AI & Automation 2026
🔗 Linked to Jira: PROJ-123
👤 Owner: [From Jira assignee]
```

---

### Scenario 2: Update Documentation from GitHub Changes

**You:** "Update confluence page customer segmentation from github"

**Agent Flow:**
```
┌─────────────────────────┐
│ Find Confluence Page    │
│ "customer segmentation" │
└──────────┬──────────────┘
           │
        FOUND
           │
           ▼
┌─────────────────────────┐
│ Search GitHub for:      │
│ • Recent commits        │
│ • Matching keywords     │
│ • Related diffs         │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Extract from each commit│
│ • Commit hash           │
│ • Commit message        │
│ • Files changed         │
│ • Lines added/removed   │
│ • Key changes (from diff)
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Format as "Updates"     │
│ section in Confluence   │
│ (newest first)          │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Update page with:       │
│ • New Updates section   │
│ • Last synced: [time]   │
│ • Last commit: [hash]   │
└──────────┬──────────────┘
           │
           ▼
    ✅ Page Updated
    N recent commits added
```

**Result:**
```
✅ Updated: "Customer Segmentation AI Process"
📝 Added 5 new commits:
   • abc1234 - Feature: Add data preprocessing
   • def5678 - Fix: Handle edge cases in segmentation
   • ghi9012 - Perf: Optimize clustering algorithm
   • jkl3456 - Docs: Update technical specs
   • mno7890 - Refactor: Clean up deprecated code

⏱️ Last synced: 2026-06-10 10:52 UTC
🔗 Latest commit: https://github.com/.../commit/abc1234
```

---

### Scenario 3: Page Already Exists

**You:** "Create confluence page for customer segmentation AI process"

**Agent Response:**
```
ℹ️ Page already exists: "Customer Segmentation AI Process"
📄 Location: Data, Marketing and Growth Homepage → AI & Automation 2026
🔗 View: https://peter-atef.atlassian.net/wiki/spaces/...
⏱️ Last updated: 2026-06-09 15:30 UTC

Would you like me to:
1. Update it with recent GitHub commits?
2. Check for changes in the Jira ticket?
3. Create a new version with different naming?
```

---

## 📊 Page Structure

### Created Confluence Page Layout

```
┌─────────────────────────────────────────┐
│ Customer Segmentation AI - AI/Automation│
│                          Process         │
├─────────────────────────────────────────┤
│                                         │
│ 📌 Process Overview                     │
│ ├─ Business Summary                     │
│ │  "Build AI system to segment         │
│ │   customers by behavior patterns"    │
│ └─                                      │
│                                         │
│ 🎯 Objective                            │
│ └─ Key business goal                    │
│                                         │
│ 🏗️ Technical Architecture                │
│ ├─ Component 1: Data Ingestion          │
│ ├─ Component 2: ML Pipeline             │
│ ├─ Component 3: Segment API             │
│ └─ Data flows & integration points      │
│                                         │
│ 🔗 Dependencies                         │
│ ├─ Data warehouse (Snowflake)           │
│ ├─ ML infrastructure (MLflow)           │
│ ├─ API gateway (Kong)                   │
│ └─ Team: Data Science, Engineering      │
│                                         │
│ 👤 Owner & Status                       │
│ ├─ Owner: [Name from Jira]              │
│ ├─ Status: In Progress                  │
│ └─ Jira Ticket: PROJ-123 [Link]         │
│                                         │
│ 📝 Recent Updates                       │
│ ├─ [2026-06-10] abc1234: Feature...     │
│ ├─ [2026-06-09] def5678: Fix...         │
│ └─ [2026-06-08] ghi9012: Perf...        │
│                                         │
│ Last synced: 2026-06-10 10:52 UTC       │
└─────────────────────────────────────────┘
```

---

## 🔄 Workflow States

### Page Creation Flow

```
START
  ↓
User Request: "Create page for [process]"
  ↓
Search Confluence
  ├─ Page exists? → FOUND (return link)
  └─ Page missing? → continue
  ↓
Search Jira
  ├─ Ticket found? → EXTRACT DATA
  └─ No ticket? → ASK USER (stub page)
  ↓
EXTRACT DATA from Jira
  ├─ Business summary
  ├─ Technical details
  ├─ Acceptance criteria
  └─ Owner & status
  ↓
BUILD PAGE TEMPLATE
  ├─ Format: HTML storage format
  ├─ Add: Jira ticket link
  └─ Add: Labels (ai-automation, process-2026)
  ↓
CREATE in Confluence
  ├─ Space: Data, Marketing and Growth
  ├─ Folder: AI & Automation 2026
  └─ Parent ID: [folder ID]
  ↓
SUCCESS
  └─ Return page link + metadata
```

### Page Update Flow

```
START
  ↓
User Request: "Update page [name] from github"
  ↓
FIND PAGE in Confluence
  ├─ Page found? → GET PAGE DATA
  └─ Not found? → ERROR (suggest create)
  ↓
GET PAGE DATA
  ├─ Current version
  ├─ Current content
  └─ Last sync timestamp
  ↓
FETCH GitHub commits
  ├─ Filter by keywords
  ├─ Get diffs
  └─ Extract changes
  ↓
BUILD UPDATES SECTION
  ├─ For each commit:
  │  ├─ Date
  │  ├─ Commit hash + link
  │  ├─ Message
  │  ├─ Files changed
  │  └─ Key changes
  └─ Order: newest first
  ↓
UPDATE PAGE
  ├─ Insert updates at top
  ├─ Update version number
  ├─ Set last sync time
  └─ Preserve existing content
  ↓
SUCCESS
  └─ Return update summary (N commits added)
```

---

## 🛠️ Command Reference

### Chat Commands to Agent

```bash
# Create new documentation page
"Create confluence page for [process name]"
"Generate Confluence doc for [process]"
"Add [process] to AI & Automation 2026"

# Update existing page
"Update confluence page [process name] from github"
"Sync [process name] documentation"
"Update [process] docs with latest changes"

# Check status
"Show confluence page [process name]"
"List pages in AI & Automation 2026"
```

---

## ⚙️ Technical Details

### API Calls Made

**Create Page Flow:**
1. `GET /wiki/api/v2/pages` - Search Confluence
2. `GET /rest/api/3/search` - Search Jira
3. `POST /wiki/api/v2/pages` - Create page

**Update Page Flow:**
1. `GET /wiki/api/v2/pages` - Find page
2. `GET /repos/{owner}/{repo}/commits` - GitHub commits
3. `GET /repos/{owner}/{repo}/commits/{sha}` - Commit details
4. `PUT /wiki/api/v2/pages/{id}` - Update page

### Authentication

```bash
# Jira & Confluence (Basic Auth)
Authorization: Basic base64(email:api_token)

# GitHub
Authorization: token {GITHUB_TOKEN}
```

---

## 📋 Checklist: First Time Setup

- [ ] 1. Create Jira Cloud API token
  - [ ] Go to https://id.atlassian.com/manage-profile/security/api-tokens
  - [ ] Create token, save it safely

- [ ] 2. Reactivate Jira instance (currently suspended)
  - [ ] Contact Atlassian support if needed
  - [ ] Verify access after reactivation

- [ ] 3. Find Confluence folder ID
  - [ ] Navigate to "Data, Marketing and Growth Homepage"
  - [ ] Create or find "AI & Automation 2026" folder
  - [ ] Extract page ID from URL
  - [ ] Store as `AI_AUTOMATION_2026_FOLDER_ID`

- [ ] 4. Set environment variables
  - [ ] `JIRA_URL`, `JIRA_EMAIL`, `ATLASSIAN_API_TOKEN`
  - [ ] `CONFLUENCE_SPACE_ID`, `AI_AUTOMATION_2026_FOLDER_ID`
  - [ ] `GITHUB_TOKEN`, `GITHUB_REPO`

- [ ] 5. Test workflows
  - [ ] Create a test page
  - [ ] Update with GitHub commits
  - [ ] Verify page formatting

---

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Page not found" | Use exact process name, check spelling |
| "No Jira ticket found" | Create Jira ticket first with process name |
| "Authentication failed" | Verify API tokens in environment |
| "Jira instance suspended" | Contact Atlassian to reactivate |
| "Confluence folder not found" | Verify `AI_AUTOMATION_2026_FOLDER_ID` |
| "No recent commits" | GitHub repo may not have matching commits |

---

## 📚 Related Documentation

- Jira Confluence API Skill: `~/.openclaw/workspace/skills/jira-confluence-api/`
- GitHub Skill: `~/.openclaw/skills/github/`
- Skill Workshop: `skill_workshop` tool
- TOOLS.md: Local configuration (not in repo)
- MEMORY.md: This project's memory log

---

## 💡 Future Enhancements

- [ ] Auto-create Jira tickets from Confluence discussions
- [ ] Webhook triggers for automatic syncing
- [ ] Page templates per process type
- [ ] Change notifications to Slack
- [ ] Historical version tracking (commit log)
- [ ] Integration with Linear or other project tools
