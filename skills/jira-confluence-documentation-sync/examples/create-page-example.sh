#!/bin/bash
# Example: Create Confluence page from Jira ticket

PROCESS_NAME="Customer Segmentation AI"

# 1. Search Jira
echo "Searching Jira for: $PROCESS_NAME"
curl -X GET \
  -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$ATLASSIAN_API_TOKEN" | base64)" \
  "$JIRA_URL/rest/api/3/search?jql=summary~\"$PROCESS_NAME\" OR description~\"$PROCESS_NAME\"&maxResults=5"

# 2. Search Confluence
echo "Searching Confluence for existing page..."
curl -X GET \
  -H "Authorization: Bearer $ATLASSIAN_API_TOKEN" \
  "$CONFLUENCE_URL/api/v2/pages?spaceId=$CONFLUENCE_SPACE_ID&title=$PROCESS_NAME"

# 3. Create page (if not found)
echo "Creating Confluence page..."
curl -X POST \
  -H "Authorization: Bearer $ATLASSIAN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "spaceId": "'$CONFLUENCE_SPACE_ID'",
    "parentId": "'$AI_AUTOMATION_2026_FOLDER_ID'",
    "title": "'$PROCESS_NAME' - AI/Automation Process",
    "body": {
      "representation": "storage",
      "value": "<p>Page created from Jira ticket</p>"
    }
  }' \
  "$CONFLUENCE_URL/api/v2/pages"
