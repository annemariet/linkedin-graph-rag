#!/usr/bin/env python3
"""
Extract and analyze all LinkedIn activity history from Member Data Portability API.

Extracts statistics for:
- DMs (messages sent/received)
- Invites (sent/received)
- Reactions (by type)
- Posts (original, repost, repost with comment)
- Comments
"""

import json
from collections import Counter, defaultdict
from datetime import datetime
from linkedin_api.changelog_utils import fetch_changelog_data


def get_all_changelog_data():
    """Fetch all changelog data by paginating through all results."""
    return fetch_changelog_data()


def extract_statistics(elements):
    """Extract statistics from changelog elements."""
    
    stats = {
        'messages': {
            'sent': 0,
            'received': 0,
            'total': 0
        },
        'invites': {
            'sent': 0,
            'received': 0,
            'total': 0
        },
        'reactions': Counter(),
        'posts': {
            'original': 0,
            'repost': 0,
            'repost_with_comment': 0,
            'total': 0
        },
        'comments': {
            'total': 0
        },
        'resource_types': Counter(),
        'method_types': Counter(),
        'resource_examples': {},  # resourceName -> example activity object
    }
    
    # Track actor to determine if action is by user
    user_actor = None
    
    for element in elements:
        resource_name = element.get('resourceName', '')
        method_name = element.get('methodName', '')
        actor = element.get('actor', '')
        activity = element.get('activity', {})
        
        # Track resource and method types
        stats['resource_types'][resource_name] += 1
        stats['method_types'][method_name] += 1
        
        # Store example activity for each resourceName (first occurrence)
        if resource_name and resource_name not in stats['resource_examples']:
            stats['resource_examples'][resource_name] = activity
        
        # Set user actor from first element (assuming consistent actor)
        if not user_actor and actor:
            user_actor = actor
        
        # Messages (DMs)
        if 'messages' in resource_name.lower():
            stats['messages']['total'] += 1
            if actor == user_actor:
                stats['messages']['sent'] += 1
            else:
                stats['messages']['received'] += 1
        
        # Invitations
        elif 'invitation' in resource_name.lower():
            stats['invites']['total'] += 1
            if actor == user_actor:
                stats['invites']['sent'] += 1
            else:
                stats['invites']['received'] += 1
        
        # Reactions
        elif 'socialActions/likes' in resource_name or 'reaction' in resource_name.lower():
            reaction_type = activity.get('reactionType', 'UNKNOWN')
            stats['reactions'][reaction_type] += 1
        
        # Posts (UGC Posts)
        elif 'ugcPost' in resource_name.lower() or 'ugcPosts' in resource_name:
            stats['posts']['total'] += 1
            
            # Determine post type from activity
            # Check if it's a repost (shares another post)
            if activity.get('resharedPost') or activity.get('resharedActivity'):
                # Check if there's a comment/commentary
                if activity.get('commentary') or activity.get('text'):
                    stats['posts']['repost_with_comment'] += 1
                else:
                    stats['posts']['repost'] += 1
            else:
                stats['posts']['original'] += 1
        
        # Comments
        elif 'comment' in resource_name.lower() or 'comments' in resource_name.lower():
            stats['comments']['total'] += 1
    
    return stats


def print_statistics(stats):
    """Print formatted statistics."""
    
    print("\n" + "=" * 60)
    print("📊 LINKEDIN ACTIVITY STATISTICS")
    print("=" * 60)
    
    # Messages
    print(f"\n💬 MESSAGES (DMs):")
    print(f"   Total: {stats['messages']['total']}")
    print(f"   Sent: {stats['messages']['sent']}")
    print(f"   Received: {stats['messages']['received']}")
    
    # Invites
    print(f"\n👋 INVITATIONS:")
    print(f"   Total: {stats['invites']['total']}")
    print(f"   Sent: {stats['invites']['sent']}")
    print(f"   Received: {stats['invites']['received']}")
    
    # Reactions
    print(f"\n❤️  REACTIONS:")
    total_reactions = sum(stats['reactions'].values())
    print(f"   Total: {total_reactions}")
    print(f"   By type:")
    for reaction_type, count in stats['reactions'].most_common():
        print(f"     • {reaction_type}: {count}")
    
    # Posts
    print(f"\n📝 POSTS:")
    print(f"   Total: {stats['posts']['total']}")
    print(f"   Original: {stats['posts']['original']}")
    print(f"   Reposts: {stats['posts']['repost']}")
    print(f"   Reposts with comment: {stats['posts']['repost_with_comment']}")
    
    # Comments
    print(f"\n💬 COMMENTS:")
    print(f"   Total: {stats['comments']['total']}")
    
    # Resource types summary
    print(f"\n📋 RESOURCE TYPES (Top 10):")
    for resource, count in stats['resource_types'].most_common(10):
        print(f"   • {resource}: {count}")
    
    # All resource names with examples
    print(f"\n📋 ALL RESOURCE NAMES WITH EXAMPLES:")
    print(f"   Total unique resource types: {len(stats['resource_examples'])}")
    for resource_name in sorted(stats['resource_examples'].keys()):
        count = stats['resource_types'][resource_name]
        example = stats['resource_examples'][resource_name]
        print(f"\n   • {resource_name} (count: {count}):")
        if example:
            # Pretty print example activity
            example_str = json.dumps(example, indent=6, default=str)
            # Indent each line
            for line in example_str.split('\n'):
                print(f"     {line}")
        else:
            print(f"     (no activity object)")
    
    print("\n" + "=" * 60)


def save_statistics(stats, filename='linkedin_statistics.json'):
    """Save statistics to JSON file."""
    
    # Convert Counter objects to dicts for JSON serialization
    stats_json = {
        'messages': stats['messages'],
        'invites': stats['invites'],
        'reactions': dict(stats['reactions']),
        'posts': stats['posts'],
        'comments': stats['comments'],
        'resource_types': dict(stats['resource_types']),
        'method_types': dict(stats['method_types']),
        'resource_examples': stats['resource_examples'],
    }
    
    with open(filename, 'w') as f:
        json.dump(stats_json, f, indent=2, default=str)
    
    print(f"💾 Statistics saved to {filename}")


def main():
    """Main function to extract and analyze LinkedIn data."""
    print("🚀 LinkedIn Data Extraction & Statistics")
    print("=" * 60)
    
    # Get all changelog data
    elements = get_all_changelog_data()
    
    if not elements:
        print("❌ No data retrieved")
        return
    
    # Extract statistics
    print("\n🔍 Analyzing data...")
    stats = extract_statistics(elements)
    
    # Print statistics
    print_statistics(stats)
    
    # Save to file
    save_statistics(stats)
    
    print("\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
