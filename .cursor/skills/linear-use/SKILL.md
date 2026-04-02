---
name: linear-use
description: Use Linear for task management; update tickets via MCP when working on them. Attach screenshots to demonstrate progress when relevant.
---

# Linear

## Overview

Follow these rules when working with Linear task management.

## Updating Linear via MCP

Linear is connected as **plugin-linear-linear**. Use it to keep tickets in sync:

- **Set status**: `update_issue` with `id` (issue UUID or identifier like `LUC-41`) and `state` (e.g. `"In Progress"`, `"Done"`, `"In Review"`, `"Backlog"`).
- **Add a comment**: `create_comment` with `issueId` (UUID) and `body` (markdown).
- **Get issue**: `get_issue` with `id` (e.g. `LUC-41`) returns full issue including `id` (UUID for update_issue/create_comment).
- **List issues**: `list_issues` for recent issues.


## Linear updates

I'll assign tasks with a Linear ticket id or a link to a task.

- When you start working on it, mark it as "in progress"
- Start with a proposed implementation plan:
    - Follow Tidy First principles and TDD as much as possible when planning.
    - Post the plan as a comment on the Linear task
    - Mark the ticket as "in review"
- Once you get a reply from me, either through Linear or in the chat:
    - set the ticket back to "in progress"
    - create a working git branch with the ticket id in the branch name to work on the ticket
    - start updating the code with small steps
    - make small, well identified commits using gitmoji and conventional commits
- push a new pull request with the ticket id in the branch name, then mark the ticket to "in review" again
- Once the last PR is merged, mark the ticket as done

## Tickets and PRs

- Put **ticket IDs** in branch names and PR titles when the work maps to Linear (e.g. `[LUC-102] …`).
- Keep issue status in sync with workflow (e.g. In progress → In review → Done) when the team expects it.

## Images and files on issues — do not “mess around” with base64

**Problem:** Piping **large base64** image payloads through agent/tool layers often hits **size or truncation limits**. That produces **blank, corrupt, or unreadable** attachments and wastes time.

**Do instead (pick one):**

1. **Markdown image with a normal HTTPS URL** in the issue **comment** body (`mcp_Linear_save_comment` or equivalent). Linear **fetches the URL once** and stores a copy on `uploads.linear.app`; the original host can be temporary. This matches [Linear’s docs](https://linear.app/developers/how-to-upload-a-file-to-linear) (“include a URL reference … in markdown”).
2. **Server-side upload:** `fileUpload` GraphQL mutation → `PUT` the bytes to the signed URL (with response headers copied) → `attachmentCreate` with `url` = returned `assetUrl`. Run this from a **script/shell** with `LINEAR_API_KEY`, not by stuffing megabytes of base64 into a single tool argument.
3. **Ask the user** to attach the screenshot manually if no API key or no stable temporary URL is available.

**Do not:**

- Commit screenshots or other binaries to the git repo for Linear.
- Shrink screenshots to tiny JPEGs **only** to squeeze through base64 limits — text becomes illegible and looks “corrupted.”
- Rely on `mcp_Linear_create_attachment` with **large** `base64Content` unless you’ve confirmed the full string is passed end-to-end (many environments truncate).

## Gradio / UI evidence

If a screenshot must show **env-driven defaults** (e.g. `.env` overrides), confirm **local env** matches what you’re demonstrating before capturing; otherwise the UI will disagree with “code defaults.” If working on a VM, setup the local `.env` file as needed.
