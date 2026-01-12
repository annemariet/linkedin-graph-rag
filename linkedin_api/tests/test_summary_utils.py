"""Tests for summary_utils module."""

from collections import Counter

from linkedin_api.utils.summaries import print_resource_summary, summarize_resources


def test_summarize_resources_counts_and_examples():
    elements = [
        {"resourceName": "ugcPosts", "methodName": "CREATE", "activity": {"id": 1}},
        {"resourceName": "messages", "methodName": "UPDATE", "activity": {"id": 2}},
        {"resourceName": "ugcPosts", "methodName": "CREATE", "activity": {"id": 3}},
    ]

    resource_counts, method_counts, resource_examples = summarize_resources(elements)

    assert resource_counts == Counter({"ugcPosts": 2, "messages": 1})
    assert method_counts == Counter({"CREATE": 2, "UPDATE": 1})
    assert resource_examples["ugcPosts"] == {"id": 1}  # first example is kept
    assert resource_examples["messages"] == {"id": 2}


def test_print_resource_summary_outputs(capsys):
    resource_counts = Counter({"ugcPosts": 2, "messages": 1})
    method_counts = Counter({"CREATE": 2, "UPDATE": 1})
    resource_examples = {"ugcPosts": {"id": 1}, "messages": {"id": 2}}

    print_resource_summary(resource_counts, method_counts, resource_examples, top_n=2)

    captured = capsys.readouterr().out
    assert "ugcPosts: 2" in captured
    assert "messages: 1" in captured
    assert "CREATE: 2" in captured
    assert "UPDATE: 1" in captured
    assert "Total unique resource types: 2" in captured
