#!/usr/bin/env python3
"""
Interactive script to store LinkedIn access token in keyring (macOS Keychain, etc.).

This script securely stores your token in the system keyring so you only need to enter it once.
"""

import sys
import getpass
import os
try:
    import keyring  # type: ignore[import-unresolved]
except ImportError:
    print("❌ keyring library not installed")
    print("   Install it with: pip install keyring")
    sys.exit(1)


from linkedin_api.auth import get_access_token


def main():
    print("🔐 LinkedIn Access Token Setup")
    print("=" * 50)
    
    SERVICE = "LINKEDIN_ACCESS_TOKEN"
    ACCOUNT = os.getenv("LINKEDIN_ACCOUNT")
    
    # Check if token already exists
    existing = keyring.get_password(SERVICE, ACCOUNT) or get_access_token()
    if existing:
        print("✅ Token already available")
        response = input("   Do you want to update it? (y/N): ").strip().lower()
        if response != 'y':
            print("   Keeping existing token.")
            return
    
    # Get token from user
    print("\n📝 Enter your LinkedIn access token:")
    print("   (Get it from: https://www.linkedin.com/developers/tools/oauth?clientId=78bwhum7gz6t9t)")
    print("   (Token will be hidden as you type)")
    
    token = getpass.getpass("   Token: ").strip()
    
    if not token:
        print("❌ No token provided. Exiting.")
        sys.exit(1)
    
    if len(token) < 20:
        print("⚠️  Warning: Token seems too short. LinkedIn tokens are typically longer.")
        response = input("   Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("   Cancelled.")
            sys.exit(1)
    
    # Store in keyring
    print(f"\n💾 Storing token in keyring... (length: {len(token)})")
    try:
        keyring.set_password(SERVICE, ACCOUNT, token)
        print("✅ Token stored successfully!")
        print("\n📌 Your token is now securely stored in your system keyring.")
        print("   (macOS: Keychain, Windows: Credential Manager, Linux: Secret Service)")
        print("   You can use it in scripts without setting environment variables.")
        print("   The token will be retrieved automatically when needed.")
    except Exception as e:
        print(f"❌ Failed to store token in keyring: {e}")
        print("   Check keyring permissions or try setting as environment variable instead.")
        sys.exit(1)


if __name__ == "__main__":
    main()

