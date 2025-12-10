"""
Utilities for fetching LinkedIn changelog data with pagination support.

This module provides shared functions for fetching changelog data from the
LinkedIn Member Data Portability API, handling pagination, filtering, and errors.
"""

from typing import List, Optional, Callable
from linkedin_api.auth import build_linkedin_session, get_access_token


BASE_URL = "https://api.linkedin.com/rest"


def get_changelog_session():
    """
    Get an authenticated session for LinkedIn API requests.

    Returns:
        A requests.Session with LinkedIn API headers, or None if token is missing
    """
    access_token = get_access_token()
    if not access_token:
        return None

    return build_linkedin_session(access_token)


def fetch_changelog_data(
    resource_filter: Optional[List[str]] = None,
    filter_func: Optional[Callable[[dict], bool]] = None,
    batch_size: int = 50,
    verbose: bool = True,
) -> List[dict]:
    """
    Fetch all changelog data by paginating through all results.

    Args:
        resource_filter: Optional list of resource names to filter by.
                        Elements are included if any filter string is in resourceName.
        filter_func: Optional custom filter function that takes an element dict
                    and returns True to include it.
        batch_size: Number of elements to fetch per request (default: 50)
        verbose: If True, print progress messages (default: True)

    Returns:
        List of changelog elements. Empty list if token is missing or on error.
    """
    session = get_changelog_session()
    if not session:
        if verbose:
            print("❌ LINKEDIN_ACCESS_TOKEN not found")
            print(
                "   Run 'uv run setup_token.py' to store it in Keychain, or set it as an environment variable"
            )
        return []

    if verbose:
        print("🔍 Fetching all changelog data...")

    all_elements = []
    start = 0

    while True:
        try:
            if verbose:
                print(f"   📡 Fetching batch starting at {start}...")

            response = session.get(
                f"{BASE_URL}/memberChangeLogs",
                params={
                    "q": "memberAndApplication",
                    "start": start,
                    "count": batch_size,
                },
            )

            if response.status_code != 200:
                if verbose:
                    print(f"❌ Error: {response.status_code}")
                    print(f"Response: {response.text[:200]}...")
                break

            data = response.json()
            elements = data.get("elements", [])

            if not elements:
                if verbose:
                    print("✅ No more data to fetch")
                break

            # Apply filters if provided
            if resource_filter:
                elements = [
                    e
                    for e in elements
                    if any(
                        resource.lower() in e.get("resourceName", "").lower()
                        for resource in resource_filter
                    )
                ]

            if filter_func:
                elements = [e for e in elements if filter_func(e)]

            all_elements.extend(elements)

            if verbose:
                total_filtered = len(all_elements)
                print(f"   ✅ Got {len(elements)} elements (total: {total_filtered})")

            # Check for more pages
            paging = data.get("paging", {})
            links = paging.get("links", [])
            next_link = None

            for link in links:
                if link.get("rel") == "next":
                    next_link = link.get("href")
                    break

            if not next_link:
                if verbose:
                    print("✅ No more pages")
                break

            start += batch_size

        except Exception as e:
            if verbose:
                print(f"❌ Exception: {str(e)}")
            break

    if verbose:
        print(f"✅ Total elements fetched: {len(all_elements)}")

    return all_elements
