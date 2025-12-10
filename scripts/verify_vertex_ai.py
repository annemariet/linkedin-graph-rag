"""Minimal Vertex AI smoke test.

Set env vars before running:
- GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
- VERTEX_PROJECT=<gcp-project-id>
- VERTEX_LOCATION=<gcp-region, e.g. us-central1>
"""

from __future__ import annotations

import os

import google.auth
import vertexai
from vertexai.preview.generative_models import GenerativeModel


def resolve_project() -> str:
    # Prefer explicit env override, else fall back to ADC project
    env_project = os.environ.get("VERTEX_PROJECT")
    if env_project:
        return env_project

    _, default_project = google.auth.default()
    if not default_project:
        raise RuntimeError(
            "No project found. Set VERTEX_PROJECT or configure gcloud ADC."
        )
    return default_project


def main() -> None:
    project = resolve_project()
    location = os.environ.get("VERTEX_LOCATION", "europe-west9")

    vertexai.init(project=project, location=location)

    model = GenerativeModel("gemini-2.5-flash-lite")
    resp = model.generate_content("Say 'pong' and nothing else.")
    print(f"Response: {resp.text!r}")


if __name__ == "__main__":
    main()
