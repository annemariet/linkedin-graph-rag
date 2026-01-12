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
    urn_to_url,
    urn_to_post_url,
    urn_to_profile_url,
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

    # Extract profile URL (actor)
    profile_urn = sample_reaction["actor"]
    print(f"\n👤 Profile URN: {profile_urn}")
    profile_url = urn_to_profile_url(profile_urn)
    print(f"   ⚠️  Profile URL (legacy): {profile_url}")
    print(f"   💡 Note: This legacy format may not work.")
    print(f"   💡 For actual profile URL, use LinkedIn API to get 'publicIdentifier'")

    # Extract just the ID
    person_id = extract_urn_id(profile_urn)
    print(f"\n🆔 Extracted Person ID: {person_id}")

    post_id = extract_urn_id(post_urn)
    print(f"🆔 Extracted Post ID: {post_id}")

    # Using the generic converter
    print(f"\n🔧 Using generic urn_to_url() converter:")
    print(f"   Post: {urn_to_url(post_urn)}")
    print(f"   Person: {urn_to_url(profile_urn)}")

    # Additional examples
    print(f"\n📚 Additional Examples:")

    examples = [
        ("urn:li:ugcPost:1234567890", "post"),
        ("urn:li:person:ABC123", "person"),
        ("urn:li:organization:456789", "organization"),
    ]

    for urn, expected_type in examples:
        url = urn_to_url(urn)
        print(f"   {urn}")
        print(f"   → {url}")

    print(f"\n" + "=" * 60)
    print("💡 Key Points:")
    print("   • Post URLs: Use full URN in path")
    print("   • Profile URLs: Require API lookup for vanity URL")
    print("   • Organization URLs: Use numeric ID in path")
    print("   • All URLs can be opened in browser to view HTML")


if __name__ == "__main__":
    main()
