import os

import pytest
import requests

from linkedin_api.utils.urns import comment_urn_to_post_url, parse_comment_urn


EXAMPLE_COMMENT_URNS = [
    "urn:li:comment:(activity:7401982773730856960,7402008011394912257)",
    "urn:li:comment:(ugcPost:7415421701938683905,7415508043578454016)",
]


@pytest.mark.integration
@pytest.mark.parametrize("comment_urn", EXAMPLE_COMMENT_URNS)
def test_parse_comment_urn_resolves_to_linkedin_post_html(comment_urn):
    parsed = parse_comment_urn(comment_urn)
    assert parsed is not None
    assert parsed["parent_urn"]

    post_url = comment_urn_to_post_url(comment_urn)
    assert post_url

    if os.getenv("LINKEDIN_TEST_ONLINE") != "1":
        pytest.skip("Set LINKEDIN_TEST_ONLINE=1 to run online LinkedIn checks.")

    response = requests.get(post_url, timeout=15)
    assert (
        response.status_code == 200
    ), f"LinkedIn returned {response.status_code} for {post_url}"

    content = response.text.lower()
    assert "linkedin" in content
    assert "feed/update" in content or "linkedin.com/feed/update" in content
