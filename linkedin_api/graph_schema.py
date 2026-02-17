"""
Graph schema definition for LinkedIn knowledge graph.

Single source of truth for node types, relationship types, and allowed patterns.
Used by:
- build_graph.py (Phase A: structural graph from CSV)
- enrich_graph.py (Phase B: LLM-powered enrichment via SimpleKGPipeline)
- migrate_schema.py (relationship renames)
- query_graphrag.py (retrieval queries)
"""

# -- Node types ----------------------------------------------------------

NODE_TYPES = [
    {
        "label": "Person",
        "description": "A LinkedIn member identified by URN.",
        "properties": [
            {"name": "urn", "type": "STRING", "required": True},
            {"name": "person_id", "type": "STRING"},
            {"name": "author_name", "type": "STRING"},
            {"name": "author_url", "type": "STRING"},
        ],
    },
    {
        "label": "Post",
        "description": "A message starting a conversation on LinkedIn.",
        "properties": [
            {"name": "urn", "type": "STRING", "required": True},
            {"name": "post_id", "type": "STRING"},
            {"name": "url", "type": "STRING"},
            {"name": "content", "type": "STRING"},
            {"name": "created_at", "type": "STRING"},
            {"name": "type", "type": "STRING"},
        ],
    },
    {
        "label": "Comment",
        "description": "A message appended by a Person to a Post or another Comment.",
        "properties": [
            {"name": "urn", "type": "STRING", "required": True},
            {"name": "comment_id", "type": "STRING"},
            {"name": "text", "type": "STRING"},
            {"name": "url", "type": "STRING"},
            {"name": "created_at", "type": "STRING"},
        ],
    },
    {
        "label": "Resource",
        "description": "A related learning resource (article, video, repository, etc.).",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
            {"name": "type", "type": "STRING"},
            {"name": "url", "type": "STRING"},
        ],
    },
    {
        "label": "Technology",
        "description": "A technology, framework, library, or tool mentioned in content.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Concept",
        "description": "An abstract idea, methodology, or principle discussed in content.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Process",
        "description": "A workflow, procedure, or series of steps.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Challenge",
        "description": "A difficulty, limitation, or problem encountered.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Benefit",
        "description": "A positive outcome or advantage.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
    {
        "label": "Example",
        "description": "A concrete use-case, demo, or real-world application.",
        "properties": [
            {"name": "name", "type": "STRING", "required": True},
        ],
    },
]

# -- Relationship types ---------------------------------------------------

RELATIONSHIP_TYPES = [
    "IS_AUTHOR_OF",
    "REACTED_TO",
    "COMMENTS_ON",
    "REFERENCES",
    "CREATED",
    "RELATED_TO",
    "PART_OF",
    "USED_IN",
    "LEADS_TO",
    "HAS_CHALLENGE",
    "CITES",
    "REPOSTS",
]

# Phase A relationships: structural graph from CSV (build_graph.py)
PHASE_A_RELATIONSHIP_TYPES = [
    "IS_AUTHOR_OF",
    "REACTED_TO",
    "COMMENTS_ON",
    "REPOSTS",
]

# -- Allowed triple patterns ----------------------------------------------

PATTERNS = [
    # Structural (Phase A -- from CSV)
    ("Person", "IS_AUTHOR_OF", "Post"),
    ("Person", "IS_AUTHOR_OF", "Comment"),
    ("Person", "REACTED_TO", "Post"),
    ("Person", "REACTED_TO", "Comment"),
    ("Comment", "COMMENTS_ON", "Comment"),
    ("Comment", "COMMENTS_ON", "Post"),
    ("Post", "REPOSTS", "Post"),
    ("Person", "REPOSTS", "Post"),
    # Enrichment (Phase B -- from SimpleKGPipeline)
    ("Post", "REFERENCES", "Resource"),
    ("Comment", "REFERENCES", "Resource"),
    ("Resource", "REFERENCES", "Resource"),
    ("Person", "CREATED", "Resource"),
    ("Technology", "RELATED_TO", "Technology"),
    ("Concept", "RELATED_TO", "Technology"),
    ("Example", "USED_IN", "Technology"),
    ("Process", "PART_OF", "Technology"),
    ("Technology", "HAS_CHALLENGE", "Challenge"),
    ("Concept", "HAS_CHALLENGE", "Challenge"),
    ("Technology", "LEADS_TO", "Benefit"),
    ("Process", "LEADS_TO", "Benefit"),
    ("Resource", "CITES", "Technology"),
]

# -- Helpers ---------------------------------------------------------------

_NODE_LABELS = {nt["label"] for nt in NODE_TYPES}


def get_node_labels() -> set[str]:
    """Return the set of all defined node labels."""
    return set(_NODE_LABELS)


def get_pipeline_schema() -> dict:
    """Return schema dict for neo4j-graphrag SimpleKGPipeline.

    The returned dict has keys ``entities``, ``relations``, and
    ``potential_schema`` matching what SimpleKGPipeline expects.
    """
    entities = []
    for nt in NODE_TYPES:
        entry: dict = {
            "label": nt["label"],
            "description": nt.get("description", ""),
        }
        props = nt.get("properties")
        if props:
            # SimpleKGPipeline only accepts str values in property dicts;
            # strip out non-str keys like "required" (bool).
            entry["properties"] = [
                {k: v for k, v in p.items() if isinstance(v, str)} for p in props
            ]
        entities.append(entry)

    relations = []
    for rt in RELATIONSHIP_TYPES:
        relations.append({"label": rt})

    return {
        "entities": entities,
        "relations": relations,
        "potential_schema": PATTERNS,
    }
