#!/usr/bin/env python3
"""
Extract posts, likes, and saved posts from LinkedIn Member Data Portability API
"""

import json
from collections import Counter
from linkedin_api.auth import build_linkedin_session, get_access_token


BASE_URL = "https://api.linkedin.com/rest"


def get_recent_changelog_data():
    """Get recent changelog data to see if posts/likes/saves are tracked there."""
    
    access_token = get_access_token()
    if not access_token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found")
        print("   Run 'python3 setup_token.py' to store it in Keychain, or set it as an environment variable")
        return
    
    print("\n🔍 Getting recent changelog data...")
    session = build_linkedin_session(access_token)

    resource_counts = Counter()
    reaction_counts = Counter()
    
    try:
        response = session.get(
            f"{BASE_URL}/memberChangeLogs",
            params={"q": "memberAndApplication", "count": 50},
        )
        
        if response.status_code == 200:
            data = response.json()
            elements = data.get('elements', [])
            
            print(f"✅ Got {len(elements)} changelog elements")
            
            # Look for post/like/save related activities
            for element in elements:
                resource_counts[element.get('resourceName', '')] += 1
                resource_name = element.get('resourceName', '')
                
                if "socialActions/likes" in resource_name:
                    activity = element.get('activity', {})
                    reaction_counts[activity.get('reactionType', 'n/a')] += 1
                elif "invitations" in resource_name:
                    activity = element.get('activity', {})
                    print(f"Invitation activity: {activity}")
                elif "ugcPosts" in resource_name:
                    activity = element.get('activity', {})
                    print(f"UGC post activity: {activity}")

        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        
    print(f"Reaction counts: {reaction_counts}")
    return resource_counts

def main():
    """Main function to extract and analyze LinkedIn data."""
    print("🚀 LinkedIn Data Extraction")
    print("=" * 50)
    # Get changelog data
    changelog_data = get_recent_changelog_data()
    print(changelog_data)
    print(f"\n" + "=" * 50)
    print("🎯 Next steps:")
    print("• If posts/likes/saves are found, we can create specific extractors")
    print("• If not found in snapshot, they might be in different endpoints")
    print("• Check LinkedIn API documentation for specific data types")

if __name__ == "__main__":
    main()
