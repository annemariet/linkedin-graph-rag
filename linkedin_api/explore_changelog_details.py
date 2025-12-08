#!/usr/bin/env python3
"""
Explore LinkedIn Member Data Portability API changelog details
Focus on time ranges, resource types, and categories
"""

import os
import requests
from datetime import datetime
from collections import defaultdict, Counter
from bs4 import BeautifulSoup
import dotenv
import keyring

dotenv.load_dotenv()

# SECURITY: Use keyring or environment variable
def get_access_token():
    """Get token from keyring or environment variable."""
    token = keyring.get_password("LINKEDIN_ACCESS_TOKEN", os.getenv('LINKEDIN_ACCOUNT'))
    if token:
        return token

    return os.getenv('LINKEDIN_ACCESS_TOKEN')

LI_REACTIONS = {
            'LIKE': '👍',
            'EMPATHY': '❤️',
            'CELEBRATE': '👏',
            "PRAISE": '👏',
            'SUPPORT': '🫴🏻',
            "APPRECIATION": '🫴🏻',
            'INSIGHTFUL': '💡',
            "INTEREST": '💡',
            'FUNNY': '😂',
            "ENTERTAINMENT": '😂',
        }

def get_all_reactions():
    """Get all reaction/like data from changelog, ignoring invitations."""
    
    access_token = get_access_token()
    if not access_token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found")
        print("   Run 'python3 setup_token.py' to store it in Keychain, or set it as an environment variable")
        return []
    
    print("❤️  Fetching all reactions from changelog...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
        'LinkedIn-Version': '202312'
    }
    
    base_url = "https://api.linkedin.com/rest"
    all_reactions = []
    start = 0
    count = 50
    
    while True:
        try:
            response = requests.get(
                f"{base_url}/memberChangeLogs",
                headers=headers,
                params={"q": "memberAndApplication", "start": start, "count": count}
            )
            
            if response.status_code != 200:
                print(f"❌ Error: {response.status_code}")
                print(response.content)
                break
            
            data = response.json()
            elements = data.get('elements', [])
            
            if not elements:
                print("✅ No more data to fetch")
                break
            
            # Filter for reactions only
            for element in elements:
                resource_name = element.get('resourceName', '')
                
                # Only process reaction-related data
                if 'socialActions/likes' in resource_name or 'reaction' in resource_name.lower():
                    activity = element.get('activity', {})
                    
                    # Extract reaction details
                    reaction_data = {
                        'timestamp': activity.get('created', {}).get('time'),
                        'reaction_type': activity.get('reactionType', ''),
                        'post_id': activity.get('root', ''),
                        'actor': activity.get('actor', ''),
                        'resource_name': resource_name
                    }
                    
                    all_reactions.append(reaction_data)
            
            print(f"   📡 Fetched {len(elements)} items, found {len([e for e in elements if 'socialActions/likes' in e.get('resourceName', '')])} reactions")
            
            # Check for more pages
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
    
    print(f"✅ Total reactions found: {len(all_reactions)}")
    return all_reactions

def get_post_details(post_url,):
    """Get post details including author and content."""
    try:
        response = requests.get(post_url)
        response.raise_for_status()
        html_content = response.text

        soup = BeautifulSoup(html_content, 'html.parser')

        # now you can start extracting details, for example:
        title = soup.find('title').get_text() if soup.find('title') else 'no title found'
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        return {
            "title": title,
            "content_paragraphs": paragraphs,
            "raw_html": html_content
        }
        
    except Exception as e:
        print(f"   ❌ Error getting post details: {str(e)}")
        return None

def construct_linkedin_url(post_id):
    """Construct a public LinkedIn URL from post ID."""
    
    if not post_id:
        return "Unknown"
    
    # Extract numeric ID from URN
    if ':' in post_id:
        numeric_id = post_id.split(':')[-1]
    else:
        numeric_id = post_id
    
    # Construct public LinkedIn URL
    return f"https://www.linkedin.com/feed/update/{post_id}/"

def analyze_author_patterns(reactions_with_posts):
    """Analyze which authors you react to the most."""
    
    print(f"\n📊 AUTHOR ANALYSIS:")
    print("=" * 50)
    
    author_counts = {}
    author_reactions = {}
    
    for reaction in reactions_with_posts:
        author = reaction.get('author_name', 'Unknown Author')
        reaction_type = reaction.get('reaction_type', 'Unknown')
        
        # Count total reactions per author
        author_counts[author] = author_counts.get(author, 0) + 1
        
        # Track reaction types per author
        if author not in author_reactions:
            author_reactions[author] = {}
        author_reactions[author][reaction_type] = author_reactions[author].get(reaction_type, 0) + 1
    
    # Sort authors by reaction count
    sorted_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)
    
    print(f"📈 Authors you react to most:")
    for i, (author, count) in enumerate(sorted_authors, 1):
        print(f"\n{i}. 👤 {author}: {count} reactions")
        
        # Show reaction breakdown for this author
        reactions = author_reactions[author]
        for reaction_type, reaction_count in reactions.items():
            emoji = LI_REACTIONS.get(reaction_type, '❓')
            print(f"   {emoji} {reaction_type}: {reaction_count}")
    
    return author_counts, author_reactions

def summarize_post_content(content, max_words=300):
    """Summarize post content if it's longer than max_words."""
    
    if not content:
        return "No content available"
    
    # Count words
    words = content.split()
    word_count = len(words)
    
    if word_count <= max_words:
        return content
    
    # Truncate to max_words and add summary indicator
    truncated = ' '.join(words[:max_words])
    return f"{truncated}... [Content truncated - original was {word_count} words]"

def analyze_resource_types(elements):
    """Analyze the different types of resources in changelog data."""
    
    print(f"\n🔍 Analyzing {len(elements)} changelog elements...")
    
    resource_types = Counter()
    method_types = Counter()
    activity_types = Counter()
    actor_types = Counter()
    
    # Detailed analysis
    detailed_resources = defaultdict(list)
    
    for element in elements:
        # Resource analysis
        resource_name = element.get('resourceName', '')
        resource_uri = element.get('resourceUri', '')
        method_name = element.get('methodName', '')
        actor = element.get('actor', '')
        activity = element.get('activity', {})
        
        # Count types
        resource_types[resource_name] += 1
        method_types[method_name] += 1
        actor_types[actor] += 1
        
        # Analyze activity structure
        if activity:
            activity_keys = list(activity.keys())
            for key in activity_keys:
                activity_types[key] += 1
            
            # Store detailed info for interesting resources
            if resource_name in ['socialActions/likes', 'invitationsV2', 'connections']:
                detailed_resources[resource_name].append({
                    'timestamp': activity.get('created', {}).get('time'),
                    'method': method_name,
                    'activity_keys': activity_keys,
                    'activity_sample': {k: v for k, v in list(activity.items())[:3]}  # First 3 items
                })
    
    # Print summary
    print(f"\n📊 Resource Types Found:")
    for resource, count in resource_types.most_common():
        print(f"   • {resource}: {count} items")
    
    print(f"\n📊 Method Types:")
    for method, count in method_types.most_common():
        print(f"   • {method}: {count} items")
    
    print(f"\n📊 Activity Types:")
    for activity_type, count in activity_types.most_common():
        print(f"   • {activity_type}: {count} items")
    
    print(f"\n📊 Actor Types:")
    for actor, count in actor_types.most_common():
        print(f"   • {actor}: {count} items")
    
    # Show detailed examples
    print(f"\n🔍 Detailed Examples:")
    for resource_name, items in detailed_resources.items():
        print(f"\n   📝 {resource_name} ({len(items)} items):")
        for i, item in enumerate(items[:2], 1):  # Show first 2 examples
            if item['timestamp']:
                date = datetime.fromtimestamp(item['timestamp'] / 1000)
                print(f"      {i}. {date} - {item['method']}")
                print(f"         Activity keys: {item['activity_keys']}")
                print(f"         Sample: {item['activity_sample']}")
    
    return resource_types, method_types, activity_types

def explore_specific_resources():
    """Explore specific resource types in detail."""
    
    access_token = get_access_token()
    if not access_token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found in environment variables")
        return
    
    print(f"\n🔍 Exploring specific resource types...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
        'LinkedIn-Version': '202312'
    }
    
    base_url = "https://api.linkedin.com/rest"
    
    # Get a larger sample to find more resource types
    try:
        response = requests.get(
            f"{base_url}/memberChangeLogs",
            headers=headers,
            params={"q": "memberAndApplication", "count": 200}
        )
        
        if response.status_code == 200:
            data = response.json()
            elements = data.get('elements', [])
            
            print(f"✅ Analyzing {len(elements)} elements for resource patterns...")
            
            # Group by resource type
            resource_groups = defaultdict(list)
            for element in elements:
                resource_name = element.get('resourceName', '')
                resource_groups[resource_name].append(element)
            
            # Analyze each resource type
            for resource_name, items in resource_groups.items():
                print(f"\n📋 {resource_name} ({len(items)} items):")
                
                # Sample the first item to show structure
                if items:
                    sample = items[0]
                    activity = sample.get('activity', {})
                    
                    print(f"   📊 Sample structure:")
                    print(f"      Method: {sample.get('methodName', 'N/A')}")
                    print(f"      Actor: {sample.get('actor', 'N/A')}")
                    print(f"      Activity keys: {list(activity.keys())}")
                    
                    # Show timestamp if available
                    created = activity.get('created', {})
                    if created.get('time'):
                        date = datetime.fromtimestamp(created['time'] / 1000)
                        print(f"      Timestamp: {date}")
                    
                    # Show a sample of the activity data
                    if activity:
                        sample_data = {k: v for k, v in list(activity.items())[:2]}
                        print(f"      Sample data: {sample_data}")
        
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        raise

def display_reactions_with_posts(reactions):
    """Display reactions with post details and author information."""
    
    if not reactions:
        print("😔 No reactions found in changelog data")
        return []
    
    print(f"\n🎯 REACTION DETAILS WITH POSTS ({len(reactions)} reactions):")
    print("=" * 80)
    
    # Sort by timestamp (newest first)
    reactions.sort(key=lambda x: x['timestamp'] or 0, reverse=True)
    
    reactions_with_posts = []
    
    for i, reaction in enumerate(reactions):
        print(f"\n{i}. 📅 REACTION DETAILS:")
        
        # Format timestamp
        if reaction['timestamp']:
            date = datetime.fromtimestamp(reaction['timestamp'] / 1000)
            print(f"   🕒 When: {date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"   📅 Date: {date.strftime('%B %d, %Y')}")
            print(f"   ⏰ Time: {date.strftime('%I:%M %p')}")
        else:
            print(f"   🕒 When: Unknown timestamp")
        
        # Reaction type
        reaction_type = reaction['reaction_type']
        reaction_emoji = LI_REACTIONS.get(reaction_type, '❓')
        
        print(f"   {reaction_emoji} Reaction: {reaction_type}")
        
        # Post ID and details
        post_id = reaction['post_id']
        if post_id:
            short_id = post_id.split(':')[-1][:10] + "..." if len(post_id.split(':')[-1]) > 10 else post_id.split(':')[-1]
            print(f"   📝 Post ID: {short_id}")
            print(f"   🔗 Full Post ID: {post_id}")
            
            # Construct LinkedIn URL
            post_url = construct_linkedin_url(post_id)

            # Try to get post details
            print(f"   🔍 Fetching post details...")
            post_details = get_post_details(post_url)
            
            
            if post_details:
                title = post_details.get("title", "No title")
                content = "".join(post_details.get("content_paragraphs", ["", "", "?"])[2:5])
                print(f"   👤 Title: {title}")
                print(f"   🔗 Post URL: {post_url}")
                print(f"   📄 Content: {content}")
                
                # Add post details to reaction data
                reaction['title'] = title
                reaction['post_content'] = content
                reaction['post_url'] = post_url
            else:
                print(f"   💡 Note: Post content not available.")
                print(f"   🔗 Post URL: {post_url}")
                reaction['post_url'] = post_url
        else:
            print(f"   📝 Post ID: Unknown")
            reaction['author_name'] = 'Unknown Author'
            reaction['post_content'] = 'No content available'
            reaction['post_url'] = 'Unknown'
  
        print(f"   📊 Resource: {reaction['resource_name']}")
        
        reactions_with_posts.append(reaction)
    
    # Summary statistics
    print(f"\n" + "=" * 80)
    print("📊 REACTION SUMMARY:")
    
    # Count reaction types
    reaction_counts = {}
    for reaction in reactions_with_posts:
        reaction_type = reaction['reaction_type']
        reaction_counts[reaction_type] = reaction_counts.get(reaction_type, 0) + 1
    
    print(f"   Total reactions: {len(reactions_with_posts)}")
    print(f"   Reaction types:")
    for reaction_type, count in reaction_counts.items():
        emoji = LI_REACTIONS.get(reaction_type, '❓')
        print(f"     {emoji} {reaction_type}: {count}")
    
    # Time range
    if reactions_with_posts:
        timestamps = [r['timestamp'] for r in reactions_with_posts if r['timestamp']]
        if timestamps:
            oldest = datetime.fromtimestamp(min(timestamps) / 1000)
            newest = datetime.fromtimestamp(max(timestamps) / 1000)
            print(f"   📅 Time range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
            print(f"   📊 Span: {(newest - oldest).days} days")
    
    return reactions_with_posts

def main():
    """Main function to explore reactions from changelog."""
    print("🚀 LinkedIn Reactions Explorer")
    print("=" * 50)
    
    # Get all reactions
    reactions = get_all_reactions()
    
    # Display reactions with post details
    reactions_with_posts = display_reactions_with_posts(reactions)
    
    # Analyze author patterns
    if reactions_with_posts:
        analyze_author_patterns(reactions_with_posts)
    
    print(f"\n" + "=" * 50)
    print("🎯 Note: Limited history because you activated portability recently!")
    print("   Future reactions should appear in the changelog.")

if __name__ == "__main__":
    main() 
