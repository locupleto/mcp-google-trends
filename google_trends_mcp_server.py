#!/usr/bin/env python3
"""
Google Trends MCP Server - Free access to Google Trends data.

Provides 5 tools for search trend analysis: interest over time,
keyword comparison, related queries, trending searches, and regional interest.

No API keys required - uses trendspy library (unofficial Google Trends).
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from trendspy import Trends

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-trends-mcp")

# Initialize MCP server
server = Server("google-trends")

# Initialize trendspy client with 5-second delay between requests
_trends = Trends(request_delay=5.0)

# Single-threaded executor serializes requests = natural rate limiting
_executor = ThreadPoolExecutor(max_workers=1)

# --- Cache ---

CACHE_TTL = 1800  # 30 minutes

_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    """Get cached value if not expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > CACHE_TTL:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: Any) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (time.time(), data)


# --- Helpers ---

async def _run_sync(func, *args, **kwargs):
    """Run a synchronous trendspy function in the thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: func(*args, **kwargs)
    )


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of dicts, handling Timestamp index."""
    if df is None or df.empty:
        return []
    df_reset = df.reset_index()
    for col in df_reset.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        df_reset[col] = df_reset[col].dt.strftime("%Y-%m-%d")
    return df_reset.to_dict(orient="records")


def _compute_trend_direction(values: list) -> str:
    """Compare recent vs prior values to determine trend direction."""
    if len(values) < 8:
        return "insufficient_data"
    recent = sum(values[-4:]) / 4
    prior = sum(values[-8:-4]) / 4
    if prior == 0:
        return "rising" if recent > 0 else "stable"
    pct_change = (recent - prior) / prior
    if pct_change > 0.10:
        return "rising"
    elif pct_change < -0.10:
        return "falling"
    return "stable"


# --- Tool Handlers ---

async def _get_interest_over_time(arguments: dict) -> dict:
    keyword = arguments["keyword"]
    timeframe = arguments.get("timeframe", "today 12-m")
    geo = arguments.get("geo", "")
    cat = arguments.get("category", 0)

    cache_key = f"iot:{keyword}:{timeframe}:{geo}:{cat}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    df = await _run_sync(
        _trends.interest_over_time, keyword,
        timeframe=timeframe, geo=geo, cat=cat
    )

    if df is None or df.empty:
        return {
            "keyword": keyword,
            "timeframe": timeframe,
            "geo": geo or "worldwide",
            "data_points": 0,
            "data": [],
            "summary": None,
            "message": "No data available for this keyword/timeframe/geo combination"
        }

    # Extract the keyword column (trendspy uses the keyword as column name)
    col = keyword if keyword in df.columns else df.columns[0]
    values = df[col].tolist()
    dates = df.index

    data = []
    for i, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        data.append({"date": date_str, "value": int(values[i])})

    result = {
        "keyword": keyword,
        "timeframe": timeframe,
        "geo": geo or "worldwide",
        "data_points": len(data),
        "data": data,
        "summary": {
            "max": int(max(values)),
            "min": int(min(values)),
            "avg": round(sum(values) / len(values), 1),
            "current": int(values[-1]),
            "trend_direction": _compute_trend_direction(values)
        }
    }

    _cache_set(cache_key, result)
    return result


async def _compare_keywords(arguments: dict) -> dict:
    keywords = arguments["keywords"]
    if len(keywords) < 2:
        raise ValueError("At least 2 keywords required for comparison")
    if len(keywords) > 5:
        raise ValueError("Maximum 5 keywords allowed (Google Trends limit)")

    timeframe = arguments.get("timeframe", "today 12-m")
    geo = arguments.get("geo", "")
    cat = arguments.get("category", 0)

    cache_key = f"cmp:{','.join(sorted(keywords))}:{timeframe}:{geo}:{cat}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    df = await _run_sync(
        _trends.interest_over_time, keywords,
        timeframe=timeframe, geo=geo, cat=cat
    )

    if df is None or df.empty:
        return {
            "keywords": keywords,
            "timeframe": timeframe,
            "geo": geo or "worldwide",
            "data": [],
            "summary": {},
            "message": "No data available for this keyword/timeframe/geo combination"
        }

    records = _df_to_records(df)

    # Rename index column if present
    for r in records:
        if "index" in r:
            r["date"] = r.pop("index")

    # Per-keyword summary
    summary = {}
    for kw in keywords:
        if kw in df.columns:
            vals = df[kw].tolist()
            summary[kw] = {
                "max": int(max(vals)),
                "min": int(min(vals)),
                "avg": round(sum(vals) / len(vals), 1),
                "current": int(vals[-1]),
                "trend_direction": _compute_trend_direction(vals)
            }

    # Dominant keyword = highest average
    dominant = max(summary.keys(), key=lambda k: summary[k]["avg"]) if summary else None

    result = {
        "keywords": keywords,
        "timeframe": timeframe,
        "geo": geo or "worldwide",
        "data_points": len(records),
        "data": records,
        "summary": summary,
        "dominant_keyword": dominant
    }

    _cache_set(cache_key, result)
    return result


async def _get_related_queries(arguments: dict) -> dict:
    keyword = arguments["keyword"]
    timeframe = arguments.get("timeframe", "today 12-m")
    geo = arguments.get("geo", "")
    cat = arguments.get("category", 0)

    cache_key = f"rq:{keyword}:{timeframe}:{geo}:{cat}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        return cached

    raw = await _run_sync(
        _trends.related_queries, keyword,
        timeframe=timeframe, geo=geo, cat=cat
    )

    # trendspy returns flat dict: {"top": DataFrame, "rising": DataFrame}
    top_queries = []
    rising_queries = []

    if raw:
        top_df = raw.get("top")
        if top_df is not None and not top_df.empty:
            for _, row in top_df.iterrows():
                top_queries.append({
                    "query": str(row.get("query", "")),
                    "value": int(row.get("value", 0))
                })
        rising_df = raw.get("rising")
        if rising_df is not None and not rising_df.empty:
            for _, row in rising_df.iterrows():
                rising_queries.append({
                    "query": str(row.get("query", "")),
                    "value": str(row.get("value", ""))
                })

    result = {
        "keyword": keyword,
        "timeframe": timeframe,
        "geo": geo or "worldwide",
        "top_queries": top_queries,
        "rising_queries": rising_queries
    }

    _cache_set(cache_key, result)
    return result


async def _get_trending_searches(arguments: dict) -> dict:
    geo = arguments.get("geo", "US")
    limit = min(arguments.get("limit", 20), 50)

    cache_key = f"trending:{geo}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        # Apply limit to cached data
        result = dict(cached)
        result["trending"] = result["trending"][:limit]
        return result

    trends_list = await _run_sync(_trends.trending_now_by_rss, geo=geo)

    trending = []
    if trends_list:
        for item in trends_list:
            entry = {
                "keyword": str(item) if not hasattr(item, "keyword") else item.keyword,
                "traffic_volume": getattr(item, "traffic", None),
            }
            # Extract news titles if available
            news = getattr(item, "news", None)
            if news:
                entry["related_news"] = [
                    {"title": getattr(n, "title", str(n)), "source": getattr(n, "source", None)}
                    for n in news[:3]
                ]
            trending.append(entry)

    # Cache the full list, apply limit on return
    full_result = {
        "geo": geo,
        "source": "rss",
        "count": len(trending),
        "trending": trending,
        "fetched_at": datetime.now(timezone.utc).isoformat()
    }
    _cache_set(cache_key, full_result)

    result = dict(full_result)
    result["trending"] = result["trending"][:limit]
    result["count"] = len(result["trending"])
    return result


async def _get_interest_by_region(arguments: dict) -> dict:
    keyword = arguments["keyword"]
    timeframe = arguments.get("timeframe", "today 12-m")
    geo = arguments.get("geo", "")
    resolution = arguments.get("resolution", "COUNTRY")
    limit = arguments.get("limit", 25)

    cache_key = f"ibr:{keyword}:{timeframe}:{geo}:{resolution}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        result = dict(cached)
        result["regions"] = result["regions"][:limit]
        return result

    df = await _run_sync(
        _trends.interest_by_region, keyword,
        timeframe=timeframe, geo=geo, resolution=resolution,
        inc_low_vol=False
    )

    if df is None or df.empty:
        return {
            "keyword": keyword,
            "geo": geo or "worldwide",
            "resolution": resolution,
            "regions": [],
            "message": "No regional data available"
        }

    # Extract and sort by interest value
    # trendspy returns columns: geoName, geoCode, <keyword>
    value_col = keyword if keyword in df.columns else [c for c in df.columns if c not in ("geoName", "geoCode")][0]
    regions = []
    for _, row in df.iterrows():
        val = int(row[value_col])
        if val > 0:
            region_name = row.get("geoName", str(row.name))
            regions.append({"region": str(region_name), "interest": val})

    regions.sort(key=lambda r: r["interest"], reverse=True)

    full_result = {
        "keyword": keyword,
        "timeframe": timeframe,
        "geo": geo or "worldwide",
        "resolution": resolution,
        "total_regions": len(regions),
        "regions": regions
    }
    _cache_set(cache_key, full_result)

    result = dict(full_result)
    result["regions"] = result["regions"][:limit]
    return result


# --- Tool Registration ---

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Google Trends tools."""
    return [
        Tool(
            name="get_interest_over_time",
            description="Get search interest over time for a keyword (0-100 scale). "
                        "Useful as a retail sentiment proxy for financial analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Search term (e.g., 'recession', 'AAPL stock', 'bitcoin')"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time range. Options: 'now 1-H', 'now 4-H', 'now 7-d', "
                                       "'today 1-m', 'today 3-m', 'today 12-m', 'today 5-y', 'all', "
                                       "or 'YYYY-MM-DD YYYY-MM-DD' for custom range. Default: 'today 12-m'",
                        "default": "today 12-m"
                    },
                    "geo": {
                        "type": "string",
                        "description": "Country code (e.g., 'US', 'GB', 'DE'). Empty = worldwide. Default: ''",
                        "default": ""
                    },
                    "category": {
                        "type": "integer",
                        "description": "Google Trends category ID (0 = all categories). "
                                       "7 = Finance, 12 = Business, 16 = News. Default: 0",
                        "default": 0
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="compare_keywords",
            description="Compare search interest for 2-5 keywords side by side. "
                        "Values are normalized against each other (top keyword peaks at 100). "
                        "Great for relative sentiment analysis (e.g., 'recession' vs 'bull market').",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 5,
                        "description": "2-5 search terms to compare"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time range (same options as get_interest_over_time). Default: 'today 12-m'",
                        "default": "today 12-m"
                    },
                    "geo": {
                        "type": "string",
                        "description": "Country code. Empty = worldwide. Default: ''",
                        "default": ""
                    },
                    "category": {
                        "type": "integer",
                        "description": "Google Trends category ID. Default: 0",
                        "default": 0
                    }
                },
                "required": ["keywords"]
            }
        ),
        Tool(
            name="get_related_queries",
            description="Get top and rising related search queries for a keyword. "
                        "Rising queries show breakout or percentage increase. "
                        "Useful for detecting emerging themes and narratives.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Base search term"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time range. Default: 'today 12-m'",
                        "default": "today 12-m"
                    },
                    "geo": {
                        "type": "string",
                        "description": "Country code. Empty = worldwide. Default: ''",
                        "default": ""
                    },
                    "category": {
                        "type": "integer",
                        "description": "Google Trends category ID. Default: 0",
                        "default": 0
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="get_trending_searches",
            description="Get real-time trending searches by country via Google Trends RSS. "
                        "Fast, reliable, no quota risk. Shows what people are searching for right now.",
            inputSchema={
                "type": "object",
                "properties": {
                    "geo": {
                        "type": "string",
                        "description": "Country code (e.g., 'US', 'GB', 'SE'). Default: 'US'",
                        "default": "US"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (1-50). Default: 20",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="get_interest_by_region",
            description="Get geographic breakdown of search interest for a keyword. "
                        "Shows which regions/countries have highest search volume.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Search term"
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Time range. Default: 'today 12-m'",
                        "default": "today 12-m"
                    },
                    "geo": {
                        "type": "string",
                        "description": "Country code. Empty = world map, 'US' = US states. Default: ''",
                        "default": ""
                    },
                    "resolution": {
                        "type": "string",
                        "enum": ["COUNTRY", "REGION", "CITY", "DMA"],
                        "description": "Geographic resolution level. Default: 'COUNTRY'",
                        "default": "COUNTRY"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Top N regions to return. Default: 25",
                        "default": 25
                    }
                },
                "required": ["keyword"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a Google Trends tool."""
    try:
        result = await execute_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        error_result = {"error": str(e), "tool": name, "arguments": arguments}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def execute_tool(name: str, arguments: dict) -> Any:
    """Dispatch to the appropriate tool handler."""
    handlers = {
        "get_interest_over_time": _get_interest_over_time,
        "compare_keywords": _compare_keywords,
        "get_related_queries": _get_related_queries,
        "get_trending_searches": _get_trending_searches,
        "get_interest_by_region": _get_interest_by_region,
    }

    handler = handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    return await handler(arguments)


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
