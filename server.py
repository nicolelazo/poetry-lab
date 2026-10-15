"""Entry point: creates the FastMCP server, registers tools, starts Streamable HTTP."""

from mcp.server.fastmcp import FastMCP

from poetry_lab import config
from poetry_lab.tools.files import LIST_FILES_DESCRIPTION, list_files

mcp = FastMCP(
    "Poetry Lab",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    streamable_http_path="/mcp",
)

mcp.tool(name="list_files", description=LIST_FILES_DESCRIPTION)(list_files)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
