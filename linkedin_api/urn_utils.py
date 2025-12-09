"""
Utilities for converting LinkedIn URNs to HTML URLs.

LinkedIn uses URN (Uniform Resource Name) syntax in their API responses,
which need to be converted to standard URLs for accessing HTML pages.
"""

from typing import Optional


def extract_urn_id(urn: str) -> Optional[str]:
    """
    Extract the ID portion from a LinkedIn URN.
    
    Examples:
        urn:li:person:k_ho7OlN0r -> k_ho7OlN0r
        urn:li:ugcPost:7398404729531285504 -> 7398404729531285504
        urn:li:organization:123456 -> 123456
    
    Args:
        urn: The LinkedIn URN string
        
    Returns:
        The ID portion of the URN, or None if invalid
    """
    if not urn or not isinstance(urn, str):
        return None
    
    if ':' not in urn:
        return urn
    
    parts = urn.split(':')
    if len(parts) < 4:
        return None
    
    return parts[-1]


def urn_to_post_url(urn: str) -> Optional[str]:
    """
    Convert a LinkedIn post URN to a public HTML URL.
    
    LinkedIn post URLs use the format:
    https://www.linkedin.com/feed/update/{urn}
    
    Examples:
        urn:li:ugcPost:7398404729531285504 
        -> https://www.linkedin.com/feed/update/urn:li:ugcPost:7398404729531285504
        urn:li:share:7398404729531285504
        -> https://www.linkedin.com/feed/update/urn:li:share:7398404729531285504
        urn:li:activity:7398038757779730432
        -> https://www.linkedin.com/feed/update/urn:li:activity:7398038757779730432
    
    Note: This format has been validated and works correctly. The URL
    will load the actual post HTML page if the post is public.
    
    Args:
        urn: The post URN (e.g., "urn:li:ugcPost:...", "urn:li:share:...", "urn:li:activity:...")
        
    Returns:
        The public LinkedIn post URL, or None if invalid
    """
    if not urn:
        return None
    
    # LinkedIn post URLs use the full URN in the path
    # Handle different URN formats: ugcPost, share, activity
    if any(urn.startswith(prefix) for prefix in ['urn:li:ugcPost:', 'urn:li:share:', 'urn:li:activity:']):
        return f"https://www.linkedin.com/feed/update/{urn}"
    
    # Handle other LinkedIn URNs
    if urn.startswith('urn:li:'):
        return f"https://www.linkedin.com/feed/update/{urn}"
    
    return None


def urn_to_profile_url(urn: str, use_api: bool = False) -> Optional[str]:
    """
    Convert a LinkedIn person URN to a profile URL.
    
    Note: LinkedIn profiles use vanity URLs (e.g., /in/john-doe/) which
    are not directly derivable from the URN. Validation shows that the
    legacy format redirects to login page and does not work.
    
    To get the actual profile URL:
    1. Use LinkedIn API to fetch profile details
    2. Extract the 'publicIdentifier' field
    3. Construct: https://www.linkedin.com/in/{publicIdentifier}
    
    Use get_profile_vanity_url_from_api() for API-based lookup.
    
    Examples:
        urn:li:person:k_ho7OlN0r
        -> https://www.linkedin.com/in/{vanity-url} (requires API lookup)
        -> Legacy format redirects to login (does not work)
    
    Args:
        urn: The person URN (e.g., "urn:li:person:k_ho7OlN0r")
        use_api: If True, should use API to get vanity URL (not implemented)
        
    Returns:
        A LinkedIn profile URL (legacy format, redirects to login - use API instead)
    """
    if not urn:
        return None
    
    if not urn.startswith('urn:li:person:'):
        return None
    
    person_id = extract_urn_id(urn)
    if not person_id:
        return None
    
    if use_api:
        # TODO: Implement API call to get vanity URL
        # This would require calling LinkedIn API to fetch profile details
        # and extract the public profile URL
        raise NotImplementedError(
            "API-based profile URL lookup not implemented. "
            "Use LinkedIn API to fetch profile and get 'publicIdentifier' field."
        )
    
    # Legacy format - may not work for all profiles
    # LinkedIn now uses vanity URLs, but this might redirect
    return f"https://www.linkedin.com/profile/view?id={person_id}"


def get_profile_vanity_url_from_api(session, person_urn: str) -> Optional[str]:
    """
    Fetch the actual vanity URL for a profile using LinkedIn API.
    
    This requires making an API call to get profile details, which includes
    the 'publicIdentifier' field that contains the vanity URL.
    
    Args:
        session: A requests.Session with LinkedIn API authentication
        person_urn: The person URN (e.g., "urn:li:person:k_ho7OlN0r")
        
    Returns:
        The vanity URL (e.g., "john-doe") or None if not found
    """
    if not person_urn.startswith('urn:li:person:'):
        return None
    
    person_id = extract_urn_id(person_urn)
    if not person_urn:
        return None
    
    try:
        # Use LinkedIn API to fetch profile
        # Note: This requires appropriate API permissions
        response = session.get(
            f"https://api.linkedin.com/v2/people/(id:{person_id})",
            params={"projection": "(id,publicIdentifier)"}
        )
        
        if response.status_code == 200:
            data = response.json()
            vanity_url = data.get('publicIdentifier')
            if vanity_url:
                return f"https://www.linkedin.com/in/{vanity_url}"
    except Exception:
        pass
    
    return None


def urn_to_url(urn: str, urn_type: Optional[str] = None) -> Optional[str]:
    """
    Convert any LinkedIn URN to its corresponding HTML URL.
    
    Automatically detects the URN type and converts accordingly.
    
    Args:
        urn: The LinkedIn URN
        urn_type: Optional hint for URN type ('post', 'person', 'organization', etc.)
                  If None, will try to detect from URN prefix
        
    Returns:
        The corresponding LinkedIn HTML URL, or None if conversion not possible
    """
    if not urn:
        return None
    
    # Auto-detect type if not provided
    if not urn_type:
        if urn.startswith('urn:li:ugcPost:'):
            urn_type = 'post'
        elif urn.startswith('urn:li:person:'):
            urn_type = 'person'
        elif urn.startswith('urn:li:organization:'):
            urn_type = 'organization'
        elif urn.startswith('urn:li:'):
            # Generic LinkedIn URN - try post format
            urn_type = 'post'
        else:
            return None
    
    if urn_type == 'post':
        return urn_to_post_url(urn)
    elif urn_type == 'person':
        return urn_to_profile_url(urn, use_api=False)
    elif urn_type == 'organization':
        org_id = extract_urn_id(urn)
        if org_id:
            return f"https://www.linkedin.com/company/{org_id}"
    
    return None
