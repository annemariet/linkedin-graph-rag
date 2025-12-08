#!/usr/bin/env python3
"""
Extract posts, likes, and saved posts from LinkedIn Member Data Portability API
"""

import os
import requests
import json
import keyring
import dotenv

dotenv.load_dotenv()

# SECURITY: Use keyring or environment variable
def get_access_token():
    """Get token from keyring or environment variable."""
    token = keyring.get_password("LINKEDIN_ACCESS_TOKEN", os.getenv('LINKEDIN_ACCOUNT'))
    if token:
        return token

    return os.getenv('LINKEDIN_ACCESS_TOKEN')

def get_all_snapshot_data():
    """Get all available snapshot data by paginating through all results."""
    
    access_token = get_access_token()
    if not access_token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found")
        print("   Run 'python3 setup_token.py' to store it in Keychain, or set it as an environment variable")
        return
    
    print("🔍 Getting all member snapshot data...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
        'LinkedIn-Version': '202312'
    }
    
    base_url = "https://api.linkedin.com/rest"
    all_data = []
    start = 0
    count = 50  # Get more data per request
    
    while True:
        print(f"📡 Fetching data from start={start}, count={count}")
        
        try:
            response = requests.get(
                f"{base_url}/memberSnapshotData",
                headers=headers,
                params={"q": "criteria", "start": start, "count": count}
            )
            
            if response.status_code != 200:
                print(f"❌ Error: {response.status_code}")
                print(f"Response: {response.text[:200]}...")
                break
            
            data = response.json()
            elements = data.get('elements', [])
            
            if not elements:
                print("✅ No more data to fetch")
                break
            
            all_data.extend(elements)
            print(f"   ✅ Got {len(elements)} elements (total: {len(all_data)})")
            
            # Check if there's more data
            paging = data.get('paging', {})
            links = paging.get('links', [])
            next_link = None
            
            for link in links:
                if link.get('rel') == 'next':
                    next_link = link.get('href')
                    break
            
            if not next_link:
                print("✅ No more pages")
                break
            
            start += count
            
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            break
    
    return all_data

def analyze_snapshot_data(data):
    """Analyze the snapshot data to find posts, likes, and saves."""
    
    print(f"\n🔍 Analyzing {len(data)} snapshot elements...")
    
    posts_data = []
    likes_data = []
    saves_data = []
    other_data = []
    
    for element in data:
        snapshot_data = element.get('snapshotData', [])
        snapshot_domain = element.get('snapshotDomain', '')
        
        print(f"\n📊 Domain: {snapshot_domain}")
        print(f"   Data items: {len(snapshot_data)}")
        
        for item in snapshot_data:
            # Look for different types of data
            if isinstance(item, dict):
                keys = list(item.keys())
                
                # Check for post-related data
                if any(key.lower() in ['post', 'content', 'text', 'article'] for key in keys):
                    posts_data.append({
                        'domain': snapshot_domain,
                        'data': item
                    })
                    print(f"   📝 Found post data: {keys}")
                
                # Check for like-related data
                elif any(key.lower() in ['like', 'reaction', 'thumb'] for key in keys):
                    likes_data.append({
                        'domain': snapshot_domain,
                        'data': item
                    })
                    print(f"   ❤️  Found like data: {keys}")
                
                # Check for save-related data
                elif any(key.lower() in ['save', 'bookmark', 'favorite'] for key in keys):
                    saves_data.append({
                        'domain': snapshot_domain,
                        'data': item
                    })
                    print(f"   💾 Found save data: {keys}")
                
                else:
                    other_data.append({
                        'domain': snapshot_domain,
                        'data': item
                    })
                    print(f"   📄 Other data: {keys}")
    
    return posts_data, likes_data, saves_data, other_data

def get_recent_changelog_data():
    """Get recent changelog data to see if posts/likes/saves are tracked there."""
    
    access_token = get_access_token()
    if not access_token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found")
        print("   Run 'python3 setup_token.py' to store it in Keychain, or set it as an environment variable")
        return
    
    print("\n🔍 Getting recent changelog data...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
        'LinkedIn-Version': '202312'
    }
    
    base_url = "https://api.linkedin.com/rest"
    
    try:
        response = requests.get(
            f"{base_url}/memberChangeLogs",
            headers=headers,
            params={"q": "memberAndApplication", "count": 50}
        )
        
        if response.status_code == 200:
            data = response.json()
            elements = data.get('elements', [])
            
            print(f"✅ Got {len(elements)} changelog elements")
            
            # Look for post/like/save related activities
            for element in elements:
                activity = element.get('activity', {})
                resource_name = element.get('resourceName', '')
                method_name = element.get('methodName', '')
                
                if any(keyword in resource_name.lower() or keyword in method_name.lower() 
                      for keyword in ['post', 'like', 'save', 'reaction', 'content']):
                    print(f"   🔍 Found relevant activity: {resource_name} - {method_name}")
                    print(f"      Activity: {json.dumps(activity, indent=2)[:300]}...")
            
            return elements
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
    
    return []

def main():
    """Main function to extract and analyze LinkedIn data."""
    print("🚀 LinkedIn Data Extraction")
    print("=" * 50)
    
    # Get all snapshot data
    snapshot_data = get_all_snapshot_data()
    
    if snapshot_data:
        # Analyze the data
        posts, likes, saves, other = analyze_snapshot_data(snapshot_data)
        
        print(f"\n📊 Summary:")
        print(f"   📝 Posts found: {len(posts)}")
        print(f"   ❤️  Likes found: {len(likes)}")
        print(f"   💾 Saves found: {len(saves)}")
        print(f"   📄 Other data: {len(other)}")
        
        # Show sample data
        if posts:
            print(f"\n📝 Sample post data:")
            print(json.dumps(posts[0], indent=2)[:500] + "...")
        
        if likes:
            print(f"\n❤️  Sample like data:")
            print(json.dumps(likes[0], indent=2)[:500] + "...")
        
        if saves:
            print(f"\n💾 Sample save data:")
            print(json.dumps(saves[0], indent=2)[:500] + "...")
    
    # Get changelog data
    changelog_data = get_recent_changelog_data()
    
    print(f"\n" + "=" * 50)
    print("🎯 Next steps:")
    print("• If posts/likes/saves are found, we can create specific extractors")
    print("• If not found in snapshot, they might be in different endpoints")
    print("• Check LinkedIn API documentation for specific data types")

if __name__ == "__main__":
    main()
