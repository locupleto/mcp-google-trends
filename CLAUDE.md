# Google Trends MCP Server

Free access to Google Trends data for financial analytics. No API keys required.

## Tools

### `get_interest_over_time`
Search interest (0-100) for a keyword over time. Returns data points + summary with trend direction.
```
keyword: "recession", timeframe: "today 12-m", geo: "US", category: 7
```

### `compare_keywords`
Compare 2-5 keywords side by side (normalized against each other).
```
keywords: ["recession", "bull market"], timeframe: "today 12-m"
```

### `get_related_queries`
Top and rising related searches for a keyword. Rising values show breakout or % increase.
```
keyword: "bitcoin", timeframe: "today 12-m", geo: "US"
```

### `get_trending_searches`
Real-time trending searches via Google RSS. Fast, no quota risk.
```
geo: "US", limit: 20
```

### `get_interest_by_region`
Geographic breakdown of search interest. Resolution: COUNTRY, REGION, CITY, DMA.
```
keyword: "bitcoin", geo: "", resolution: "COUNTRY", limit: 25
```

## Timeframe Options
- Real-time: `now 1-H`, `now 4-H`, `now 7-d`
- Recent: `today 1-m`, `today 3-m`, `today 12-m`, `today 5-y`
- All time: `all`
- Custom range: `2024-01-01 2024-12-31`
- Custom interval: `2024-02-01 10-d`, `2024-03-15 3-m`

## Category IDs (common)
- 0 = All, 7 = Finance, 12 = Business, 16 = News, 71 = Food & Drink

## Rate Limiting
- 5-second delay between API calls (built into trendspy)
- Single-threaded executor (no concurrent requests)
- 30-minute cache TTL

## Backend
Uses `trendspy` library (unofficial Google Trends). Free, no API key. Works reliably at 5-20 queries/day.
