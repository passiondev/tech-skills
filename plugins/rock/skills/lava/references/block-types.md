# Rock RMS Block Types

Common block types for page building. The catalog (`~/.claude/passion-rock/catalog.json`) has the full list with IDs for the connected instance.

## Content

**HTML Content** -- Static or dynamic HTML content with Lava support.
- Content: HTML/Lava string
- Most versatile block, used for custom content

**Content Channel View** -- Display items from a Content Channel (blog posts, news, etc.).
- ContentChannelId, template settings

**Markdown Detail** -- Render markdown content.

## People

**Person Profile** -- Full person profile view.
**Person Search** -- Search for people by name, email, phone.
**Person Directory** -- Directory listing with filters.
**Person Bio** -- Compact person bio display.

## Groups

**Group Detail** -- Display group information.
**Group List** -- List groups with filtering.
**Group Member List** -- Members of a specific group.
**Group Finder** -- Search/browse groups by type, location, schedule.
**Group Registration** -- Register for a group.

## Workflows

**Workflow Entry** -- Launch a workflow from a page (shows the entry form).
- WorkflowTypeId: which workflow to launch
- Key block for user-facing workflow forms

**Workflow List** -- List workflow instances with status.
- WorkflowTypeId: filter by workflow type
- Shows active/completed workflows

**Workflow Navigation** -- Navigate between workflow categories.

## Check-in

**Check-in Manager** -- Staff check-in management console.
**Check-in Kiosk** -- Self-service check-in display.

## Communication

**Communication Entry** -- Compose and send communications.
**Communication List** -- List sent communications.

## Finance

**Transaction Entry** -- Online giving form.
**Giving Analytics** -- Giving reports and dashboards.
**Scheduled Transaction List** -- Manage recurring gifts.

## CMS / Navigation

**Page Menu** -- Navigation menu for child pages.
**Login** -- Login form.
**Registration** -- New account registration.
**Redirect** -- Redirect to another URL.
**Page/Zone Block List** -- Admin block for managing blocks on a page.

## Reporting

**Dynamic Data** -- Display results of a DataView or SQL query.
**Report Viewer** -- Display a Rock report.
**Metric Detail** -- Show metric values and charts.

## Notes

- Blocks are placed in Zones on a Page. Common zones: Main, Sidebar, Feature, Footer.
- Each block has settings (attributes) that configure its behavior.
- BlockType IDs vary by Rock instance. Use the catalog to find the correct ID.
- System blocks (IsSystem=true) should not be modified or removed.
