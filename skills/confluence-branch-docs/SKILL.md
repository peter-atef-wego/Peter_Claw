---
name: confluence-branch-docs
description: Create or update Confluence documentation from Git branch activity. Use when a new GitHub/Git branch is created and a matching Confluence page should be created, or when a Confluence page should be updated using the diff of a specific branch against its base branch.
---

# Confluence Branch Docs

Use this skill to keep Confluence documentation synchronized with Git branch work.

## Required Inputs

Before acting, identify:

- Repository name or local repo path
- Branch name
- Base branch, usually `main`, `master`, or the PR target branch
- Confluence parent page or folder ID
- Confluence page title pattern
- Whether the task is:
  - `create` page for a newly created branch
  - `update` page using a branch diff

## Required Environment

Expect these values from environment variables, config, or user-provided context:

```bash
CONFLUENCE_URL="https://example.atlassian.net/wiki"
CONFLUENCE_SPACE_ID="..."
CONFLUENCE_PARENT_PAGE_ID="..."
ATLASSIAN_EMAIL="..."
ATLASSIAN_API_TOKEN="***"
```

For GitHub-backed repositories, also use:

```bash
GITHUB_REPOSITORY="owner/repo"
GITHUB_TOKEN="***"
```

Never print tokens.

## Branch Name Handling

Normalize the branch name into readable documentation metadata.

Examples:

```text
feature/customer-segmentation-v2
→ Customer Segmentation V2

bugfix/payment-timeout
→ Payment Timeout

automation/jira-confluence-sync
→ Jira Confluence Sync
```

Use the normalized name in the Confluence page title unless the user provides a title.

Recommended title format:

```text
[Branch Docs] <Normalized Branch Name>
```

## Workflow: Create Page When New Branch Is Created

When receiving a new branch event:

1. Extract:
   - branch name
   - repository
   - creator, if available
   - creation timestamp
   - default/base branch

2. Check whether a Confluence page already exists.

   Search by:
   - exact title
   - branch name
   - repository + branch metadata if available

3. If a page exists:
   - Do not create a duplicate.
   - Return the existing page URL.
   - Optionally update the page metadata section.

4. If no page exists:
   - Create a new Confluence page under the configured parent page.

5. Use this initial page structure:

```markdown
# <Page Title>

## Overview

This page tracks documentation for branch `<branch-name>` in `<repository>`.

## Branch Metadata

- Repository: `<owner/repo>`
- Branch: `<branch-name>`
- Base Branch: `<base-branch>`
- Created By: `<creator-or-unknown>`
- Created At: `<timestamp>`
- Status: Draft / In Progress

## Purpose

Describe the intended purpose of this branch.

## Planned Changes

_To be filled as implementation progresses._

## Technical Notes

_To be updated from branch diffs._

## Files Changed

_No diff analyzed yet._

## Recent Updates

- `<timestamp>` — Documentation page created for branch `<branch-name>`.

## Links

- Branch: `<github-branch-url>`
- Pull Request: `TBD`
```

6. Return:
   - Confluence page title
   - Confluence page URL
   - branch name
   - status

## Workflow: Update Page From Specific Branch Diff

When asked to update a Confluence page using a branch diff:

1. Confirm or infer:
   - repository
   - branch name
   - base branch
   - Confluence page

2. Fetch latest refs:

```bash
git fetch origin <base-branch>
git fetch origin <branch-name>
```

3. Determine merge base:

```bash
git merge-base origin/<base-branch> origin/<branch-name>
```

4. Generate useful diff context:

```bash
git diff --stat <merge-base>..origin/<branch-name>
git diff --name-status <merge-base>..origin/<branch-name>
git diff <merge-base>..origin/<branch-name>
```

5. Summarize the diff into documentation-friendly sections:

- Functional changes
- Technical implementation changes
- New files
- Modified files
- Deleted files
- Configuration changes
- Database/schema changes
- API changes
- Risks or migration notes
- Testing notes, if visible from changed files

6. Find the related Confluence page.

Prefer matching by:

1. Stored branch metadata
2. Exact branch name
3. Page title
4. Repository + normalized branch title

7. Fetch the current Confluence page version.

8. Update the page by replacing or appending these sections:

```markdown
## Technical Notes

<summary of implementation changes>

## Files Changed

<grouped list of changed files>

## Diff Summary

<high-level branch diff summary>

## Risks / Review Notes

<risks, breaking changes, migrations, unknowns>

## Recent Updates

- `<timestamp>` — Updated from diff of `<branch-name>` against `<base-branch>`.
```

9. Preserve existing human-written content where possible.

Do not overwrite custom sections unless the user explicitly asks.

## Confluence API Notes

Use Confluence Cloud REST API.

To search pages:

```http
GET /wiki/rest/api/content/search?cql=title~"<title>" AND type=page
```

To create a page:

```http
POST /wiki/rest/api/content
```

Payload shape:

```json
{
  "type": "page",
  "title": "Page Title",
  "space": {
    "id": "SPACE_ID"
  },
  "ancestors": [
    {
      "id": "PARENT_PAGE_ID"
    }
  ],
  "body": {
    "storage": {
      "value": "<html-content>",
      "representation": "storage"
    }
  }
}
```

To update a page:

```http
PUT /wiki/rest/api/content/<page-id>
```

Increment the existing page version:

```json
{
  "version": {
    "number": 2
  }
}
```

## HTML Conversion

Confluence storage format expects HTML.

Convert Markdown-like documentation into simple Confluence-safe HTML:

- `# Heading` → `<h1>`
- `## Heading` → `<h2>`
- lists → `<ul><li>`
- inline code → `<code>`
- code blocks → `<pre><code>`

Avoid complex styling.

## GitHub Event: Branch Created

For GitHub webhook events, branch creation usually arrives as a `create` event.

Relevant fields:

```json
{
  "ref": "feature/example",
  "ref_type": "branch",
  "repository": {
    "full_name": "owner/repo",
    "html_url": "https://github.com/owner/repo"
  },
  "sender": {
    "login": "username"
  }
}
```

Only create a Confluence page when:

```text
ref_type == "branch"
```

Ignore tag creation events.

## Output Format

After creating a page, respond with:

```markdown
Created Confluence page for branch `<branch-name>`.

- Page: <url>
- Repository: `<owner/repo>`
- Base branch: `<base-branch>`
- Status: Created
```

After updating a page, respond with:

```markdown
Updated Confluence page from branch diff.

- Page: <url>
- Branch: `<branch-name>`
- Compared against: `<base-branch>`
- Files changed: `<count>`
- Status: Updated
```

## Safety Rules

- Never expose API tokens.
- Never create duplicate pages if a matching page already exists.
- Never overwrite human-authored sections unless explicitly instructed.
- Always preserve the current Confluence page version flow.
- If the branch diff is very large, summarize by directory and key files instead of pasting the full diff.
