#!/usr/bin/env python3
"""
Gradio MVP UI: run pipeline (collect → enrich → summarize) and query GraphRAG.

Tab 1: Pipeline — period, from-cache, optional limit; run and see log.
Tab 2: GraphRAG query — lazy-init Neo4j and Vertex AI on demand.
"""

import logging
import os
import tempfile

import dotenv

dotenv.load_dotenv()
from typing import TYPE_CHECKING

import gradio as gr
import json
from neo4j import GraphDatabase
from neo4j_graphrag.generation.graphrag import GraphRAG

if TYPE_CHECKING:
    from neo4j import Driver

from linkedin_api.activity_csv import get_data_dir
from linkedin_api.content_store import list_summarized_metadata, load_content
from linkedin_api.llm_config import create_embedder, create_llm
from linkedin_api.query_graphrag import (
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
    create_vector_cypher_retriever,
    create_vector_retriever,
)
from linkedin_api.run_pipeline import run_pipeline_ui_streaming

_REPORT_SYSTEM = (
    "You are a concise analyst. Summarize the user's LinkedIn activity globally. "
    "Highlight main themes, recurring topics, technologies, and any patterns. "
    "Output a short report in markdown (sections, bullet points). No preamble."
)
REPORT_MAX_POSTS = 50
REPORT_BATCH_CHAR_LIMIT = 4000
REPORT_MAX_SUMMARY_CHARS = 400
REPORT_MAX_FULL_POST_CHARS = 1500

# Order defines report sections. "other" gets summaries + links only (no LLM).
REPORT_CATEGORIES = (
    "product_announcement",
    "tutorial",
    "opinion",
    "paper",
    "experiment",
    "job_news",
    "other",
)
CATEGORY_LABELS = {
    "product_announcement": "Product announcements",
    "tutorial": "Tutorials & how-to",
    "opinion": "Opinion & hot takes",
    "paper": "Papers & research",
    "experiment": "Experiments & benchmarks",
    "job_news": "Job & career",
    "other": "Other (uncategorized — review to improve categorization)",
}


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


def _format_post_for_prompt(m: dict, use_full_posts: bool = True) -> str:
    """Format post for LLM prompt. Uses full content or summary."""
    text: str
    if use_full_posts and m.get("urn"):
        content = load_content(m["urn"])
        if content:
            text = _truncate(content, REPORT_MAX_FULL_POST_CHARS)
        else:
            text = _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
    else:
        text = _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
    parts = [f"- {text}"]
    if m.get("topics"):
        parts.append(f"  Topics: {', '.join(m['topics'])}")
    if m.get("technologies"):
        parts.append(f"  Tech: {', '.join(m['technologies'])}")
    return "\n".join(parts)


def _batches_by_char_limit(
    metas: list[dict], char_limit: int, use_full_posts: bool = True
) -> list[list[dict]]:
    """Split metas into batches; start a new batch when adding the next post would exceed char_limit."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0
    for m in metas:
        block = _format_post_for_prompt(m, use_full_posts)
        if current and current_len + len(block) > char_limit:
            batches.append(current)
            current = []
            current_len = 0
        current.append(m)
        current_len += len(block)
    if current:
        batches.append(current)
    return batches


def _summarize_batch(
    llm, metas: list[dict], category_label: str, use_full_posts: bool = True
) -> str:
    """One LLM call for this batch. Returns 2–4 sentence summary."""
    block = "\n\n".join(_format_post_for_prompt(m, use_full_posts) for m in metas)
    system = (
        "You are a concise analyst. Summarize the following LinkedIn posts in 2–4 sentences. "
        "Highlight main themes, recurring topics, and any patterns. Output plain text, no preamble."
    )
    prompt = f"Posts in '{category_label}' ({len(metas)}):\n\n---\n{block}\n---"
    response = llm.invoke(prompt, system_instruction=system)
    return (response.content if hasattr(response, "content") else str(response)).strip()


def _format_other_section(metas: list[dict], use_full_posts: bool = True) -> str:
    """Format 'other' category as summary or full content + link per post (no LLM)."""
    lines = []
    for m in metas:
        if use_full_posts and m.get("urn"):
            content = load_content(m["urn"])
            text = (
                _truncate(content, REPORT_MAX_FULL_POST_CHARS)
                if content
                else _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
            )
        else:
            text = _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
        url = (m.get("post_url") or "").strip()
        if url:
            lines.append(f"- {text} — [post]({url})")
        else:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "_No posts in this category._"


def _report_signature(
    use_full_posts: bool = True,
) -> tuple[int, tuple[str, ...], bool] | None:
    """Signature of the post set used for the report. None if no posts. Used for cache invalidation."""
    all_metas = list_summarized_metadata()
    if not all_metas:
        return None
    all_metas.sort(key=lambda m: m.get("summarized_at") or "", reverse=True)
    metas = all_metas[:REPORT_MAX_POSTS]
    return (
        len(all_metas),
        tuple((m.get("summarized_at") or "") for m in metas),
        use_full_posts,
    )


_REPORT_CACHE_FILE = "report_cache.json"


def _load_report_cache(
    use_full_posts: bool,
) -> tuple[str, tuple[int, tuple[str, ...], bool]] | None:
    """Load cached report from disk. Returns (report, signature) or None if mode mismatch."""
    path = get_data_dir() / _REPORT_CACHE_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        n = data.get("n", 0)
        at = tuple(data.get("summarized_at", []))
        cached_full = data.get("use_full_posts", True)
        if cached_full != use_full_posts:
            return None
        report = data.get("report", "")
        if not report:
            return None
        return (report, (n, at, use_full_posts))
    except (json.JSONDecodeError, OSError):
        return None


def _save_report_cache(report: str, sig: tuple[int, tuple[str, ...], bool]) -> None:
    """Persist report and signature to disk so cache survives page refresh."""
    path = get_data_dir() / _REPORT_CACHE_FILE
    try:
        path.write_text(
            json.dumps(
                {
                    "n": sig[0],
                    "summarized_at": list(sig[1]),
                    "use_full_posts": sig[2],
                    "report": report,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def generate_activity_report(use_full_posts: bool = True) -> str:
    """Build report by category. Batches by char limit per category; 'other' is summaries + links only."""
    setup_gcp_credentials()
    all_metas = list_summarized_metadata()
    if not all_metas:
        return "No summarized posts found. Run the pipeline first (collect → enrich → summarize)."
    all_metas.sort(key=lambda m: m.get("summarized_at") or "", reverse=True)
    metas = all_metas[:REPORT_MAX_POSTS]
    by_category: dict[str, list[dict]] = {}
    for m in metas:
        cat = (m.get("category") or "").strip().lower() or "other"
        if cat not in REPORT_CATEGORIES:
            cat = "other"
        by_category.setdefault(cat, []).append(m)
    try:
        llm = create_llm(json_mode=False)
        parts = []
        for cat in REPORT_CATEGORIES:
            category_metas = by_category.get(cat)
            if not category_metas:
                continue
            label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
            if cat == "other":
                parts.append(
                    f"## {label}\n\n{_format_other_section(category_metas, use_full_posts)}"
                )
                continue
            batches = _batches_by_char_limit(
                category_metas, REPORT_BATCH_CHAR_LIMIT, use_full_posts
            )
            batch_summaries = [
                _summarize_batch(llm, batch, label, use_full_posts) for batch in batches
            ]
            parts.append(f"## {label}\n\n" + "\n\n".join(batch_summaries))
        if not parts:
            return "No posts to summarize."
        return "\n\n".join(parts)
    except Exception as e:
        logger.exception("Report generation failed")
        msg = str(e)
        if "504" in msg or "Gateway time-out" in msg or "timeout" in msg.lower():
            return (
                "❌ The LLM request timed out (504). Try again in a few minutes, "
                "or run the pipeline with a **limit** to use fewer posts."
            )
        if "<!DOCTYPE" in msg or "<html" in msg.lower() or "<span" in msg:
            return "❌ The LLM provider returned an error page. Try again later or check your API/network."
        return f"❌ Error generating report: {msg[:200]}"


def _report_error_message(e: Exception) -> str:
    """Turn an exception into a short, UI-safe message (no HTML)."""
    msg = str(e)
    if "504" in msg or "Gateway time-out" in msg or "timeout" in msg.lower():
        return (
            "❌ The LLM request timed out (504). Try again in a few minutes, "
            "or run the pipeline with a limit to use fewer posts."
        )
    if any(tag in msg for tag in ("<!DOCTYPE", "<html", "<span", "<div")):
        return "❌ The LLM provider returned an error page. Try again later or check your API/network."
    return f"❌ Error: {msg[:200]}"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class GraphRAGServices:
    """Container for initialized GraphRAG services."""

    def __init__(self, driver: "Driver", embedder, llm):
        self.driver = driver
        self.embedder = embedder
        self.llm = llm


def setup_gcp_credentials() -> str | None:
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return None
    try:
        creds_data = json.loads(creds_json)
        fd, creds_path = tempfile.mkstemp(suffix=".json", prefix="gcp_credentials_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(creds_data, f)
            os.chmod(creds_path, 0o600)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            project_id: str | None = creds_data.get("project_id")
            logger.info(f"Loaded GCP credentials to {creds_path} (0600)")
            return str(project_id) if project_id else None
        except (OSError, json.JSONDecodeError) as e:
            try:
                os.unlink(creds_path)
            except OSError:
                pass
            logger.warning(f"Failed to write credentials file: {e}")
            return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
        return None


def resolve_vertex_project(project_id_from_creds: str | None) -> str:
    vertex_project = os.getenv("VERTEX_PROJECT") or project_id_from_creds
    if not vertex_project:
        try:
            import google.auth

            _, vertex_project = google.auth.default()
        except (ImportError, Exception):
            pass
    if not vertex_project:
        raise RuntimeError(
            "Vertex AI project not found. Set VERTEX_PROJECT or ensure "
            "GOOGLE_APPLICATION_CREDENTIALS_JSON contains project_id."
        )
    return vertex_project


def initialize_services() -> GraphRAGServices:
    project_id = setup_gcp_credentials()
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logger.info("Connected to Neo4j successfully")
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Neo4j: {e}") from e
    try:
        if os.getenv("LLM_PROVIDER", "openai") == "vertexai":
            try:
                import vertexai

                vertex_project = resolve_vertex_project(project_id)
                vertex_location = os.getenv("VERTEX_LOCATION", "[REDACTED]")
                vertexai.init(project=vertex_project, location=vertex_location)
            except ImportError:
                pass
        embedder = create_embedder()
        llm = create_llm()
        logger.info("Initialized LLM and embedder successfully")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize LLM/embedder: {e}") from e
    return GraphRAGServices(driver, embedder, llm)


def query_linkedin_graphrag(
    services: GraphRAGServices,
    query_text: str,
    use_cypher: bool = False,
    top_k: int = 5,
) -> str:
    if not query_text.strip():
        return "⚠️ Please enter a query."
    try:
        retriever = (
            create_vector_cypher_retriever(services.driver, services.embedder)
            if use_cypher
            else create_vector_retriever(services.driver, services.embedder)
        )
        rag = GraphRAG(llm=services.llm, retriever=retriever)
        response = rag.search(
            query_text=query_text,
            retriever_config={"top_k": top_k},
            return_context=True,
        )
        answer = response.answer
        if hasattr(response, "retriever_result") and response.retriever_result:
            if len(response.retriever_result.items) > 0:
                answer += f"\n\n---\n\n📊 **Retrieved {len(response.retriever_result.items)} relevant chunks**"
        return answer
    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        return f"❌ Error: {e}\n\nCheck configuration and that content is indexed."


def get_database_stats(services: GraphRAGServices) -> str:
    try:
        with services.driver.session(database=NEO4J_DATABASE) as session:
            chunk_result = session.run(
                "MATCH (c:Chunk) RETURN count(c) as count"
            ).single()
            chunk_count = chunk_result["count"] if chunk_result else 0
            embedding_result = session.run(
                "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
            ).single()
            chunk_with_embedding = embedding_result["count"] if embedding_result else 0
            post_result = session.run(
                "MATCH (p:Post) RETURN count(p) as count"
            ).single()
            post_count = post_result["count"] if post_result else 0
            comment_result = session.run(
                "MATCH (c:Comment) RETURN count(c) as count"
            ).single()
            comment_count = comment_result["count"] if comment_result else 0
            enrichment_counts = {}
            for label in [
                "Resource",
                "Technology",
                "Concept",
                "Process",
                "Challenge",
                "Benefit",
                "Example",
            ]:
                result = session.run(
                    f"MATCH (n:{label}) RETURN count(n) as count"
                ).single()
                count = result["count"] if result else 0
                if count > 0:
                    enrichment_counts[label] = count
            output = "**Database Statistics**\n\n"
            output += f"- Total Chunks: {chunk_count}\n"
            output += f"- Chunks with Embeddings: {chunk_with_embedding}\n"
            output += f"- Posts: {post_count}\n"
            output += f"- Comments: {comment_count}\n"
            if enrichment_counts:
                output += "\n**Enrichment Nodes:**\n"
                for label, count in enrichment_counts.items():
                    output += f"- {label}: {count}\n"
            if chunk_with_embedding == 0:
                output += (
                    "\n⚠️ **Warning**: No embeddings found. Run `index_content` first."
                )
            elif chunk_with_embedding < chunk_count:
                output += f"\n⚠️ **Warning**: {chunk_count - chunk_with_embedding} chunks missing embeddings."
            return output
    except Exception as e:
        logger.error(f"Error getting database stats: {e}", exc_info=True)
        return f"❌ Error getting stats: {str(e)}"


def create_pipeline_interface():
    """Pipeline tab: single button runs collect → enrich → summarize → report; progress bars and caches."""
    with gr.Blocks(
        title="Pipeline",
        css="#report-output { min-height: 24em; overflow-y: auto; }",
    ) as block:
        gr.Markdown(
            "# Pipeline\nOne run: fetch/enrich/summarize (using caches when possible), then generate report."
        )
        with gr.Row():
            period = gr.Dropdown(
                choices=["7d", "14d", "30d"],
                value="7d",
                label="Period",
            )
            from_cache = gr.Checkbox(
                value=False,
                label="Skip fetch (use cached data only)",
                info="No LinkedIn API call; use only previously fetched data.",
            )
            limit = gr.Number(value=None, label="Limit (optional)", precision=0)
            use_full_posts = gr.Checkbox(
                value=True,
                label="Use full post content",
                info="Default: use full posts. Uncheck to use short summaries (legacy).",
            )
        run_btn = gr.Button("Get latest news report", variant="primary")
        log_output = gr.Textbox(
            label="Log",
            lines=6,
            max_lines=12,
            interactive=False,
            visible=True,
        )
        report_output = gr.Markdown(
            value="Click **Get latest news report** to refresh data and get a summary.",
            label="Report",
            elem_id="report-output",
        )
        report_cache_state = gr.State(value=None)  # (report_text, signature) or None

        def run_all(
            last: str,
            from_cache: bool,
            lim,
            use_full: bool,
            cache,
            progress=gr.Progress(),
        ):
            logger.info(
                "Pipeline & report started: last=%s from_cache=%s limit=%s",
                last,
                from_cache,
                lim,
            )
            try:
                lim_int = int(lim) if lim not in (None, "", float("nan")) else None
            except (TypeError, ValueError):
                lim_int = None

            progress(0, desc="Fetching…")
            log_text = ""
            try:
                for chunk in run_pipeline_ui_streaming(
                    last=last,
                    from_cache=from_cache,
                    limit=lim_int,
                ):
                    log_text = chunk
                    last = chunk.strip().split("\n")[-1] if chunk.strip() else ""
                    if last.startswith("Enriching ") and "/" in last:
                        try:
                            nums = (
                                last.removeprefix("Enriching ").rstrip("…").split("/")
                            )
                            done, total = int(nums[0]), int(nums[1])
                            if total > 0:
                                progress(0.2 + 0.2 * done / total, desc=last)
                        except Exception:
                            pass
                    elif last.startswith("Summarizing batch ") and "/" in last:
                        try:
                            nums = (
                                last.removeprefix("Summarizing batch ")
                                .rstrip("…")
                                .split("/")
                            )
                            done, total = int(nums[0]), int(nums[1])
                            if total > 0:
                                progress(0.4 + 0.2 * done / total, desc=last)
                        except Exception:
                            pass
                    elif "Collected" in last:
                        progress(0.2, desc="Enriching…")
                    elif "Enriched" in last:
                        progress(0.4, desc="Summarizing…")
                    elif "Summarized" in last:
                        progress(0.6, desc="Finishing up…")
                    elif "✅ Done" in last:
                        progress(0.75, desc="Generating report…")
                    elif last.startswith("❌"):
                        progress(1, desc="Failed")
                        yield log_text, gr.update(
                            value="⚠️ Pipeline failed. See log above."
                        ), cache
                        return
                    yield log_text, gr.update(), cache
            except Exception as e:
                logger.exception("Pipeline failed")
                err_msg = str(e)[:200]
                progress(1, desc="Failed")
                yield f"{log_text}\n\n❌ Failed: {err_msg}", gr.update(
                    value="⚠️ Pipeline failed. See log above."
                ), cache
                return

            progress(0.75, desc="Generating report…")
            sig = _report_signature(use_full)
            disk = _load_report_cache(use_full)
            if disk is not None and disk[1] == sig:
                result = disk[0]
                logger.info("Report cache hit (disk)")
                cache = (result, sig)
            elif cache is not None and cache[1] == sig:
                result = cache[0]
                logger.info("Report cache hit (session)")
            else:
                try:
                    result = generate_activity_report(use_full_posts=use_full)
                    cache = (result, sig) if sig else None
                    if sig is not None:
                        _save_report_cache(result, sig)
                except Exception as e:
                    logger.exception("Report generation failed")
                    result = _report_error_message(e)
                    cache = None
            progress(1, desc="Done.")
            yield log_text, result, cache

        run_btn.click(
            fn=run_all,
            inputs=[period, from_cache, limit, use_full_posts, report_cache_state],
            outputs=[log_output, report_output, report_cache_state],
        )
    return block


def create_query_interface():
    """GraphRAG query tab; lazy-init on first use."""
    with gr.Blocks(title="GraphRAG Query") as block:
        gr.Markdown(
            "# GraphRAG Query\nQuery indexed LinkedIn content. Click Initialize to connect."
        )
        services_state = gr.State(value=None)

        def init_fn():
            try:
                services = initialize_services()
                return services, "Connected to Neo4j and Vertex AI. You can query now."
            except RuntimeError as e:
                logger.exception("GraphRAG init failed")
                return None, f"Initialization failed: {e}"

        init_btn = gr.Button("Initialize GraphRAG", variant="secondary")
        init_status = gr.Markdown(
            value="GraphRAG not initialized. Click the button to connect."
        )
        with gr.Row():
            with gr.Column(scale=2):
                query_input = gr.Textbox(
                    label="Your Question",
                    placeholder="What are the main themes in my LinkedIn posts?",
                    lines=3,
                )
                with gr.Row():
                    use_cypher = gr.Checkbox(
                        label="Use Graph Traversal (Cypher)",
                        value=False,
                        info="Include related entities in the search",
                    )
                    top_k = gr.Slider(1, 20, value=5, step=1, label="top_k")
                submit_btn = gr.Button("Search", variant="primary", size="lg")
            with gr.Column(scale=1):
                stats_output = gr.Markdown(value="Initialize GraphRAG to load stats.")
                refresh_stats = gr.Button("Refresh Stats", size="sm")
        answer_output = gr.Markdown(label="Answer")
        gr.Examples(
            examples=[
                ["What topics do I post about most frequently?", False, 5],
                ["Show me posts about AI or machine learning", False, 10],
                ["Who are the most active commenters on my posts?", True, 10],
            ],
            inputs=[query_input, use_cypher, top_k],
        )

        init_btn.click(
            fn=init_fn,
            inputs=[],
            outputs=[services_state, init_status],
        )

        def do_query(svc, q, cypher, k):
            if svc is None:
                return "Click **Initialize GraphRAG** first."
            return query_linkedin_graphrag(svc, q, cypher, k)

        def do_stats(svc):
            if svc is None:
                return "Click **Initialize GraphRAG** to load stats."
            return get_database_stats(svc)

        submit_btn.click(
            fn=do_query,
            inputs=[services_state, query_input, use_cypher, top_k],
            outputs=answer_output,
        )
        query_input.submit(
            fn=do_query,
            inputs=[services_state, query_input, use_cypher, top_k],
            outputs=answer_output,
        )
        refresh_stats.click(
            fn=do_stats,
            inputs=[services_state],
            outputs=stats_output,
        )
    return block


def main():
    pipeline_demo = create_pipeline_interface()
    query_demo = create_query_interface()
    demo = gr.TabbedInterface(
        [pipeline_demo, query_demo],
        ["Pipeline", "GraphRAG query"],
        title="LinkedIn MVP",
    )
    port = int(os.getenv("PORT", 7860))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(
        "LLM_PROVIDER=%s (embedding: %s)",
        os.getenv("LLM_PROVIDER", "<unset>"),
        os.getenv("EMBEDDING_PROVIDER", "<unset>"),
    )
    logger.info(f"Starting Gradio app on {host}:{port}")
    demo.launch(server_name=host, server_port=port, share=False, show_error=True)


if __name__ == "__main__":
    main()
