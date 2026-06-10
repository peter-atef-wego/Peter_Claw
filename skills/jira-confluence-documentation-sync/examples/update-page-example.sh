#!/bin/bash
# Example: Update Confluence page from GitHub commits

PAGE_NAME="Customer Segmentation AI"

# 1. Find Confluence page
echo "Finding Confluence page: $PAGE_NAME"
curl -X GET \
  -H "Authorization: Bearer $ATLASSIAN_API_TOKEN" \
  "$CONFLUENCE_URL/api/v2/pages?spaceId=$CONFLUENCE_SPACE_ID&title=$PAGE_NAME"

# 2. Get recent commits from GitHub
echo "Fetching GitHub commits..."
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$GITHUB_REPO/commits?per_page=10 | jq '.[].commit.message'

# 3. Update page with GitHub data
echo "Updating Confluence page with recent commits..."
curl -X PUT \
  -H "Authorization: Bearer $ATLASSIAN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "'$PAGE_NAME' - AI/Automation Process",
    "body": {
      "representation": "storage",
      "value": "<p>Updated with latest commits</p>"
    },
    "version": {"number": 2}
  }' \
  "$CONFLUENCE_URL/api/v2/pages/{pageId}"
