#!/usr/bin/env python3
"""
Example: Converting LinkedIn URNs to HTML URLs

Demonstrates how to extract URLs from LinkedIn API responses
that use URN (Uniform Resource Name) syntax.

Run with: uv run examples/urn_to_url_example.py
"""

import sys
from pathlib import Path

# Add parent directory to path to import linkedin_api
sys.path.insert(0, str(Path(__file__).parent.parent))

from linkedin_api.utils.urns import (
    urn_to_post_url,
    extract_urn_id,
)


def main():
    """Example usage with sample LinkedIn API response data."""

    # Sample data from LinkedIn API (like your reaction data)
    sample_reaction = {
        "actor": "urn:li:person:k_ho7OlN0r",
        "reactionType": "LIKE",
        "created": {"actor": "urn:li:person:k_ho7OlN0r", "time": 1763996190957},
        "root": "urn:li:ugcPost:7398404729531285504",
        "lastModified": {"actor": "urn:li:person:k_ho7OlN0r", "time": 1763996190957},
    }

    print("🔗 LinkedIn URN to URL Conversion Examples")
    print("=" * 60)

    # Extract post URL
    post_urn = sample_reaction["root"]
    print(f"\n📝 Post URN: {post_urn}")
    post_url = urn_to_post_url(post_urn)
    print(f"   ✅ Post URL: {post_url}")
    print(f"   💡 You can open this URL in a browser to view the post HTML")

    # Extract just the ID
    profile_urn = sample_reaction["actor"]
    person_id = extract_urn_id(profile_urn)
    print(f"\n🆔 Extracted Person ID: {person_id}")

    post_id = extract_urn_id(post_urn)
    print(f"🆔 Extracted Post ID: {post_id}")

    # Additional examples
    print(f"\n📚 Additional Examples:")

    examples = [
        "urn:li:ugcPost:1234567890",
        "urn:li:share:9876543210",
        "urn:li:activity:5555555555",
    ]

    for urn in examples:
        url = urn_to_post_url(urn)
        print(f"   {urn}")
        print(f"   → {url}")

    print(f"\n" + "=" * 60)
    print("💡 Key Points:")
    print("   • Post URLs use full URN in path")
    print("   • Profile URLs require API lookup for vanity URL (not implemented)")
    print("   • All post URLs can be opened in browser to view HTML")


if __name__ == "__main__":
    main()
