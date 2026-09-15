# MCP Adapter

Model Context Protocol adapter for AsistCV (Claude Desktop integration).

## Stack

- Python 3.12+
- MCP SDK
- UV (package manager)

## Commands

```bash
# Install dependencies
uv sync

# Run the MCP server (stdio)
uv run asistcv-mcp

# Run tests
uv run pytest
```

## Structure

```
mcp-adapter/
├── src/           # Source code
├── tests/         # Test suite
└── pyproject.toml # Project configuration
```

## Usage

Configure in Claude Desktop via JSON config pointing to this server.
