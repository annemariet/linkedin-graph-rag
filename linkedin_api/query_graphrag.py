#!/usr/bin/env python3
"""
Query LinkedIn content using GraphRAG.

This script demonstrates how to use GraphRAG to query the indexed LinkedIn
post and comment content.
"""

import os
import dotenv
from typing import Optional
from neo4j import GraphDatabase

# Apply DNS fix before importing Google libraries
try:
    from linkedin_api.dns_utils import setup_gcp_dns_fix
    setup_gcp_dns_fix(use_custom_resolver=True)
except ImportError:
    pass

from neo4j_graphrag.embeddings.vertexai import VertexAIEmbeddings
from neo4j_graphrag.llm import VertexAILLM
from neo4j_graphrag.retrievers import VectorRetriever, VectorCypherRetriever
from neo4j_graphrag.generation.graphrag import GraphRAG

dotenv.load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neoneoneo")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "textembedding-gecko@002")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-pro")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "linkedin_content_index")


def find_vector_index(driver, preferred_name: str) -> Optional[str]:
    """
    Find a vector index, preferring the specified name but falling back to any available.
    
    Returns:
        Index name if found, None otherwise
    """
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            # First, try to find the preferred index
            result = session.run(
                "SHOW INDEXES WHERE type = 'VECTOR' AND name = $name",
                name=preferred_name
            )
            index_info = result.single()
            if index_info:
                print(f"   ✅ Found preferred index '{preferred_name}'")
                return preferred_name
            
            # If not found, list all vector indexes
            print(f"   ⚠️  Index '{preferred_name}' not found")
            all_indexes = session.run("SHOW INDEXES WHERE type = 'VECTOR'")
            indexes = list(all_indexes)
            if indexes:
                print(f"   Available vector indexes:")
                for idx in indexes:
                    idx_name = idx.get('name', 'unknown')
                    print(f"     • {idx_name}")
                
                # Auto-select if only one exists
                if len(indexes) == 1:
                    selected = indexes[0].get('name')
                    print(f"   ✅ Auto-selecting '{selected}' (only available index)")
                    return selected
                else:
                    # Use the first one that looks like a content index
                    for idx in indexes:
                        idx_name = idx.get('name', '')
                        if 'chunk' in idx_name.lower() or 'embedding' in idx_name.lower() or 'content' in idx_name.lower():
                            print(f"   ✅ Auto-selecting '{idx_name}' (looks like content index)")
                            return idx_name
                    
                    # Fall back to first available
                    selected = indexes[0].get('name')
                    print(f"   ⚠️  Auto-selecting '{selected}' (first available, may not be correct)")
                    return selected
            else:
                print(f"   ❌ No vector indexes found in database")
                return None
    except Exception as e:
        print(f"   ⚠️  Error checking index: {str(e)}")
        return None


def verify_index_exists(driver, index_name: str) -> bool:
    """Verify that the vector index exists in Neo4j."""
    found_name = find_vector_index(driver, index_name)
    return found_name is not None


def create_vector_retriever(driver, embedder):
    """Create a simple vector retriever."""
    # Find available index (may auto-select if preferred not found)
    actual_index_name = find_vector_index(driver, VECTOR_INDEX_NAME)
    if not actual_index_name:
        raise RuntimeError(
            f"No vector index found. "
            f"Please run index_content.py first to create the index."
        )
    
    if actual_index_name != VECTOR_INDEX_NAME:
        print(f"   ℹ️  Using index '{actual_index_name}' instead of '{VECTOR_INDEX_NAME}'")
    
    return VectorRetriever(
        driver,
        index_name=actual_index_name,
        embedder=embedder,
        return_properties=["text", "chunk_index", "source_urn"],
    )


def create_vector_cypher_retriever(driver, embedder):
    """Create a vector + Cypher retriever that traverses the graph."""
    # Find available index (may auto-select if preferred not found)
    actual_index_name = find_vector_index(driver, VECTOR_INDEX_NAME)
    if not actual_index_name:
        raise RuntimeError(
            f"No vector index found. "
            f"Please run index_content.py first to create the index."
        )
    
    if actual_index_name != VECTOR_INDEX_NAME:
        print(f"   ℹ️  Using index '{actual_index_name}' instead of '{VECTOR_INDEX_NAME}'")
    
    return VectorCypherRetriever(
        driver,
        index_name=actual_index_name,
        embedder=embedder,
        retrieval_query="""
        // Get the chunk and traverse to related entities
        WITH node AS chunk
        MATCH (chunk)-[:FROM_CHUNK]->(source)
        OPTIONAL MATCH (source)<-[:REACTS_TO|COMMENTS_ON|CREATES|REPOSTS]-(person:Person)
        OPTIONAL MATCH (source)-[:REPOSTS]->(original:Post)
        
        // Collect all related information
        WITH collect(DISTINCT chunk) AS chunks,
             collect(DISTINCT source) AS sources,
             collect(DISTINCT person) AS people,
             collect(DISTINCT original) AS originals
        
        // Format context (using string concatenation instead of apoc.text.join for compatibility)
        WITH chunks, sources, people, originals,
             reduce(text = '', c IN chunks | text + 
                CASE WHEN text = '' THEN '' ELSE '\n---\n' END + c.text
             ) AS content_text,
             reduce(text = '', s IN sources | text + 
                CASE WHEN text = '' THEN '' ELSE '\n' END + s.urn + ' (' + labels(s)[0] + ')'
             ) AS source_text,
             reduce(text = '', p IN people | text + 
                CASE WHEN text = '' THEN '' ELSE '\n' END + p.urn
             ) AS people_text,
             reduce(text = '', o IN originals | text + 
                CASE WHEN text = '' THEN '' ELSE '\n' END + o.urn
             ) AS original_text
        
        RETURN '=== Post/Comment Content ===\n' + content_text + 
               '\n\n=== Source Info ===\n' + source_text +
               CASE WHEN people_text <> '' THEN 
                   '\n\n=== Related People ===\n' + people_text
               ELSE '' END +
               CASE WHEN original_text <> '' THEN 
                   '\n\n=== Reposted From ===\n' + original_text
               ELSE '' END AS info
        """
    )


def query_graphrag(query_text: str, use_cypher: bool = False, top_k: int = 5):
    """
    Query the GraphRAG system.
    
    Args:
        query_text: Natural language query
        use_cypher: If True, use VectorCypherRetriever, else VectorRetriever
        top_k: Number of results to retrieve
    """
    print(f"🚀 LinkedIn GraphRAG Query")
    print("=" * 60)
    print(f"\n📝 Query: {query_text}")
    print(f"   Retriever: {'Vector + Cypher' if use_cypher else 'Vector'}")
    print(f"   Top K: {top_k}")
    
    # Connect to Neo4j
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    
    try:
        driver.verify_connectivity()
        print(f"   Database: {NEO4J_DATABASE}")
        
        # Initialize embedder and LLM - fail immediately on error
        try:
            embedder = VertexAIEmbeddings(model=EMBEDDING_MODEL)
            # Test embedder
            test_embedding = embedder.embed_query("test")
            if not test_embedding or len(test_embedding) == 0:
                raise ValueError("Embedder returned empty test embedding")
        except Exception as e:
            print(f"\n❌ FATAL ERROR: Failed to initialize embedder")
            print(f"   Error: {str(e)}")
            print(f"   Model: {EMBEDDING_MODEL}")
            print(f"\n💡 Try a different model: textembedding-gecko@002 or textembedding-gecko")
            raise RuntimeError(f"Embedder initialization failed: {str(e)}") from e
        
        try:
            llm = VertexAILLM(
                model_name=LLM_MODEL,
                model_params={"temperature": 0.0}
            )
        except Exception as e:
            print(f"\n❌ FATAL ERROR: Failed to initialize LLM")
            print(f"   Error: {str(e)}")
            print(f"   Model: {LLM_MODEL}")
            raise RuntimeError(f"LLM initialization failed: {str(e)}") from e
        
        # Create retriever
        if use_cypher:
            retriever = create_vector_cypher_retriever(driver, embedder)
        else:
            retriever = create_vector_retriever(driver, embedder)
        
        # Debug: Check if chunks exist and have embeddings
        print(f"\n🔍 Verifying chunks in database...")
        with driver.session(database=NEO4J_DATABASE) as session:
            chunk_count = session.run("MATCH (c:Chunk) RETURN count(c) as count").single()['count']
            chunk_with_embedding = session.run(
                "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"
            ).single()['count']
            print(f"   Total Chunk nodes: {chunk_count}")
            print(f"   Chunks with embeddings: {chunk_with_embedding}")
            
            if chunk_count == 0:
                print(f"   ⚠️  No chunks found! Run index_content.py first.")
            elif chunk_with_embedding == 0:
                print(f"   ⚠️  Chunks exist but no embeddings found!")
            elif chunk_with_embedding < chunk_count:
                print(f"   ⚠️  Warning: {chunk_count - chunk_with_embedding} chunks missing embeddings")
        
        # Create GraphRAG
        rag = GraphRAG(llm=llm, retriever=retriever)
        
        # Query
        print(f"\n🔍 Searching...")
        
        # Test the retriever directly first
        print(f"   Testing retriever directly...")
        try:
            test_results = retriever.get_search_results(query_text=query_text, top_k=top_k)
            print(f"   ✅ Retriever returned {len(test_results.records)} results")
            if len(test_results.records) == 0:
                print(f"   ⚠️  WARNING: Retriever found no results!")
                print(f"   This could mean:")
                print(f"     • No chunks match the query semantically")
                print(f"     • Embeddings aren't properly stored")
                print(f"     • Vector index isn't working correctly")
                print(f"   Trying a very generic query to test...")
                # Try a very generic query
                generic_results = retriever.get_search_results(query_text="post", top_k=3)
                print(f"   Generic query 'post' returned {len(generic_results.records)} results")
                if len(generic_results.records) > 0:
                    print(f"   Sample result:")
                    sample = generic_results.records[0]
                    print(f"     {sample.data()}")
        except Exception as retriever_error:
            print(f"   ❌ Error testing retriever: {str(retriever_error)}")
            import traceback
            traceback.print_exc()
        
        response = rag.search(
            query_text=query_text,
            retriever_config={"top_k": top_k},
            return_context=True
        )
        
        # Display results
        print(f"\n{'='*60}")
        print(f"💬 ANSWER")
        print(f"{'='*60}")
        print(response.answer)
        
        # Show context if available
        if hasattr(response, 'retriever_result') and response.retriever_result:
            print(f"\n{'='*60}")
            print(f"📚 RETRIEVED CONTEXT")
            print(f"{'='*60}")
            if len(response.retriever_result.items) == 0:
                print(f"   ⚠️  No context retrieved!")
                print(f"   The retriever found no matching chunks.")
            else:
                for i, item in enumerate(response.retriever_result.items[:3], 1):
                    print(f"\n--- Context {i} ---")
                    if hasattr(item, 'content'):
                        content = item.content
                        # Truncate if too long
                        if len(content) > 500:
                            print(content[:500] + "...")
                        else:
                            print(content)
                    elif hasattr(item, 'data'):
                        print(item.data())
        else:
            print(f"\n{'='*60}")
            print(f"📚 RETRIEVED CONTEXT")
            print(f"{'='*60}")
            print(f"   ⚠️  No retriever_result available")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        driver.close()


def interactive_query():
    """Interactive query interface."""
    print("🚀 LinkedIn GraphRAG Interactive Query")
    print("=" * 60)
    print("\nEnter queries to search your LinkedIn content.")
    print("Commands:")
    print("  - Type your question and press Enter")
    print("  - 'cypher' to toggle Cypher retriever")
    print("  - 'topk <number>' to set top_k")
    print("  - 'quit' or 'exit' to exit")
    print()
    
    use_cypher = False
    top_k = 5
    
    while True:
        try:
            query = input("Query> ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if query.lower() == 'cypher':
                use_cypher = not use_cypher
                print(f"   {'✅' if use_cypher else '❌'} Cypher retriever: {'enabled' if use_cypher else 'disabled'}")
                continue
            
            if query.lower().startswith('topk '):
                try:
                    top_k = int(query.split()[1])
                    print(f"   ✅ Top K set to {top_k}")
                except:
                    print("   ❌ Invalid number")
                continue
            
            query_graphrag(query, use_cypher=use_cypher, top_k=top_k)
            print()
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {str(e)}")


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 1:
        # Command line query
        query = " ".join(sys.argv[1:])
        use_cypher = '--cypher' in sys.argv
        query_graphrag(query, use_cypher=use_cypher)
    else:
        # Interactive mode
        interactive_query()


if __name__ == "__main__":
    main()
