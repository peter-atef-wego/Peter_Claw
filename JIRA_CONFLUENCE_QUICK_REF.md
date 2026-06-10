# Jira ↔ Confluence ↔ GitHub Quick Reference

## 🎯 What This Skill Does

Connects your **AI & Automation 2026** documentation (Confluence) with **Jira tickets** and **GitHub commits** for automated process documentation management.

---

## 💬 Quick Commands

### Create Page
```
"Create confluence page for [process]"
```
- Searches Confluence first (avoid duplicates)
- Finds matching Jira ticket
- Generates page with business + technical sections
- Returns page link

### Update Page
```
"Update confluence page [process] from github"
```
- Finds your Confluence page
- Gets latest GitHub commits
- Adds "Recent Updates" section
- Updates page version

---

## 📁 Confluence Structure

```
Data, Marketing and Growth Homepage
└── AI & Automation 2026  ← Pages go here
    ├── Customer Segmentation AI Process
    ├── Recommendation Engine Process
    ├── Churn Prediction AI Process
    └── ... (more AI processes)
```

---

## 🔗 What Gets Synced

### FROM Jira TO Confluence
```
Jira Ticket
├── Summary          → Business Summary (Business perspective)
├── Description      → Objective (Business perspective)
├── Acceptance Crit. → Technical Architecture (Technical perspective)
├── Assignee         → Owner (Page metadata)
├── Status           → Status (Page metadata)
└── Labels           → Tags (Page metadata)
```

### FROM GitHub TO Confluence
```
GitHub Commits
├── Commit message   → Update title
├── Commit hash      → Link to GitHub
├── Files changed    → Files listing
├── Lines added/del. → Change summary
└── Commit date      → Timestamp
```

---

## 📊 Page Template

When a page is created, it includes:

```
Process Overview
├─ Business Summary (from Jira summary + description)
├─ Objective (business goal)
├─ Technical Architecture (from acceptance criteria)
├─ Dependencies (systems & teams)
├─ Owner & Status (from Jira assignee + status)
├─ Jira Ticket Link (clickable link to PROJ-123)
└─ Recent Updates (GitHub commits, newest first)
```

---

## ✅ Examples

### Example 1: Create Page

```
You: "Create confluence page for customer segmentation AI"

Agent:
✅ Created: "Customer Segmentation AI - AI/Automation Process"
📄 Location: Data, Marketing and Growth Homepage → AI & Automation 2026
🔗 Jira Ticket: PROJ-123 (Data Segmentation Initiative)
👤 Owner: John Smith
⏱️ Status: In Progress
📝 Sections: Business Summary, Technical Architecture, Dependencies, Owner, Recent Updates

Page created successfully!
```

### Example 2: Update Page

```
You: "Update confluence page customer segmentation from github"

Agent:
✅ Updated: "Customer Segmentation AI - AI/Automation Process"

Added 5 recent commits:
• abc1234 (Jun 10) - Feature: Add clustering preprocessing
• def5678 (Jun 9)  - Fix: Handle null values in segments
• ghi9012 (Jun 8)  - Perf: Optimize distance calculation
• jkl3456 (Jun 7)  - Docs: Update model parameters
• mno7890 (Jun 6)  - Refactor: Simplify segment API

Page updated successfully! Last synced: 2026-06-10 10:52 UTC
```

### Example 3: Page Already Exists

```
You: "Create confluence page for customer segmentation AI"

Agent:
ℹ️ Page already exists!
📄 "Customer Segmentation AI - AI/Automation Process"
🔗 View page: https://peter-atef.atlassian.net/wiki/...

Would you like to update it with recent GitHub commits instead?
```

---

## 🔧 Setup Checklist

**One-time setup (needed before first use):**

- [ ] Jira instance reactivated (currently suspended)
- [ ] Found Confluence folder ID for "AI & Automation 2026"
- [ ] Set `AI_AUTOMATION_2026_FOLDER_ID` environment variable
- [ ] All API tokens in environment variables (JIRA, Confluence, GitHub)

**First test:**
- [ ] Run: `"Create confluence page for test process"` 
- [ ] Check page created in Confluence
- [ ] Run: `"Update confluence page test process from github"`
- [ ] Check recent commits added to page

---

## 📝 Tips & Tricks

**For better results:**
1. ✅ Create Jira tickets FIRST with clear process names
2. ✅ Use consistent naming (e.g., "Customer Segmentation AI" everywhere)
3. ✅ Keep GitHub commit messages descriptive
4. ✅ Update docs regularly to stay in sync

**Naming conventions:**
- Jira: "Build [Process] for [Business Goal]"
- Confluence: "[Process Name] - AI/Automation Process"
- GitHub: Use branch names that match process name

---

## 🚨 Common Issues & Fixes

| Problem | Fix |
|---------|-----|
| "Page not found" when updating | Create page first with "Create confluence page..." command |
| "No Jira ticket found" | Create Jira ticket with process name first |
| "Jira suspended" | Contact Atlassian support to reactivate |
| Confluence folder not found | Verify `AI_AUTOMATION_2026_FOLDER_ID` is set |
| No GitHub commits showing | GitHub repo may not have matching commits |
| Wrong page updated | Use exact page name; check Confluence for duplicates |

---

## 📚 Full Documentation

For detailed workflow and technical info, see: `JIRA_CONFLUENCE_WORKFLOW.md`

---

## 🎓 Learning Path

1. **Start:** Run first "Create confluence page..." command
2. **Verify:** Check page created in Confluence
3. **Update:** Run "Update confluence page..." with GitHub commits
4. **Practice:** Create 2-3 more pages for different processes
5. **Optimize:** Adjust process naming for better search results

---

## 📞 Support

If something breaks:
1. Check TOOLS.md for API token configuration
2. Verify Confluence folder ID is correct
3. Check GitHub repo is accessible
4. Review JIRA_CONFLUENCE_WORKFLOW.md troubleshooting section
5. Update MEMORY.md with issue for future reference
