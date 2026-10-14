---
name: "jira-confluence-documentation-sync"
description: "Sync Jira tickets to Confluence documentation pages with GitHub-aware updates for AI/Automation processes in Data, Marketing & Growth."
---

# Jira → Confluence → GitHub Documentation Sync Skill

## Overview

This skill automates the documentation lifecycle for AI & Automation processes:
1. **Search** Confluence for existing process documentation
2. **Create** new Confluence pages from Jira tickets (business + technical perspective)
3. **Update** documentation from GitHub commit history and diffs
4. **Sync** changes back to keep knowledge centralized

Triggered by user chat requests or Jira ticket-created events when the hosting environment delivers them.

## Hard Rules

1. **New Jira ticket → new Confluence page only after duplicate search.** When a new Jira ticket is the source, search Confluence by Jira key and summary before creating anything.
2. **Page title mirrors the Jira ticket.** Use the Jira summary as the page name, lightly normalized for readability, and include the Jira key for traceability. Recommended format: `<Jira summary> (<JIRA-KEY>)`.
3. **Initialize from Jira content.** The first page version must be grounded in the Jira ticket: summary, description, acceptance criteria, status, assignee, reporter, labels, priority, components, due date, links, and visible custom fields that describe scope. Unknown or empty fields become `TODO`, never invented content.
4. **Branch updates are diff-owned sections only.** When updating from branch changes, preserve Jira-originated/business sections and human edits. Replace only branch/diff-owned sections: Current Branch State, Difference From Base Branch, Technical Notes, Files Changed, Diff Summary, Risks / Review Notes, Testing Notes, Recent Updates.
5. **Branch update detail standard.** Branch updates must show current branch state, ahead/behind versus base, detailed explanation of changes, and a brief line for every changed file.

## Workflow Triggers

### Trigger 1: Create Confluence Page for Process or New Jira Ticket
**User Request:** "Create confluence page for process [X]"
**Jira Event:** new ticket created for an AI/Automation process

**Execution Flow:**
```
1. Search Confluence for existing page
   - Space: "Data, Marketing and Growth Homepage"
   - Folder: "AI & Automation 2026"
   - Query: Process name
   
2. If page exists → Return link, ask if user wants to update
   
3. If NOT found:
   a. Search Jira for matching ticket unless the trigger already includes a ticket
      - Search: project=* AND (summary~"[process]" OR description~"[process]")
      - Order: most recent first
   
   b. If Jira ticket found or provided by event:
      - Title the page from the Jira ticket: `<Jira summary> (<JIRA-KEY>)`
      - Extract useful ticket content: summary, description, acceptance criteria, labels, assignee, reporter, status, priority, components, due date, linked issues, attachments list, and scope-related custom fields
      - Create Confluence page initialized with:
        * Jira Ticket Snapshot
        * Business Summary (from Jira summary + description)
        * Objective / Scope
        * Acceptance Criteria
        * Technical Architecture / Implementation Notes
        * Data Flows
        * Dependencies
        * Owner, Reporter, Status, Priority, Labels
        * Jira Link
        * Branch / GitHub Updates placeholder
   
   c. If NO Jira ticket:
      - Ask user for process details
      - Create stub page for manual completion only if explicitly instructed
```

### Trigger 2: Update Confluence Documentation from GitHub
**User Request:** "Update confluence page [page name] from github"

**Execution Flow:**
```
1. Find Confluence page by Jira key, Jira summary/page title, process name, or stored branch metadata in "AI & Automation 2026" folder

2. Get current branch state and GitHub diff:
   - Resolve repo, branch, and base branch / PR target / default branch
   - Fetch head commit, latest commit date, ahead/behind counts
   - Compare base...branch
   - Parse commits and file diffs for:
     * New features/changes
     * Bug fixes
     * Performance improvements
     * Architecture updates
     * Config/schema/API changes
     * Risks and testing evidence

3. Update Confluence page:
   a. Preserve Jira-originated and human-written sections
   b. Replace or add only branch/diff-owned sections:
      - Current Branch State
      - Difference From Base Branch
      - Technical Notes
      - Files Changed
      - Diff Summary
      - Risks / Review Notes
      - Testing Notes
      - Recent Updates
   c. List every changed file briefly with status, additions/deletions, and one-line purpose

4. Add metadata:
   - Last synced: [timestamp]
   - Base branch: [base]
   - Branch: [branch]
   - Last commit: [commit hash + message]
```

## API Integration Details

### Confluence Search & Create

**Search for existing page:**
```bash
GET /wiki/api/v2/pages?spaceId={spaceId}&status=current&title={processName}
```

**Get Space ID for "Data, Marketing and Growth Homepage":**
```bash
GET /wiki/api/v2/spaces?keys=DATA_MARKETING_GROWTH
```

**Get folder structure:**
```bash
# If AI_AUTOMATION_2026_FOLDER_ID is a Confluence folder ID, prefer:
GET /wiki/api/v2/folders/{folderId}

# Legacy/page fallback when the parent is a page:
GET /wiki/api/v2/pages/{parentPageId}/children
```

**Create new page in "AI & Automation 2026" folder:**
```bash
POST /wiki/api/v2/pages
{
  "spaceId": "space_id",
  "parentId": "ai_automation_2026_folder_or_page_id",
  "title": "<Jira summary> (<JIRA-KEY>)",
  "body": {
    "representation": "storage",
    "value": "<page_content_html>"
  },
  "metadata": {
    "labels": [
      {"name": "ai-automation"},
      {"name": "process-2026"},
      {"name": "data-marketing-growth"}
    ]
  }
}
```

**Update existing page:**
```bash
PUT /wiki/api/v2/pages/{pageId}
{
  "title": "[Process Name] - AI/Automation Process",
  "body": {
    "representation": "storage",
    "value": "<updated_content_html>"
  },
  "version": {"number": current_version + 1}
}
```

### Jira Ticket Search

**Search for related Jira tickets:**
```bash
GET /rest/api/3/search?jql=summary~"{processName}" OR description~"{processName}"&orderBy=created DESC&maxResults=5
```

**Parse ticket content:**
```javascript
{
  "key": "PROJ-123",
  "summary": "Build AI process for X",
  "description": "...",
  "fields": {
    "customfield_*": "...",
    "assignee": {...},
    "labels": [...],
    "status": {...}
  }
}
```

### GitHub Integration

**Get recent commits for repo:**
```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/{owner}/{repo}/commits?per_page=50&author={filter}
```

**Get commit diff:**
```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/{owner}/{repo}/commits/{sha}
```

**Parse commit:**
```javascript
{
  "commit": {
    "message": "Feature: Add X capability",
    "author": {...},
    "committer": {...}
  },
  "files": [
    {
      "filename": "src/x.ts",
      "additions": 50,
      "deletions": 10,
      "patch": "..."
    }
  ]
}
```

## Page Template Structure

### New Page from Jira Ticket

Title format: `<Jira summary> (<JIRA-KEY>)`.

```html
<ac:structured-macro ac:name="panel">
  <ac:parameter ac:name="title">Jira Ticket Snapshot</ac:parameter>
  <ac:rich-text-body>
    <h2>Ticket Metadata</h2>
    <ul>
      <li>Jira Key: [JIRA-KEY linked to ticket]</li>
      <li>Status: [Jira status]</li>
      <li>Priority: [Jira priority or TODO]</li>
      <li>Assignee: [Jira assignee or TODO]</li>
      <li>Reporter: [Jira reporter or TODO]</li>
      <li>Labels / Components: [Jira labels/components or TODO]</li>
      <li>Due Date: [Jira due date or TODO]</li>
    </ul>

    <h2>Business Summary</h2>
    <p>[Extracted from Jira summary + description]</p>
    
    <h2>Objective</h2>
    <p>[Key business goal]</p>
    
    <h2>Technical Architecture</h2>
    <ul>
      <li>[From Jira acceptance criteria]</li>
      <li>[Key components]</li>
      <li>[Data flows]</li>
    </ul>
    
    <h2>Dependencies</h2>
    <ul>
      <li>[Systems/processes depended on]</li>
      <li>[Team dependencies]</li>
    </ul>
    
    <h2>Owner & Status</h2>
    <p>Owner: [From Jira assignee]</p>
    <p>Status: [From Jira status]</p>
    <p>Jira Ticket: [Link to PROJ-123]</p>

    <h2>Branch / GitHub Updates</h2>
    <p><em>No branch diff synced yet.</em></p>

    <h2>Recent Updates</h2>
    <p>Last updated: [timestamp]</p>
    <!-- GitHub branch diff updates inserted here without overwriting Jira-originated sections -->
  </ac:rich-text-body>
</ac:structured-macro>
```

### Update Section Template

```html
<h3>Update - [Date]</h3>
<p>
  <strong>GitHub Commit:</strong> 
  <a href="https://github.com/...">commit_hash</a>
</p>
<p><strong>Message:</strong> [Commit message]</p>
<p><strong>Changes:</strong></p>
<ul>
  <li>[File]: +[additions] -[deletions]</li>
  <li>[Key change from diff]</li>
</ul>
```

## Implementation Steps

### Step 1: Create Page from Jira Ticket

```typescript
async function createConfluencePageFromJira(processName: string) {
  // 1. Search Confluence for existing page
  const existingPage = await searchConfluencePage(processName);
  if (existingPage) {
    return { status: "exists", page: existingPage };
  }
  
  // 2. Search Jira for matching ticket
  const jiraTicket = await searchJiraTicket(processName);
  if (!jiraTicket) {
    return { status: "no_jira_ticket", message: "No matching Jira ticket found" };
  }
  
  // 3. Extract content from Jira
  const businessSummary = extractBusinessSummary(jiraTicket);
  const technicalDetails = extractTechnicalDetails(jiraTicket);
  
  // 4. Build Confluence page HTML
  const pageContent = buildPageTemplate(businessSummary, technicalDetails, jiraTicket);
  
  // 5. Create page in Confluence
  const newPage = await createConfluencePage({
    title: `${processName} - AI/Automation Process`,
    parentId: AI_AUTOMATION_2026_FOLDER_ID,
    body: pageContent,
    labels: ["ai-automation", "process-2026"]
  });
  
  return { status: "created", page: newPage };
}
```

### Step 2: Update Page from GitHub

```typescript
async function updateConfluencePageFromGithub(pageName: string) {
  // 1. Find Confluence page
  const page = await findConfluencePage(pageName);
  if (!page) {
    return { status: "not_found", message: `Page "${pageName}" not found` };
  }
  
  // 2. Get related GitHub commits
  const commits = await getRecentCommits({
    keywords: [pageName, extractKeywords(page)],
    limit: 10
  });
  
  // 3. Parse commits into update entries
  const updates = commits.map(commit => ({
    date: commit.commit.author.date,
    hash: commit.sha.substring(0, 7),
    message: commit.commit.message.split("\n")[0],
    files: commit.files.map(f => ({
      name: f.filename,
      additions: f.additions,
      deletions: f.deletions,
      keyChanges: extractKeyChanges(f.patch)
    }))
  }));
  
  // 4. Update Confluence page
  const updatedContent = insertGithubUpdates(page.body, updates);
  const result = await updateConfluencePage(page.id, {
    body: updatedContent,
    version: page.version + 1
  });
  
  return { status: "updated", page: result, updates_count: updates.length };
}
```

### Step 3: Helper Functions

```typescript
// Search Confluence page
async function searchConfluencePage(processName: string) {
  const response = await fetch(
    `${CONFLUENCE_URL}/wiki/api/v2/pages?spaceId=${SPACE_ID}&title=${encodeURIComponent(processName)}`,
    {
      headers: authHeader()
    }
  );
  const data = await response.json();
  return data.results?.[0];
}

// Search Jira ticket
async function searchJiraTicket(processName: string) {
  const jql = `summary~"${processName}" OR description~"${processName}"`;
  const response = await fetch(
    `${JIRA_URL}/rest/api/3/search?jql=${encodeURIComponent(jql)}&orderBy=created DESC&maxResults=5`,
    {
      headers: authHeader()
    }
  );
  const data = await response.json();
  return data.issues?.[0];
}

// Extract business summary from Jira
function extractBusinessSummary(ticket) {
  return {
    title: ticket.fields.summary,
    description: ticket.fields.description || "",
    objective: ticket.fields.customfield_business_objective || "",
    owner: ticket.fields.assignee?.displayName || "Unassigned",
    status: ticket.fields.status.name
  };
}

// Extract technical details from Jira
function extractTechnicalDetails(ticket) {
  return {
    acceptanceCriteria: ticket.fields.customfield_acceptance_criteria || "",
    technicalNotes: ticket.fields.customfield_technical_spec || "",
    dependencies: ticket.fields.issuelinks || [],
    labels: ticket.fields.labels || []
  };
}

// Get recent GitHub commits
async function getRecentCommits(options) {
  const response = await fetch(
    `${GITHUB_API}/repos/${REPO_OWNER}/${REPO_NAME}/commits?per_page=50`,
    {
      headers: {
        "Authorization": `token ${GITHUB_TOKEN}`,
        "Accept": "application/vnd.github.v3+json"
      }
    }
  );
  const commits = await response.json();
  
  // Filter by keywords
  return commits.filter(c => 
    options.keywords.some(k => 
      c.commit.message.toLowerCase().includes(k.toLowerCase())
    )
  ).slice(0, options.limit);
}

// Extract key changes from diff
function extractKeyChanges(patch) {
  const lines = patch.split("\n");
  return lines
    .filter(l => l.startsWith("+") || l.startsWith("-"))
    .filter(l => !l.startsWith("+++") && !l.startsWith("---"))
    .map(l => l.substring(1).trim())
    .filter(l => l.length > 0)
    .slice(0, 5); // Top 5 changes
}
```

## User Chat Commands

### Create Page
```
"Create confluence page for process [X]"
"Create confluence documentation for [X] automation process"
"Add AI process [X] to Confluence"
```

**Agent responds:**
- ✅ Page created with Jira data
- ℹ️ Page already exists (with link)
- ❌ No matching Jira ticket found

### Update Page
```
"Update confluence page [X] from github"
"Sync [X] process documentation with latest commits"
"Update documentation for [X] using recent changes"
```

**Agent responds:**
- ✅ Page updated with N new commits
- ℹ️ No new commits since last update
- ❌ Page not found

## Configuration

Store in environment:
```bash
export JIRA_URL="https://peter-atef.atlassian.net"
export JIRA_EMAIL="[EMAIL]"
export ATLASSIAN_API_TOKEN="***"

export CONFLUENCE_URL="https://peter-atef.atlassian.net/wiki"
export CONFLUENCE_SPACE_ID="DATA_MARKETING_GROWTH"
export AI_AUTOMATION_2026_FOLDER_ID="12345"

export GITHUB_TOKEN="***"
export GITHUB_REPO="owner/repo"
```

## Confluence Folder Setup (Manual - One Time)

1. In Confluence, navigate to "Data, Marketing and Growth Homepage"
2. Create folder: "AI & Automation 2026"
3. Get the page ID from URL: `/wiki/spaces/...?pageId=12345`
4. Store as `AI_AUTOMATION_2026_FOLDER_ID` in config

## Security & Error Handling

- ✅ API tokens stored in environment (not in code/repo)
- ✅ Validate page exists before updating
- ✅ Check version number before PUT (avoid conflicts)
- ✅ Graceful fallback if Jira/GitHub unavailable
- ✅ Log all operations for audit trail

## Related

- [Jira API Docs](https://developer.atlassian.com/cloud/jira/rest/v3/)
- [Confluence API Docs](https://developer.atlassian.com/cloud/confluence/rest/v2/)
- [GitHub API Docs](https://docs.github.com/en/rest)
- [Branch-based docs](../confluence-branch-docs/SKILL.md)
- [Workflow guide](../../docs/JIRA_CONFLUENCE_WORKFLOW.md)
