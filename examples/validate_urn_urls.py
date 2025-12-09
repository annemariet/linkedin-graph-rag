#!/usr/bin/env python3
"""
Validate that LinkedIn URN-to-URL conversions produce working URLs.

Tests actual HTTP requests to verify URLs point to expected pages.

Run with: uv run examples/validate_urn_urls.py
"""

import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from linkedin_api.urn_utils import (
    urn_to_post_url,
    urn_to_profile_url,
    extract_urn_id,
)


def validate_url(url: str, expected_type: str = "page") -> dict:
    """
    Validate a URL by making an HTTP request and checking the response.
    
    Args:
        url: The URL to validate
        expected_type: Type of page expected ('post', 'profile', 'page')
        
    Returns:
        Dictionary with validation results
    """
    result = {
        "url": url,
        "status_code": None,
        "success": False,
        "redirected": False,
        "final_url": None,
        "title": None,
        "is_linkedin": False,
        "error": None,
    }
    
    try:
        # Follow redirects but track them
        response = requests.get(url, allow_redirects=True, timeout=10)
        result["status_code"] = response.status_code
        result["final_url"] = response.url
        result["redirected"] = response.url != url
        
        if response.status_code == 200:
            result["success"] = True
            
            # Parse HTML to check if it's a LinkedIn page
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check title
            title_tag = soup.find('title')
            if title_tag:
                result["title"] = title_tag.get_text().strip()
            
            # Check if it's LinkedIn (by domain or content)
            result["is_linkedin"] = (
                'linkedin.com' in response.url.lower() or
                (title_tag and 'linkedin' in title_tag.get_text().lower())
            )
            
            # Check for common LinkedIn page indicators
            if soup.find('meta', property='og:site_name', content='LinkedIn'):
                result["is_linkedin"] = True
            
    except requests.exceptions.Timeout:
        result["error"] = "Request timeout"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection error"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def print_validation_result(result: dict, label: str):
    """Print validation result in a readable format."""
    print(f"\n{'='*60}")
    print(f"🔍 {label}")
    print(f"{'='*60}")
    print(f"URL: {result['url']}")
    
    if result['redirected']:
        print(f"🔄 Redirected to: {result['final_url']}")
    
    if result['status_code']:
        status_emoji = "✅" if result['status_code'] == 200 else "❌"
        print(f"{status_emoji} Status Code: {result['status_code']}")
    
    if result['success']:
        print(f"✅ Page loaded successfully")
        if result['title']:
            print(f"📄 Title: {result['title']}")
        if result['is_linkedin']:
            print(f"✅ Confirmed LinkedIn page")
        else:
            print(f"⚠️  May not be a LinkedIn page")
    else:
        if result['error']:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"❌ Page did not load successfully")


def main():
    """Validate URN-to-URL conversions with real HTTP requests."""
    
    print("🔗 LinkedIn URN URL Validation")
    print("=" * 60)
    
    # Test data from your sample
    test_cases = [
        {
            "urn": "urn:li:ugcPost:7398404729531285504",
            "type": "post",
            "url_func": urn_to_post_url,
        },
        {
            "urn": "urn:li:person:k_ho7OlN0r",
            "type": "profile",
            "url_func": urn_to_profile_url,
        },
    ]
    
    # Additional test cases
    additional_tests = [
        {
            "urn": "urn:li:ugcPost:1234567890",
            "type": "post",
            "url_func": urn_to_post_url,
        },
    ]
    
    all_tests = test_cases + additional_tests
    
    results = []
    
    for test in all_tests:
        urn = test["urn"]
        url_func = test["url_func"]
        url = url_func(urn)
        
        if url:
            print(f"\n🧪 Testing: {urn}")
            result = validate_url(url, test["type"])
            result["urn"] = urn
            result["urn_type"] = test["type"]
            results.append(result)
            print_validation_result(result, f"{test['type'].title()} URL")
        else:
            print(f"\n❌ Could not convert URN: {urn}")
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 VALIDATION SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    print(f"❌ Failed: {len(failed)}/{len(results)}")
    
    if successful:
        print(f"\n✅ Working URLs:")
        for r in successful:
            print(f"   • {r['urn']}")
            print(f"     → {r['final_url']}")
            if r['title']:
                print(f"     Title: {r['title']}")
    
    if failed:
        print(f"\n❌ Failed URLs:")
        for r in failed:
            print(f"   • {r['urn']}")
            print(f"     → {r['url']}")
            if r['error']:
                print(f"     Error: {r['error']}")
            elif r['status_code']:
                print(f"     Status: {r['status_code']}")
    
    print(f"\n💡 Notes:")
    print(f"   • Post URLs use full URN in path")
    print(f"   • Profile URLs may redirect or require authentication")
    print(f"   • Some URLs may be private or deleted")
    print(f"   • LinkedIn may show login page for private content")


if __name__ == "__main__":
    main()
