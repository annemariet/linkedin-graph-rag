"""Minimal Vertex AI smoke test.

Set env vars before running:
- GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
- VERTEX_PROJECT=<gcp-project-id>
- VERTEX_LOCATION=<gcp-region, e.g. us-central1>
"""

from __future__ import annotations

import os
import sys

# Add parent directory to path for DNS utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Apply DNS fix before importing Google libraries
try:
    from linkedin_api.dns_utils import setup_gcp_dns_fix, test_dns_resolution
    
    # Setup DNS fix for VPN issues
    setup_gcp_dns_fix(use_custom_resolver=True)
    
    # Test DNS resolution
    location = os.environ.get("VERTEX_LOCATION", "europe-west9")
    test_host = f"{location}-aiplatform.googleapis.com"
    if not test_dns_resolution(test_host):
        print(f"⚠️  Warning: DNS resolution for {test_host} may fail")
        print("   Consider installing dnspython: pip install dnspython")
except ImportError:
    print("⚠️  DNS utils not available, proceeding without DNS fix")

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
