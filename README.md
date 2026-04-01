# Google Trends MCP Server

An MCP (Model Context Protocol) server providing free access to Google Trends data. No API keys required.

## Features

- **Interest Over Time** - Track search volume trends for any keyword
- **Keyword Comparison** - Compare up to 5 keywords side by side
- **Related Queries** - Discover top and rising related searches
- **Trending Searches** - Real-time trending topics via Google RSS
- **Regional Interest** - Geographic breakdown by country, region, or city

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage with Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "google-trends": {
      "type": "stdio",
      "command": "/path/to/mcp-google-trends/venv/bin/python3",
      "args": ["/path/to/mcp-google-trends/google_trends_mcp_server.py"],
      "env": {}
    }
  }
}
```

## Testing

```bash
source venv/bin/activate
python test_server.py
```

## Rate Limiting

The server includes three layers of rate limiting:
1. 5-second delay between trendspy API calls
2. Single-threaded executor (serialized requests)
3. 30-minute in-memory cache

## Dependencies

- `mcp` - Model Context Protocol SDK
- `trendspy` - Unofficial Google Trends library
- `pandas` - DataFrame handling
