---
name: "jira-confluence-api"
description: "REST API integration for Jira and Confluence issue tracking and documentation management."
---

# Jira & Confluence REST API Integration

## Overview

This skill provides OpenClaw agent access to Jira Cloud and Confluence via REST APIs using Atlassian API token authentication.

## Authentication

### API Token Setup

1. Generate token: https://id.atlassian.com/manage-profile/security/api-tokens
2. Store in environment:
   ```bash
   export ATLASSIAN_API_TOKEN="your_token_here"
   export JIRA_EMAIL="email@example.com"
   export JIRA_URL="https://your-org.atlassian.net"
   ```

3. Set in TOOLS.md (credentials not committed to repo):
   ```markdown
   ## Atlassian Integration
   - Jira URL: https://peter-atef.atlassian.net
   - Email: [EMAIL]
   - API Token: (stored locally)
   ```

### Basic Auth Header

All requests use HTTP Basic Auth:
```bash
-H "Authorization: Basic $(echo -n 'email:api_token' | base64)"
```

Or Bearer token (for some endpoints):
```bash
-H "Authorization: Bearer {API_TOKEN}"
```

## Jira API Operations

### Base URL
```
https://your-org.atlassian.net/rest/api/3/
```

### Common Endpoints

**Get Current User**
```bash
GET /rest/api/3/myself
```

**List Projects**
```bash
GET /rest/api/3/project
```

**Search Issues (JQL)**
```bash
GET /rest/api/3/search?jql=project=PROJ AND status=Open
```

**Create Issue**
```bash
POST /rest/api/3/issue
{
  "fields": {
    "project": {"key": "PROJ"},
    "summary": "Issue summary",
    "description": "Issue description",
    "issuetype": {"name": "Bug"}
  }
}
```

**Update Issue**
```bash
PUT /rest/api/3/issue/{issueId}
{
  "fields": {
    "status": {"name": "In Progress"},
    "assignee": {"name": "user_id"}
  }
}
```

**Add Comment**
```bash
POST /rest/api/3/issue/{issueId}/comment
{
  "body": "Comment text"
}
```

**Get Issue**
```bash
GET /rest/api/3/issue/{issueId}
```

**List Issue Transitions**
```bash
GET /rest/api/3/issue/{issueId}/transitions
```

**Transition Issue**
```bash
POST /rest/api/3/issue/{issueId}/transitions
{
  "transition": {"id": "transitionId"}
}
```

### Common JQL Queries

```jql
# My open issues
assignee = currentUser() AND status = Open

# Issues in project
project = PROJ AND status != Done

# Recently created
created >= -7d

# By label
labels = "urgent"

# All open bugs
type = Bug AND status != Done
```

## Confluence API Operations

### Base URL
```
https://your-org.atlassian.net/wiki/api/v2/
```

### Common Endpoints

**Get Spaces**
```bash
GET /wiki/api/v2/spaces
```

**Get Pages in Space**
```bash
GET /wiki/api/v2/spaces/{spaceId}/pages
```

**Create Page**
```bash
POST /wiki/api/v2/pages
{
  "spaceId": "space_id",
  "title": "Page Title",
  "body": {
    "representation": "storage",
    "value": "<p>Content here</p>"
  }
}
```

**Update Page**
```bash
PUT /wiki/api/v2/pages/{pageId}
{
  "title": "Updated Title",
  "body": {
    "representation": "storage",
    "value": "<p>Updated content</p>"
  },
  "version": {"number": 1}
}
```

**Get Page Content**
```bash
GET /wiki/api/v2/pages/{pageId}?body-format=storage
```

**Search Pages**
```bash
GET /wiki/api/v2/pages?limit=20&query-param=search_term
```

## Example Usage

### Create a Bug Ticket
```bash
curl -X POST \
  -H "Authorization: Basic $(echo -n 'email:token' | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "DEV"},
      "summary": "Agent failed to process request",
      "description": "Error in REST API integration",
      "issuetype": {"name": "Bug"}
    }
  }' \
  https://peter-atef.atlassian.net/rest/api/3/issue
```

### Search for Open Issues
```bash
curl -X GET \
  -H "Authorization: Basic $(echo -n 'email:token' | base64)" \
  'https://peter-atef.atlassian.net/rest/api/3/search?jql=assignee=currentUser()%20AND%20status=Open'
```

### Add Comment to Issue
```bash
curl -X POST \
  -H "Authorization: Basic $(echo -n 'email:token' | base64)" \
  -H "Content-Type: application/json" \
  -d '{"body": "Agent updated this automatically"}' \
  https://peter-atef.atlassian.net/rest/api/3/issue/PROJ-123/comment
```

## Integration with OpenClaw Agent

The agent can:
- Query Jira issues using JQL
- Create/update/transition issues
- Comment on tickets
- Search Confluence pages
- Create/update documentation
- Build automation workflows combining Jira + Confluence

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Verify API token is valid, check base64 encoding |
| 403 Forbidden | Ensure token has correct permissions |
| Instance suspended | Reactivate Jira Cloud subscription |
| 404 Not Found | Verify project key, issue ID, or page ID |
| Rate limited (429) | Implement retry logic with backoff |

## Related

- [Jira Cloud REST API Docs](https://developer.atlassian.com/cloud/jira/rest/v3/)
- [Confluence REST API Docs](https://developer.atlassian.com/cloud/confluence/rest/v2/)
- [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
- [Authentication](https://developer.atlassian.com/cloud/jira/rest/v3/api-group-authentication/)
