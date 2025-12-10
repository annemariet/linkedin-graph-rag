#!/usr/bin/env python3
"""
Validate that LINKEDIN_ACCESS_TOKEN is available without exposing its value.
This script checks for the token and validates it's properly configured.

SECURITY NOTES:
- This script does NOT use dotenv to avoid AI tools accessing .env files
- This script never prints or logs the token value
- Token can be stored in macOS Keychain (recommended) or environment variable
- AI tools should NOT run this script - you should run it yourself to verify
"""

import sys

from linkedin_api.auth import get_access_token


def check_token():
    """Check if token exists and is valid format without exposing value."""
    token = get_access_token()

    if not token:
        print("❌ LINKEDIN_ACCESS_TOKEN not found")
        print("\n📝 To set it up (choose one method):")
        print("\n   Method 1 (Recommended - Keyring):")
        print("     python3 setup_token.py")
        print("     This stores the token securely in your system keyring")
        print("\n   Method 2 (Shell environment variable):")
        print("     export LINKEDIN_ACCESS_TOKEN=your_token_here")
        print("\n   Method 3 (Temporary - Single command):")
        print("     LINKEDIN_ACCESS_TOKEN=your_token_here python3 script.py")
        return False

    # Validate token format (LinkedIn tokens are typically long alphanumeric strings)
    if len(token) < 20:
        print("⚠️  Token seems too short. LinkedIn tokens are typically longer.")
        return False

    print(f"✅ LINKEDIN_ACCESS_TOKEN is set")
    print(f"   Token length: {len(token)} characters")

    return True


if __name__ == "__main__":
    success = check_token()
    sys.exit(0 if success else 1)
