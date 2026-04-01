#!/usr/bin/env python3
"""
Test suite for Google Trends MCP Server.

Tests run sequentially to respect rate limiting.
Uses benign keywords to avoid triggering bot detection.
"""

import asyncio
import json
import sys

from google_trends_mcp_server import execute_tool


async def test_interest_over_time():
    print("\n=== Testing get_interest_over_time ===")
    result = await execute_tool("get_interest_over_time", {
        "keyword": "python programming",
        "timeframe": "today 3-m",
        "geo": "US"
    })
    print(json.dumps(result, indent=2, default=str)[:500])
    assert result["keyword"] == "python programming"
    assert result["data_points"] > 0, "Expected data points"
    assert result["summary"] is not None, "Expected summary"
    assert result["summary"]["max"] <= 100, "Values should be 0-100"
    print(f"PASS: {result['data_points']} data points, current={result['summary']['current']}, "
          f"trend={result['summary']['trend_direction']}")
    return True


async def test_compare_keywords():
    print("\n=== Testing compare_keywords ===")
    result = await execute_tool("compare_keywords", {
        "keywords": ["python", "javascript"],
        "timeframe": "today 3-m",
        "geo": "US"
    })
    print(json.dumps(result, indent=2, default=str)[:500])
    assert len(result["keywords"]) == 2
    assert result["data_points"] > 0, "Expected data points"
    assert result["dominant_keyword"] in ["python", "javascript"]
    print(f"PASS: {result['data_points']} data points, dominant={result['dominant_keyword']}")
    return True


async def test_compare_keywords_validation():
    print("\n=== Testing compare_keywords validation ===")
    try:
        await execute_tool("compare_keywords", {"keywords": ["only_one"]})
        print("FAIL: Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"PASS: Correctly rejected single keyword: {e}")
        return True


async def test_related_queries():
    print("\n=== Testing get_related_queries ===")
    result = await execute_tool("get_related_queries", {
        "keyword": "machine learning",
        "timeframe": "today 12-m",
        "geo": "US"
    })
    print(json.dumps(result, indent=2, default=str)[:500])
    assert result["keyword"] == "machine learning"
    print(f"PASS: {len(result['top_queries'])} top queries, "
          f"{len(result['rising_queries'])} rising queries")
    return True


async def test_trending_searches():
    print("\n=== Testing get_trending_searches ===")
    result = await execute_tool("get_trending_searches", {
        "geo": "US",
        "limit": 5
    })
    print(json.dumps(result, indent=2, default=str)[:500])
    assert result["source"] == "rss"
    assert len(result["trending"]) <= 5
    print(f"PASS: {result['count']} trending topics from {result['source']}")
    return True


async def test_interest_by_region():
    print("\n=== Testing get_interest_by_region ===")
    result = await execute_tool("get_interest_by_region", {
        "keyword": "artificial intelligence",
        "timeframe": "today 12-m",
        "geo": "",
        "resolution": "COUNTRY",
        "limit": 10
    })
    print(json.dumps(result, indent=2, default=str)[:500])
    assert result["keyword"] == "artificial intelligence"
    assert len(result["regions"]) <= 10
    if result["regions"]:
        assert result["regions"][0]["interest"] >= result["regions"][-1]["interest"], \
            "Regions should be sorted by interest descending"
    print(f"PASS: {len(result['regions'])} regions, "
          f"top={result['regions'][0]['region'] if result['regions'] else 'none'}")
    return True


async def test_cache():
    print("\n=== Testing cache (second call should be instant) ===")
    import time

    # First call (should hit API)
    t0 = time.time()
    await execute_tool("get_trending_searches", {"geo": "US", "limit": 3})
    first_time = time.time() - t0

    # Second call (should hit cache)
    t0 = time.time()
    result = await execute_tool("get_trending_searches", {"geo": "US", "limit": 3})
    second_time = time.time() - t0

    print(f"First call: {first_time:.2f}s, Second call: {second_time:.4f}s")
    assert second_time < first_time, "Cached call should be faster"
    print(f"PASS: Cache working ({second_time:.4f}s vs {first_time:.2f}s)")
    return True


async def run_all_tests():
    tests = [
        ("get_trending_searches", test_trending_searches),
        ("cache", test_cache),
        ("get_interest_over_time", test_interest_over_time),
        ("compare_keywords", test_compare_keywords),
        ("compare_keywords_validation", test_compare_keywords_validation),
        ("get_related_queries", test_related_queries),
        ("get_interest_by_region", test_interest_by_region),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            result = await test_fn()
            if result:
                passed += 1
            else:
                failed += 1
                print(f"FAIL: {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {name} - {e}")

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
