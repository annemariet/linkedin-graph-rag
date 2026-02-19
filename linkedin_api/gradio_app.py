#!/usr/bin/env python3
"""
Gradio MVP UI: run pipeline (collect → enrich → summarize) and query GraphRAG.

Tab 1: Pipeline — period, from-cache, optional limit; run and see log.
Tab 2: GraphRAG query — lazy-init Neo4j and Vertex AI on demand.
"""

import logging
import os
import tempfile
from typing import TYPE_CHECKING

import gradio as gr
import json
from neo4j import GraphDatabase
from neo4j_graphrag.generation.graphrag import GraphRAG

if TYPE_CHECKING:
    from neo4j import Driver

from linkedin_api.llm_config import create_embedder, create_llm
from linkedin_api.content_store import list_summarized_metadata
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


def _format_post_for_prompt(m: dict) -> str:
    summary = _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
    parts = [f"- {summary}"]
    if m.get("topics"):
        parts.append(f"  Topics: {', '.join(m['topics'])}")
    if m.get("technologies"):
        parts.append(f"  Tech: {', '.join(m['technologies'])}")
    return "\n".join(parts)


def _batches_by_char_limit(metas: list[dict], char_limit: int) -> list[list[dict]]:
    """Split metas into batches; start a new batch when adding the next post would exceed char_limit."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0
    for m in metas:
        block = _format_post_for_prompt(m)
        if current and current_len + len(block) > char_limit:
            batches.append(current)
            current = []
            current_len = 0
        current.append(m)
        current_len += len(block)
    if current:
        batches.append(current)
    return batches


def _summarize_batch(llm, metas: list[dict], category_label: str) -> str:
    """One LLM call for this batch. Returns 2–4 sentence summary."""
    block = "\n\n".join(_format_post_for_prompt(m) for m in metas)
    system = (
        "You are a concise analyst. Summarize the following LinkedIn posts in 2–4 sentences. "
        "Highlight main themes, recurring topics, and any patterns. Output plain text, no preamble."
    )
    prompt = f"Posts in '{category_label}' ({len(metas)}):\n\n---\n{block}\n---"
    response = llm.invoke(prompt, system_instruction=system)
    return (response.content if hasattr(response, "content") else str(response)).strip()


def _format_other_section(metas: list[dict]) -> str:
    """Format 'other' category as summary + link per post (no LLM)."""
    lines = []
    for m in metas:
        summary = _truncate(m["summary"], REPORT_MAX_SUMMARY_CHARS)
        url = (m.get("post_url") or "").strip()
        if url:
            lines.append(f"- {summary} — [post]({url})")
        else:
            lines.append(f"- {summary}")
    return "\n".join(lines) if lines else "_No posts in this category._"


def generate_activity_report() -> str:
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
                parts.append(f"## {label}\n\n{_format_other_section(category_metas)}")
                continue
            batches = _batches_by_char_limit(category_metas, REPORT_BATCH_CHAR_LIMIT)
            batch_summaries = [_summarize_batch(llm, batch, label) for batch in batches]
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
            project_id = creds_data.get("project_id")
            logger.info(f"Loaded GCP credentials to {creds_path} (0600)")
            return project_id
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
                vertex_location = os.getenv("VERTEX_LOCATION", "europe-west9")
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
    """Pipeline tab: run collect → enrich → summarize with options."""
    with gr.Blocks(
        title="Pipeline",
        css="#report-output { min-height: 24em; overflow-y: auto; }",
    ) as block:
        gr.Markdown(
            "# Pipeline\nRun collect → enrich → summarize. Progress appears below."
        )
        with gr.Row():
            period = gr.Dropdown(
                choices=["7d", "14d", "30d"],
                value="7d",
                label="Period",
            )
            from_cache = gr.Checkbox(value=False, label="From cache (neo4j_data)")
            limit = gr.Number(value=None, label="Limit (optional)", precision=0)
        run_btn = gr.Button("Run pipeline", variant="primary")
        log_output = gr.Textbox(
            label="Log",
            lines=12,
            max_lines=24,
            interactive=False,
            placeholder="Click Run pipeline to start.",
        )
        gr.Markdown(
            "---\n**Report** — Summarize your activity with the LLM (uses summarized posts from the pipeline)."
        )
        report_btn = gr.Button("Generate report", variant="secondary")
        report_output = gr.Markdown(
            value="Click **Generate report** to get a global summary.",
            label="Report",
            elem_id="report-output",
        )

        def run(last: str, from_cache: bool, lim):
            logger.info(
                "Pipeline run started: last=%s from_cache=%s limit=%s",
                last,
                from_cache,
                lim,
            )
            try:
                lim_int = int(lim) if lim not in (None, "", float("nan")) else None
            except (TypeError, ValueError):
                lim_int = None
            yield from run_pipeline_ui_streaming(
                last=last,
                from_cache=from_cache,
                limit=lim_int,
            )

        run_btn.click(
            fn=run,
            inputs=[period, from_cache, limit],
            outputs=log_output,
        )

        def do_report():
            logger.info("Generate report clicked")
            yield "🔄 Generating report…", gr.update(interactive=False)
            try:
                result = generate_activity_report()
            except Exception as e:
                logger.exception("Report generation failed")
                result = _report_error_message(e)
            yield result, gr.update(interactive=True)

        report_btn.click(
            fn=do_report,
            inputs=[],
            outputs=[report_output, report_btn],
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
    logger.info(f"Starting Gradio app on {host}:{port}")
    demo.launch(server_name=host, server_port=port, share=False, show_error=True)


if __name__ == "__main__":
    main()
