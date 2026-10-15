"""Entry point: creates the FastMCP server, registers tools, starts Streamable HTTP."""

from mcp.server.fastmcp import FastMCP

from poetry_lab import config
from poetry_lab.tools import files, search

mcp = FastMCP(
    "Poetry Lab",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    streamable_http_path="/mcp",
)

TOOLS = [
    (files.list_files, files.LIST_FILES_DESCRIPTION),
    (files.read_file, files.READ_FILE_DESCRIPTION),
    (files.write_file, files.WRITE_FILE_DESCRIPTION),
    (files.str_replace, files.STR_REPLACE_DESCRIPTION),
    (files.delete_file, files.DELETE_FILE_DESCRIPTION),
    (search.search_poems, search.SEARCH_POEMS_DESCRIPTION),
]

for func, description in TOOLS:
    mcp.tool(name=func.__name__, description=description)(func)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
