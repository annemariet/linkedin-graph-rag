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

## Dev notes

Changelog data:
list of elements with following schema:
{
   'owner',
   'resourceId',
   'method',
   'activity',
   'configVersion',
   'parentSiblingActivities',
   'resourceName',
   'resourceUri',
   'actor',
   'activityId',
   'processedAt',
   'activityStatus',
   'capturedAt',
   'siblingActivities',
   'id'
}

'resourceName': 'messages' -> this is for DMs. I want to skip these, I only want to count how many DMs I sent (and received if that's possible)

Other types of resources:
{'messages': 25, 'socialActions/likes': 22, 'invitations': 2, 'ugcPosts': 1}

Example:
```
'owner': 'urn:li:person:k_ho7OlN0r',
'resourceId': '2-MTc2NDA5OTEzNTA1MGI2Nzg4My0xMDAmOWY1YTU5M2EtOWJmNS00NjZhLWE5ZGMtNTlkNGUzMTJiM2VhXzEwMA==',
'method': 'CREATE',
'activity': {'owner': 'urn:li:person:k_ho7OlN0r', 'attachments': [], 'clientExperience': {'clientGeneratedToken': 'c248e9b2-3439-43ee-8095-3b3f356f1023'},
'author': 'urn:li:person:k_ho7OlN0r',
'thread': 'urn:li:messagingThread:2-OWY1YTU5M2EtOWJmNS00NjZhLWE5ZGMtNTlkNGUzMTJiM2VhXzEwMA==',
'contentClassification': {'classification': 'SAFE'},
'content': {'format': 'TEXT', 'fallback': 'Je ne sais pas exactement où est le RV 😂.\nTu peux me contacter au 06 04 42 91 31 si jamais.', 'formatVersion': 1}, 'deliveredAt': 1764099135050, 'actor': 'urn:li:messagingActor:urn:li:person:k_ho7OlN0r',
'createdAt': 1764099135050, 'mailbox': 'urn:li:messagingMailbox:urn:li:person:k_ho7OlN0r', 'messageContexts': [], 'id': '2-MTc2NDA5OTEzNTA1MGI2Nzg4My0xMDAmOWY1YTU5M2EtOWJmNS00NjZhLWE5ZGMtNTlkNGUzMTJiM2VhXzEwMA==', '$URN': 'urn:li:messagingMessage:2-MTc2NDA5OTEzNTA1MGI2Nzg4My0xMDAmOWY1YTU5M2EtOWJmNS00NjZhLWE5ZGMtNTlkNGUzMTJiM2VhXzEwMA=='}, 'configVersion': 19, 'parentSiblingActivities': [],
'resourceName': 'messages', 'resourceUri': '/messages/2-MTc2NDA5OTEzNTA1MGI2Nzg4My0xMDAmOWY1YTU5M2EtOWJmNS00NjZhLWE5ZGMtNTlkNGUzMTJiM2VhXzEwMA==', 'actor': 'urn:li:person:k_ho7OlN0r', 'activityId': 'e53339f6-7abb-4146-b9cb-fc4fbfa692d7', 'processedAt': 1764099135440, 'activityStatus': 'SUCCESS', 'capturedAt': 1764099135260, 'siblingActivities': [], 'id': 5893231114}
```

Activity object: not all fields are always present. I have an example with just "reactionType". Some don't have the $URN field.
{
   'actor', 'reactionType', 'created', 'root', 'lastModified', '$URN', 'object'
}

Let's examine reactionType.
Reaction counts: Counter({'LIKE': 11, 'INTEREST': 7, 'APPRECIATION': 2, 'PRAISE': 2, 'n/a': 1})

I'm curious about what invitations and ugcPosts are.

invitations example: 
```
{
   'invitationV2': {
      'inviter': 'urn:li:person:t0Lo9bjtc-',
      'trackingId': 'º±2Ì\x0eÕMÕ¨+ø\x80Õ\x100\x1d',
      'invitee': 'urn:li:person:k_ho7OlN0r'
   }
}
```

UGCPost seems to be simply posts and is quite rich.
It's not clear whether it's for all posts or basic shares.

Even though I'd like to focus on likes, it might be useful to have the proper initial post structure right.