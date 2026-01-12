# LinkedIn Graph Data Extraction

A Python client for extracting LinkedIn activity data from the Member Data Portability API and building a Neo4j knowledge graph.

## Features

- ✅ Fetch post-related activities (posts, comments, reactions)
- ✅ Extract entities and relationships for Neo4j
- ✅ Enrich posts with author profiles
- ✅ Extract and link external resources (articles, videos, repos)
- ✅ Build Neo4j knowledge graph
- ✅ Query graph with GraphRAG

## Setup

### 1. Install Dependencies

This project uses `uv` for dependency management:

```bash
uv sync
```

This installs Python 3.12 (if needed) and all dependencies.

### 2. Get LinkedIn Access Token

1. Go to [LinkedIn Developers](https://www.linkedin.com/developers/)
2. Create a new app
3. Get OAuth 2.0 access token with `r_dma_portability_self_serve` scope
4. Get token from: https://www.linkedin.com/developers/tools/oauth?clientId=78bwhum7gz6t9t

**Note:** Tokens expire every ~60 days. You'll need to regenerate them.

### 3. Configure Access Token

**Recommended: Store in Keychain (macOS)**

```bash
uv run python setup_token.py
```

This securely stores your token in macOS Keychain.

**Alternative: Environment Variable**

```bash
export LINKEDIN_ACCESS_TOKEN=your_access_token_here
```

### 4. Configure Neo4j

Set environment variables (or use defaults):

```bash
export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password
export NEO4J_DATABASE=neo4j
```

Or create a `.env` file:

```bash
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

## Building the Graph

### Step-by-Step Workflow

#### Step 1: Extract Graph Data

Fetch LinkedIn changelog data and extract entities/relationships:

```bash
uv run python -m linkedin_api.extract_graph_data
```

**What it does:**
- Fetches post-related activities from LinkedIn API (posts, comments, reactions)
- Extracts entities: Posts, People, Comments, Reactions
- Extracts relationships: CREATES, REPOSTS, REACTS_TO, COMMENTED_ON, etc.
- Saves to `neo4j_data_YYYYMMDD_HHMMSS.json`

**Output:** `neo4j_data_*.json` file with nodes and relationships ready for Neo4j import.

#### Step 2: Build Graph in Neo4j

Load the extracted data into Neo4j and enrich with additional information:

```bash
uv run python -m linkedin_api.build_graph neo4j_data_YYYYMMDD_HHMMSS.json
```

Or use the most recent file automatically:

```bash
uv run python -m linkedin_api.build_graph
```

**What it does:**
1. Loads nodes and relationships from JSON into Neo4j
2. Enriches Post nodes with author information (name, profile URL) by scraping LinkedIn
3. Extracts external resources (articles, videos, GitHub repos) from post/comment content
4. Creates Resource nodes and REFERENCES relationships

**Options:**
- `--skip-cleanup`: Merge new data with existing graph (preserves author info, resources)
- Without flag: Cleans database and creates fresh graph

**Example with incremental update:**

```bash
uv run python -m linkedin_api.build_graph --skip-cleanup
```

#### Step 3: Query the Graph

Query the graph using GraphRAG:

```bash
uv run python -m linkedin_api.query_graphrag
```

## Scripts Overview

### Main Scripts

- **`extract_graph_data.py`** - Step 1: Fetch and extract graph data to JSON
- **`build_graph.py`** - Step 2: Load JSON into Neo4j and enrich
- **`query_graphrag.py`** - Query the graph with GraphRAG
- **`analyze_activity.py`** - Analyze all LinkedIn activity (exploration tool)

### Utility Modules

- **`enrich_profiles.py`** - Extract author profiles from LinkedIn URLs
- **`extract_resources.py`** - Extract external resources from content
- **`utils/`** - Shared utilities (auth, changelog fetching, URN conversion, etc.)

## Usage Examples

### Complete Workflow (First Time)

```bash
# 1. Extract data
uv run python -m linkedin_api.extract_graph_data

# 2. Build graph (fresh)
uv run python -m linkedin_api.build_graph

# 3. Query graph
uv run python -m linkedin_api.query_graphrag
```

### Incremental Update

```bash
# 1. Extract new data
uv run python -m linkedin_api.extract_graph_data

# 2. Merge with existing graph (preserves author info, resources)
uv run python -m linkedin_api.build_graph --skip-cleanup
```

### Explore Activity Data

```bash
# Analyze all LinkedIn activity (not just posts)
uv run python -m linkedin_api.analyze_activity
```

## Graph Schema

### Nodes

- **Post**: LinkedIn posts (original, reposts)
  - Properties: `urn`, `post_id`, `url`, `content`, `type`, `timestamp`
- **Person**: People (authors, actors)
  - Properties: `urn`, `person_id`, `name`, `profile_url`
- **Comment**: Comments on posts
  - Properties: `urn`, `text`, `timestamp`
- **Reaction**: Reactions/likes
  - Properties: `urn`, `reaction_type`, `timestamp`
- **Resource**: External resources (articles, videos, repos)
  - Properties: `url`, `type`, `title`

### Relationships

- `Person CREATES Post`
- `Person REPOSTS Post`
- `Person REACTS_TO Post`
- `Person CREATED Comment`
- `Comment COMMENTED_ON Post` (top-level)
- `Comment COMMENTED_ON Comment` (replies)
- `Post REFERENCES Resource`
- `Comment REFERENCES Resource`

## Troubleshooting

### Token Expired

If you see `401 Unauthorized` or `EXPIRED_ACCESS_TOKEN`:

1. Get a new token from: https://www.linkedin.com/developers/tools/oauth?clientId=78bwhum7gz6t9t
2. Update it: `uv run python setup_token.py`

### Neo4j Connection Issues

```bash
# Check connection
uv run python check_token.py

# Verify Neo4j is running
# Check NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD environment variables
```

### Rate Limiting

LinkedIn API has rate limits. If you hit them:
- Wait a few minutes and retry
- The scripts handle pagination automatically

## API References

- [LinkedIn Member Data Portability API](https://learn.microsoft.com/en-us/linkedin/dma/member-data-portability/shared/member-changelog-api?view=li-dma-data-portability-2025-11&tabs=http)
- [LinkedIn DMA Portability API Terms](https://www.linkedin.com/legal/l/portability-api-terms)

## Development Notes

### Changelog Data Structure

Each element from the API contains:
- `resourceName`: Type of resource (e.g., "ugcPosts", "socialActions/likes")
- `methodName`: Action (e.g., "CREATE")
- `activity`: Detailed activity data
- `actor`: Person who performed the action

### Resource Types

- `ugcPosts` / `ugcPost`: Posts
- `socialActions/likes`: Reactions
- `socialActions/comments`: Comments
- `messages`: DMs (not imported to graph)
- `invitations`: Connection invites (not imported to graph)
