# LinkedIn API & Terms Compliance Note

This doc summarizes how this project uses LinkedIn and where it aligns or may conflict with LinkedIn’s terms. **It is not legal advice.** You should read the official terms and, if needed, get legal advice.

## How this project gets data

The project is built around **selective use of the LinkedIn Member Data Portability API**: you request your own activity (changelog), and the code uses that API-derived data as the primary source. It is not a scraper: it does not discover or crawl LinkedIn; it only works with activity and URLs that the API already returns for the authenticated member.

## Official terms to review

- **[Additional Terms for the LinkedIn DMA Portability API Programs](https://www.linkedin.com/legal/l/portability-api-terms)** – governs Portability API use; overrides general API terms where they conflict.
- **[LinkedIn API Terms of Use](https://www.linkedin.com/legal/l/api-terms-of-use)** – general API and platform rules.
- **LinkedIn User Agreement** – general use of LinkedIn (including automated access to pages).

## What this project does

### 1. Member Data Portability API (Changelog) — primary data source

- **How:** OAuth with `r_dma_portability_self_serve`, then REST calls to the Member Changelog API.
- **What:** Fetches the **authenticated member’s own** activity (posts, comments, reactions they created or interacted with).
- **Storage:** Changelog-derived entities (e.g. URNs, URLs, timestamps) are stored in Neo4j and used for your own graph/GraphRAG.

**Compliance:** This use fits the Portability API’s purpose (member retrieving and using their own data). It is limited to the data and use cases described in the Portability and API terms (e.g. no advertising, sales, or recruiting use).

### 2. Optional: reading content from URLs returned by the API

- **How:** For a subset of items (your own), the code may issue `requests.get(post_url)` and parse HTML to obtain full post text or author info. The **URLs come only from the Portability API** (your changelog); the project does not discover or crawl other members or feeds.
- **Where used:**
  - **enrich_profiles.py** – optional author name and profile URL from post HTML (can be disabled with `ENABLE_AUTHOR_ENRICHMENT=0`).
  - **index_content.py** – full post text when not already in Neo4j (API content is used first; `USE_API_CONTENT_ONLY=1` disables URL fetch).
  - **extract_resources.py** – post content and link extraction from API/Neo4j first; **extract_title_from_url** also fetches arbitrary URLs (including non-LinkedIn) for resource metadata.
- **Context:** This is selective reading of pages for **your own** activity items already returned by the API, not bulk or cross-user scraping.

**Compliance concern:** LinkedIn's terms generally prohibit:

- **Scraping / automated access** – programmatic fetching and parsing of LinkedIn pages is typically restricted, even for public content.
- **Commingling** – combining LinkedIn data with other sources in ways that violate the API terms.

So: **using the Portability API as the sole source of discovery and primary source of content is aligned with the Portability/API terms; optional enrichment by reading public post URLs for your own items is a separate compliance consideration** under the general API and user terms.

## Geographic / eligibility

- Portability API is intended for members in the **EU/EEA and Switzerland** (DMA). Access may be restricted or error for other regions.
- Other LinkedIn terms (User Agreement, API Terms) apply regardless of region.

## Recommendations

1. **Read the full terms**
   Open the Portability and API terms links above and confirm your use case and data handling match.

2. **Reduce reliance on HTTP fetching of LinkedIn pages**
   Where possible, rely only on data returned by the Portability API (e.g. post/comment text or identifiers it provides) for indexing and author info, and avoid or minimize reading post URLs.

3. **Optional: document and gate “enrichment”**
   If you keep post-URL fetching:
   - Treat it as an optional enrichment (e.g. feature flag or doc note) so the core flow is “API only.”
   - In docs/UI, state that author/content enrichment uses selective reads of post URLs (from the API) and may be subject to LinkedIn’s automation rules.

4. **No advertising / sales / recruiting**
   Do not use Portability or other project data for ads, lead gen, sales prospects, or recruiting. This project’s use (personal graph/GraphRAG) is consistent with that.

5. **Data retention**
   Portability terms may have expectations on how long you keep data; general API terms sometimes impose short retention (e.g. 24–48h) for certain data. Check the current Portability and API terms for any retention or storage limits.

## Summary

| Area                         | Status / risk |
|-----------------------------|----------------|
| Portability API usage       | Aligned (own data, personal use). |
| Long-term storage of API data | Confirm against current Portability/API terms. |
| Optional read of post URLs (your own, from API) | **Risk:** may conflict with anti-scraping and commingling rules. |
| Author/content enrichment  | Same risk as above; gated by env vars; API-only mode available. |

You should validate this against the latest Portability and API terms and your own legal requirements.

---

## Workarounds: avoiding direct HTML fetch

### 1. Use API content only (recommended)

The **changelog API already returns full post and comment text**:

- Posts: `activity.specificContent.com.linkedin.ugc.ShareContent.shareCommentary.text`
- Comments: `activity.message.text`

Today we **truncate** that to 200 characters in `extract_graph_data.py`, then later fetch the post URL in `index_content.py` and `extract_resources.py` to get full text. That’s why we hit LinkedIn’s HTML.

**Change:** Store full text from the API (no truncation), then:

- **Indexing:** In `index_content.py`, read content from Neo4j (Post.content, Comment.text) instead of calling `extract_post_content(url)`. Only fall back to URL fetch when content is missing (e.g. legacy data).
- **Resources:** In `extract_resources.py`, use the full content already in Neo4j; no need to fetch when we have it.

**Author enrichment:** The API gives an **actor URN** (e.g. `urn:li:person:...`), not display name or profile URL. So we cannot fully replace author enrichment with API-only data. Options: (a) make author enrichment optional (env flag or feature flag) and document that it uses a fetch, or (b) show only the actor URN and skip fetching the profile page.

### 2. Going through a search engine

**Idea:** Query a search engine (e.g. “site:linkedin.com [text from API]”) and use the result instead of hitting LinkedIn directly.

- **If we then fetch the result URL:** We still end up requesting LinkedIn’s page to get full content → same compliance issue.
- **If we use only the search snippet:** We avoid contacting LinkedIn, but snippets are short, often truncated, and we’d be bound by the search engine’s ToS and rate limits. Quality for GraphRAG would be worse.

So using a search engine **does not remove** the need to hit LinkedIn when we need full content; and snippet-only use is a different trade-off (other ToS, lower quality), not a direct substitute.

### 3. Summary

| Goal              | API-only approach                         | Search engine                    |
|-------------------|-------------------------------------------|----------------------------------|
| Post/comment text | Yes: use full text from changelog, no fetch | No: still need to fetch for full text |
| Author name/URL   | No: API gives URN only; keep optional fetch or drop | No improvement                  |
| Resource URLs     | Yes: extract from API text in Neo4j       | N/A                              |

**Practical path:** Implemented: we store full content from the API, index from Neo4j first, and only fetch when content is missing (e.g. legacy data) unless `USE_API_CONTENT_ONLY=1`. Author enrichment is gated by `ENABLE_AUTHOR_ENRICHMENT` (see below).

### 4. Environment variables (implemented)

| Variable | Default | Effect |
|----------|---------|--------|
| `USE_API_CONTENT_ONLY` | unset (use API first, allow URL fallback) | When `1`/`true`/`yes`: never fetch LinkedIn URLs for content. Indexing and resource extraction use only data from the API/Neo4j. |
| `ENABLE_AUTHOR_ENRICHMENT` | `1` (enabled) | When `0`/`false`/`no`: skip all author name/profile fetching (no LinkedIn post page requests). Build graph, enrich_profiles CLI, and Gradio review UI will not call the author fetch. |
