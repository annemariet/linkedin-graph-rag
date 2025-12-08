# LinkedIn Portability API Client

A Python client for LinkedIn's Portability API to fetch saved posts and feed data, compliant with DMA (Digital Markets Act) requirements.

## Features

- ✅ Fetch saved posts
- ✅ Fetch feed posts  
- ✅ Get user profile
- ✅ DMA-compliant data access
- ✅ Simple error handling
- ✅ Environment variable support

## Setup

### 1. Install Dependencies

This project uses `uv` for dependency management. Install dependencies with:

```bash
uv sync
```

This will:
- Install Python 3.12 (if needed)
- Install all dependencies including `keyring` and `requests`
- Set up the virtual environment

### 2. Get LinkedIn Access Token

**Option A: LinkedIn Developer App**
1. Go to [LinkedIn Developers](https://www.linkedin.com/developers/)
2. Create a new app
3. Get OAuth 2.0 access token. The Portability API uses `r_dma_portability_self_serve` scope


**Troubleshooting**

Token expires: `{"status":401,"serviceErrorCode":65602,"code":"EXPIRED_ACCESS_TOKEN","message":"The token used in the request has expired"}`

This happens every 2 months. A token can be recreated on https://www.linkedin.com/developers/tools/oauth?clientId=78bwhum7gz6t9t. Update the right secret used by the app (most lately, `LINKEDIN_ACCESS_TOKEN`)


https://learn.microsoft.com/en-us/linkedin/dma/member-data-portability/shared/member-changelog-api?view=li-dma-data-portability-2025-11&tabs=http

https://www.linkedin.com/developers/apps/224112894/auth


### 3. Configure Access Token

**Recommended: Store in Keychain (macOS)**

```bash
uv run python3 setup_token.py
```

This securely stores your token in macOS Keychain. You only need to do this once.

**Alternative: Environment Variable**

```bash
export LINKEDIN_ACCESS_TOKEN=your_access_token_here
```

## Usage
Run scripts using `uv run` to ensure the correct Python version:
```bash
uv run python3 explore_changelog_details.py
uv run python3 get_linkedin_data.py
```
**Note**: The scripts will automatically retrieve your token from Keychain (if stored) or environment variables.

`python explore_changelog_detail.py`  works OK except it's not correctly parsing the posts yet, not handling reactions on comments properly, and it's still not getting the saved posts, only the reactions.

I thought I'd use Instapaper to save posts but I've kept saving with LinkedIn...

`python get_linkedin_data.py` is lower level and can be used for dev.

Next steps:
- Properly handle post content for analysis
- cleanup all the extra files


## Important Notes

⚠️ **API Limitations:**
- LinkedIn Portability API is subject to rate limits
- Access tokens expire (typically 60 days)
- Some endpoints may require additional permissions

⚠️ **DMA Compliance:**
- This implementation follows LinkedIn's DMA requirements
- Data access is limited to user's own content
- Respects LinkedIn's data portability guidelines

## Troubleshooting

### Common Issues

1. **403 Forbidden**
   - Check access token validity
   - Verify required scopes are granted
   - Ensure token hasn't expired

2. **401 Unauthorized**
   - Invalid access token
   - Token format issues

3. **Rate Limiting**
   - Implement exponential backoff
   - Reduce request frequency

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Legal Compliance

This implementation follows:
- [LinkedIn DMA Portability API Terms](https://www.linkedin.com/legal/l/portability-api-terms)
- [LinkedIn API Terms of Use](https://www.linkedin.com/legal/l/api-terms-of-use)
- GDPR and DMA data portability requirements 


# Resources and follow-up ideas

- [srchd](https://github.com/dust-tt/srchd) with a link to a talk from dotAI, how to coordinate agents through a publication/review reasoning, including references.
- [auth0](https://auth0.com/ai/docs/intro/overview) secure authentication for agent use

# TODO next

- [ ] Cleanup token/keyring setup, check and retrieval, avoid duplication
- [ ] Review get_linkedin_data.py to extract relevant info from posts
- [ ] Extract posts and articles from links -- understand linkedin urn/uri thing