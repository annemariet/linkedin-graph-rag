---
name: gradio-pages
description: Build Gradio UIs that stay responsive. Use when creating or modifying Gradio apps, Blocks, event handlers, or when the user mentions Gradio, slow UI, or blocking.
---

# Gradio UI: Keep It Responsive

## Rule: Never Block the First Paint

Handlers that update the UI must return **quickly** (< ~1s). If a user action triggers slow work (HTTP, browser/Playwright, heavy compute), the UI will freeze until the handler returns.

**Do:**
- Return immediately with **placeholders** (e.g. "Loading…", "Click X to load"), then do slow work only when the user explicitly asks (e.g. a separate button).
- Or run slow work in a **background thread** and update outputs when done (if Gradio supports it for your flow).

**Don’t:**
- Run fetch + thumbnail + format in the same handler that’s supposed to show the first item.
- Call slow helpers (e.g. `fetch_post_page`, `get_thumbnail_path_for_url`) inside Load or Navigate handlers "for convenience." Prefer on-demand (e.g. "Extract author", "Load thumbnail").

## One Expensive Operation per Explicit Action

- "Load" / "Sync" → only load and sync data; render the first item from in-memory/DB. Do **not** run author fetch or thumbnail for the first item before returning.
- "Extract author" → run only the author (and content) fetch. Do **not** run thumbnail in the same call.
- Thumbnail → run only when the user asks for a thumbnail (e.g. "Load thumbnail" button) or in a separate, optional step after author is shown.

So: **split "author" and "thumbnail"** into separate code paths. Thumbnail can be lazy (on demand or after a short delay) so "Extract author" stays fast (cache ~tens of ms, HTTP ~1–2 s, not minutes).

## Logging and Observability

- Use `logging` (e.g. `logger.info`) in handlers and in shared code (fetch, sync). Configure `logging.basicConfig` with a clear format (e.g. `%(asctime)s [%(levelname)s] %(name)s: %(message)s`) so progress is visible in the **terminal** where the app is run.
- Log at the start of slow steps (e.g. "Fetching changelog…", "Syncing N elements…") so the user sees that the app is working, not stuck.

## State and Handlers

- Keep UI state in `gr.State`; create the State **inside** `gr.Blocks()` so Gradio treats it as a component.
- Ensure each button/action has a **single** handler that does one thing. Avoid chains that re-run the same slow logic multiple times (e.g. multiple handlers updating the same outputs with the same heavy call).
- When navigating (Prev/Next), prefer updating from already-loaded state (e.g. queue in State). Optionally run lightweight work (e.g. render from cache); defer heavy work (fetch, thumbnail) to explicit user actions.

## Checklist Before Shipping

- [ ] Load / first paint returns in &lt; ~2 s with real data (or clear "Loading…" / placeholder).
- [ ] No single click runs both HTTP fetch and Playwright (or other multi-second work) unless the user explicitly asked for both.
- [ ] Terminal shows progress (logs) during long operations.
- [ ] How to stop the app is obvious (e.g. "Press Ctrl+C in the terminal" in the UI or README).
