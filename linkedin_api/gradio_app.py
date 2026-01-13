#!/usr/bin/env python3
"""
Gradio web interface for LinkedIn GraphRAG.

This provides a web UI for querying indexed LinkedIn content using GraphRAG.
"""

# Standard library imports
import json
import logging
import os
import tempfile
from typing import TYPE_CHECKING

# Third-party imports
import google.auth
import gradio as gr
import vertexai
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings
from neo4j_graphrag.generation.graphrag import GraphRAG
from neo4j_graphrag.llm import VertexAILLM

if TYPE_CHECKING:
    from neo4j import Driver

# Local imports
from linkedin_api.query_graphrag import (
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
    EMBEDDING_MODEL,
    LLM_MODEL,
    create_vector_cypher_retriever,
    create_vector_retriever,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphRAGServices:
    """Container for initialized GraphRAG services."""

    def __init__(
        self,
        driver: "Driver",
        embedder: VertexAIEmbeddings,
        llm: VertexAILLM,
    ):
        self.driver = driver
        self.embedder = embedder
        self.llm = llm


def setup_gcp_credentials() -> str | None:
    """
    Setup Google Cloud credentials from environment variable.

    If GOOGLE_APPLICATION_CREDENTIALS_JSON is set, writes it to a secure temp file.
    Security: File is created with 0600 permissions (read/write for owner only).

    Returns:
        Project ID from credentials if available, None otherwise
    """
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return None

    try:
        creds_data = json.loads(creds_json)
        # Use mkstemp for secure file creation with restrictive permissions
        fd, creds_path = tempfile.mkstemp(suffix=".json", prefix="gcp_credentials_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(creds_data, f)
            # Set restrictive permissions: 0600 = read/write for owner only
            os.chmod(creds_path, 0o600)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            project_id: str | None = creds_data.get("project_id")
            logger.info(
                f"Loaded GCP credentials from environment variable to {creds_path} "
                f"(permissions: 0600)"
            )
            return project_id
        except (OSError, json.JSONDecodeError) as e:
            # Clean up file if something goes wrong
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
    """
    Resolve Vertex AI project ID from various sources.

    Priority:
    1. VERTEX_PROJECT environment variable
    2. project_id from credentials JSON
    3. Default project from Application Default Credentials

    Args:
        project_id_from_creds: Project ID extracted from credentials JSON

    Returns:
        Project ID string

    Raises:
        RuntimeError: If project ID cannot be determined
    """
    vertex_project = os.getenv("VERTEX_PROJECT") or project_id_from_creds
    if not vertex_project:
        try:
            _, vertex_project = google.auth.default()
        except google.auth.exceptions.DefaultCredentialsError:
            pass

    if not vertex_project:
        raise RuntimeError(
            "Vertex AI project not found. Set VERTEX_PROJECT environment variable "
            "or ensure GOOGLE_APPLICATION_CREDENTIALS_JSON contains project_id."
        )

    return vertex_project


def initialize_services() -> GraphRAGServices:
    """
    Initialize Neo4j and Vertex AI connections.

    Returns:
        GraphRAGServices instance with initialized services

    Raises:
        RuntimeError: If initialization fails
    """
    # Setup credentials first
    project_id = setup_gcp_credentials()

    # Initialize Neo4j
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logger.info("Connected to Neo4j successfully")
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Neo4j: {e}") from e

    # Initialize Vertex AI
    try:
        vertex_project = resolve_vertex_project(project_id)
        vertex_location = os.getenv("VERTEX_LOCATION", "europe-west9")
        logger.info(
            f"Initializing Vertex AI with project={vertex_project}, location={vertex_location}"
        )
        vertexai.init(project=vertex_project, location=vertex_location)

        embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
        llm = VertexAILLM(model_name=LLM_MODEL, model_params={"temperature": 0.0})
        logger.info("Initialized Vertex AI models successfully")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Vertex AI: {e}") from e

    return GraphRAGServices(driver, embedder, llm)


def query_linkedin_graphrag(
    services: GraphRAGServices,
    query_text: str,
    use_cypher: bool = False,
    top_k: int = 5,
) -> str:
    """
    Query the GraphRAG system and return the answer.

    Args:
        services: Initialized GraphRAG services
        query_text: Natural language query
        use_cypher: If True, use VectorCypherRetriever (includes graph traversal)
        top_k: Number of results to retrieve

    Returns:
        Answer from the GraphRAG system
    """
    if not query_text.strip():
        return "⚠️ Please enter a query."

    try:
        # Create retriever using existing functions
        if use_cypher:
            retriever = create_vector_cypher_retriever(
                services.driver, services.embedder
            )
        else:
            retriever = create_vector_retriever(services.driver, services.embedder)

        # Create GraphRAG
        rag = GraphRAG(llm=services.llm, retriever=retriever)

        # Query
        response = rag.search(
            query_text=query_text,
            retriever_config={"top_k": top_k},
            return_context=True,
        )

        # Format response
        answer = response.answer

        # Add context preview if available
        if hasattr(response, "retriever_result") and response.retriever_result:
            if len(response.retriever_result.items) > 0:
                answer += f"\n\n---\n\n📊 **Retrieved {len(response.retriever_result.items)} relevant chunks**"

        return answer

    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        return f"❌ Error: {e}\n\nPlease check your configuration and ensure the content is indexed."


def get_database_stats(services: GraphRAGServices) -> str:
    """Get statistics about the indexed content."""
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

            # Format stats
            output = "**Database Statistics**\n\n"
            output += f"- Total Chunks: {chunk_count}\n"
            output += f"- Chunks with Embeddings: {chunk_with_embedding}\n"
            output += f"- Posts: {post_count}\n"
            output += f"- Comments: {comment_count}\n"

            if chunk_with_embedding == 0:
                output += "\n⚠️ **Warning**: No embeddings found! Please run `index_content.py` first."
            elif chunk_with_embedding < chunk_count:
                missing = chunk_count - chunk_with_embedding
                output += f"\n⚠️ **Warning**: {missing} chunks missing embeddings."

            return output

    except Exception as e:
        logger.error(f"Error getting database stats: {e}", exc_info=True)
        return f"❌ Error getting stats: {str(e)}"


def create_gradio_interface(services: GraphRAGServices):
    """
    Create and configure the Gradio interface.

    Args:
        services: Initialized GraphRAG services
    """

    # Create closures to capture services
    def query_fn(query_text: str, use_cypher: bool, top_k: int) -> str:
        return query_linkedin_graphrag(services, query_text, use_cypher, top_k)

    def stats_fn() -> str:
        return get_database_stats(services)

    with gr.Blocks(title="LinkedIn GraphRAG Query", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
        # 🔍 LinkedIn GraphRAG Query Interface

        Query your indexed LinkedIn posts and comments using natural language.
        """
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
                        info="Enable to include related entities in the search",
                    )
                    top_k = gr.Slider(
                        minimum=1,
                        maximum=20,
                        value=5,
                        step=1,
                        label="Number of Results (top_k)",
                    )

                submit_btn = gr.Button("🔍 Search", variant="primary", size="lg")

            with gr.Column(scale=1):
                stats_output = gr.Markdown(value=stats_fn())
                refresh_stats = gr.Button("🔄 Refresh Stats", size="sm")

        answer_output = gr.Markdown(label="Answer")

        # Example queries
        gr.Markdown("### 💡 Example Queries")
        gr.Examples(
            examples=[
                ["What topics do I post about most frequently?", False, 5],
                ["Show me posts about AI or machine learning", False, 10],
                ["What are my most engaging posts?", True, 5],
                ["Who are the most active commenters on my posts?", True, 10],
            ],
            inputs=[query_input, use_cypher, top_k],
        )

        # Event handlers
        submit_btn.click(
            fn=query_fn,
            inputs=[query_input, use_cypher, top_k],
            outputs=answer_output,
        )

        query_input.submit(
            fn=query_fn,
            inputs=[query_input, use_cypher, top_k],
            outputs=answer_output,
        )

        refresh_stats.click(fn=stats_fn, outputs=stats_output)

    return demo


def main():
    """Launch the Gradio app."""
    try:
        services = initialize_services()
    except RuntimeError as e:
        logger.error(f"Initialization failed: {e}")
        raise

    demo = create_gradio_interface(services)

    # Get port from environment (for Scalingo deployment)
    port = int(os.getenv("PORT", 7860))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting Gradio app on {host}:{port}")
    demo.launch(server_name=host, server_port=port, share=False, show_error=True)


if __name__ == "__main__":
    main()
