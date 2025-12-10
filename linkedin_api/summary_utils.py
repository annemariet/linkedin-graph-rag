"""
Shared helpers for summarizing and printing LinkedIn changelog data.
"""

from collections import Counter
from typing import Dict, List, Tuple


def summarize_resources(elements: List[dict]) -> Tuple[Counter, Counter, Dict[str, dict]]:
    """
    Build counters and examples for resource and method usage.

    Returns:
        (resource_counts, method_counts, resource_examples)
    """
    resource_counts: Counter = Counter()
    method_counts: Counter = Counter()
    resource_examples: Dict[str, dict] = {}

    for element in elements:
        resource_name = element.get("resourceName", "")
        method_name = element.get("methodName", "")
        activity = element.get("activity", {})

        resource_counts[resource_name] += 1
        method_counts[method_name] += 1

        if resource_name and resource_name not in resource_examples:
            resource_examples[resource_name] = activity

    return resource_counts, method_counts, resource_examples


def print_resource_summary(
    resource_counts: Counter,
    method_counts: Counter,
    resource_examples: Dict[str, dict],
    *,
    top_n: int = 10,
) -> None:
    """Pretty-print resource and method stats with examples."""
    print(f"\n📋 RESOURCE TYPES (Top {top_n}):")
    for resource, count in resource_counts.most_common(top_n):
        print(f"   • {resource}: {count}")

    print(f"\n📋 METHOD TYPES (Top {top_n}):")
    for method, count in method_counts.most_common(top_n):
        print(f"   • {method or 'UNKNOWN'}: {count}")

    print(f"\n📋 ALL RESOURCE NAMES WITH EXAMPLES:")
    print(f"   Total unique resource types: {len(resource_examples)}")
    for resource_name in sorted(resource_examples.keys()):
        count = resource_counts[resource_name]
        example = resource_examples[resource_name]
        print(f"\n   • {resource_name} (count: {count}):")
        if example:
            print(f"     {example}")
        else:
            print("     (no activity object)")
