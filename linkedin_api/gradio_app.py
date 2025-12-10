#!/usr/bin/env python3
"""
Gradio web interface for LinkedIn GraphRAG.

This provides a web UI for querying indexed LinkedIn content using GraphRAG.
"""

import os
import json
import logging
import tempfile
from pathlib import Path
import gradio as gr

# Handle Google Cloud credentials for cloud deployment
# If GOOGLE_APPLICATION_CREDENTIALS_JSON is set, write it to a temp file
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    try:
        # Create a persistent temp file for credentials
        creds_path = Path(tempfile.gettempdir()) / "gcp_credentials.json"
        with open(creds_path, 'w') as f:
            json.dump(json.loads(creds_json), f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_path)
        logging.info(f"Loaded GCP credentials from environment variable to {creds_path}")
    except Exception as e:
        logging.warning(f"Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")

# Import from existing query module
from linkedin_api.query_graphrag import (
    find_vector_index,
    create_vector_retriever,
    create_vector_cypher_retriever,
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    EMBEDDING_MODEL,
    LLM_MODEL,
    VECTOR_INDEX_NAME,
)
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings
from neo4j_graphrag.llm import VertexAILLM
from neo4j_graphrag.generation.graphrag import GraphRAG

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize connections on startup
try:
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    driver.verify_connectivity()
    logger.info("Connected to Neo4j successfully")
    
    embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
    llm = VertexAILLM(
        model_name=LLM_MODEL,
        model_params={"temperature": 0.0}
    )
    logger.info("Initialized Vertex AI models successfully")
except Exception as e:
    logger.error(f"Initialization failed: {str(e)}")
    raise


def query_linkedin_graphrag(query_text: str, use_cypher: bool = False, top_k: int = 5) -> str:
    """
    Query the GraphRAG system and return the answer.
    
    Args:
        query_text: Natural language query
        use_cypher: If True, use VectorCypherRetriever (includes graph traversal)
        top_k: Number of results to retrieve
        
    Returns:
        Answer from the GraphRAG system
    """
    try:
        if not query_text.strip():
            return "⚠️ Please enter a query."
        
        # Create retriever using existing functions
        if use_cypher:
            retriever = create_vector_cypher_retriever(driver, embedder)
        else:
            retriever = create_vector_retriever(driver, embedder)
        
        # Create GraphRAG
        rag = GraphRAG(llm=llm, retriever=retriever)
        
        # Query
        response = rag.search(
            query_text=query_text,
            retriever_config={"top_k": top_k},
            return_context=True
        )
        
        # Format response
        answer = response.answer
        
        # Add context preview if available
        if hasattr(response, 'retriever_result') and response.retriever_result:
            if len(response.retriever_result.items) > 0:
                answer += f"\n\n---\n\n📊 **Retrieved {len(response.retriever_result.items)} relevant chunks**"
        
        return answer
        
    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        return f"❌ Error: {str(e)}\n\nPlease check your configuration and ensure the content is indexed."


def get_database_stats() -> str:
    """Get statistics about the indexed content."""
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            stats = {}
            
            # Count chunks
            chunk_count = session.run("MATCH (c:Chunk) RETURN count(c) as count").single()['count']
            stats['Total Chunks'] = chunk_count
            
            # Count chunks with embeddings
            chunk_with_embedding = session.run(
                "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
            ).single()['count']
            stats['Chunks with Embeddings'] = chunk_with_embedding
            
            # Count posts
            post_count = session.run("MATCH (p:Post) RETURN count(p) as count").single()['count']
            stats['Posts'] = post_count
            
            # Count comments
            comment_count = session.run("MATCH (c:Comment) RETURN count(c) as count").single()['count']
            stats['Comments'] = comment_count
            
            # Format stats
            output = "**Database Statistics**\n\n"
            for key, value in stats.items():
                output += f"- {key}: {value}\n"
            
            if chunk_with_embedding == 0:
                output += "\n⚠️ **Warning**: No embeddings found! Please run `index_content.py` first."
            elif chunk_with_embedding < chunk_count:
                output += f"\n⚠️ **Warning**: {chunk_count - chunk_with_embedding} chunks missing embeddings."
            
            return output
            
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"


# Create Gradio interface
with gr.Blocks(title="LinkedIn GraphRAG Query", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🔍 LinkedIn GraphRAG Query Interface
    
    Query your indexed LinkedIn posts and comments using natural language.
    """)
    
    with gr.Row():
        with gr.Column(scale=2):
            query_input = gr.Textbox(
                label="Your Question",
                placeholder="What are the main themes in my LinkedIn posts?",
                lines=3
            )
            
            with gr.Row():
                use_cypher = gr.Checkbox(
                    label="Use Graph Traversal (Cypher)",
                    value=False,
                    info="Enable to include related entities in the search"
                )
                top_k = gr.Slider(
                    minimum=1,
                    maximum=20,
                    value=5,
                    step=1,
                    label="Number of Results (top_k)"
                )
            
            submit_btn = gr.Button("🔍 Search", variant="primary", size="lg")
            
        with gr.Column(scale=1):
            stats_output = gr.Markdown(value=get_database_stats())
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
        fn=query_linkedin_graphrag,
        inputs=[query_input, use_cypher, top_k],
        outputs=answer_output
    )
    
    query_input.submit(
        fn=query_linkedin_graphrag,
        inputs=[query_input, use_cypher, top_k],
        outputs=answer_output
    )
    
    refresh_stats.click(
        fn=get_database_stats,
        outputs=stats_output
    )


def main():
    """Launch the Gradio app."""
    # Get port from environment (for Scalingo deployment)
    port = int(os.getenv("PORT", 7860))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting Gradio app on {host}:{port}")
    
    demo.launch(
        server_name=host,
        server_port=port,
        share=False,
        show_error=True
    )


if __name__ == "__main__":
    main()
