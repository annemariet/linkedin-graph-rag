---
name: linear-use
description: Linear workflow and how to attach images or files without brittle base64 hacks. Use for Linear issues, comments, attachments, or when the user mentions Linear tickets.
---

# Linear

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

If a screenshot must show **env-driven defaults** (e.g. `.env` overrides), confirm **local env** matches what you’re demonstrating before capturing; otherwise the UI will disagree with “code defaults.”
