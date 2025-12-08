# Security Model for LinkedIn API Tools

## Token Security

**IMPORTANT**: The `LINKEDIN_ACCESS_TOKEN` is a sensitive credential that should never be exposed to AI tools or logged.

### How to Set the Token

**Recommended Method: macOS Keychain (Store Once)**

```bash
# Run the setup script (macOS only)
python3 setup_token.py
```

This securely stores your token in macOS Keychain. You only need to enter it once, and scripts will automatically retrieve it.

**Alternative: Shell Environment Variable**

```bash
# Temporary (current shell session only)
export LINKEDIN_ACCESS_TOKEN=your_token_here

# Or inline with command (doesn't persist)
LINKEDIN_ACCESS_TOKEN=your_token_here python3 script.py
```

### Security Measures

1. **macOS Keychain Storage**: Tokens stored in encrypted macOS Keychain (recommended)
2. **No `.env` files**: We don't use `python-dotenv` to avoid AI tools potentially accessing `.env` files
3. **No token in code**: Token is never hardcoded or committed to git
4. **No token in logs**: Scripts never print or log the token value
5. **Validation only**: `check_token.py` only validates the token exists, never displays it
6. **Keychain encryption**: macOS Keychain is encrypted and requires user authentication to access

### AI Tool Safety

- AI tools should NOT run scripts that access `LINKEDIN_ACCESS_TOKEN`
- AI tools can design and structure code, but you should run it yourself
- If you need to test, run scripts yourself with your token set

### Token Management

- Tokens expire every ~60 days
- Get new tokens from: https://www.linkedin.com/developers/tools/oauth?clientId=78bwhum7gz6t9t
- Required scope: `r_dma_portability_self_serve`

## Alternative: Auth0 Token Vault

For production AI agent systems, consider [Auth0 for AI Agents](https://auth0.com/ai/docs/get-started/overview) with Token Vault:

**When Auth0 makes sense:**
- Production AI applications with multiple users
- Systems requiring automatic token refresh
- Multi-tenant applications
- Centralized token management across services

**For this local development tool:**
- Current approach (shell env vars) is sufficient
- Auth0 adds unnecessary complexity
- Manual token refresh every 60 days is acceptable

See: https://auth0.com/ai/docs/get-started/overview

