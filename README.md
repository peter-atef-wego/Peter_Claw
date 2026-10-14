# Peter_Claw: Confluence-GitHub Sync Agent

A single-purpose agent that keeps Confluence documentation in sync with GitHub branch work.
Jira is used read-only to initialize a page for a new process.

## What it does

| Request | Result |
|---|---|
| A new branch is created | A `[Branch Docs] <Branch Name>` page is created under the configured parent page |
| "Update the Confluence page from branch `X`" | The page is updated from the diff of `X` against its base branch |
| "Create a Confluence page for process X" | Searches the AI & Automation 2026 folder; if no page exists, creates one from the matching Jira ticket |
| "Update the documentation for process X" | Updates the page from recent GitHub commits and diffs |

## Layout

```
CLAUDE.md                                   Agent instructions and rules
skills/
  confluence-branch-docs/SKILL.md           Branch created / branch diff -> Confluence page
  jira-confluence-documentation-sync/       Jira ticket -> page; GitHub commits -> page updates
    SKILL.md
    examples/                               Example create/update scripts and config
docs/
  JIRA_CONFLUENCE_QUICK_REF.md              Command cheat sheet
  JIRA_CONFLUENCE_WORKFLOW.md               End-to-end workflow and troubleshooting
.env.example                                Required environment variables (placeholders only)
```

## Setup

1. Copy `.env.example` to `.env` (gitignored) and fill in real values.
2. Set `CONFLUENCE_PARENT_PAGE_ID` / `AI_AUTOMATION_2026_FOLDER_ID` to the Confluence page that new pages go under.
3. Point `GITHUB_REPOSITORY` at the repo whose branches you want documented.
4. Run the agent with this repo as its workspace so it loads `CLAUDE.md` and the skills.

## Security

Tokens live only in the environment. CI fails if a credential-shaped string is committed.
