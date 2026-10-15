"""Entry point: creates the FastMCP server, registers tools, starts Streamable HTTP with token auth."""

import sys

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from poetry_lab import config
from poetry_lab.auth import AuthConfigError, BearerAuthMiddleware
from poetry_lab.tools import files, search


def transport_security(domain: str = "") -> TransportSecuritySettings:
    """Allow only local Host/Origin headers, plus the public ngrok domain when one is set."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    if domain:
        hosts.append(domain)
        origins.append(f"https://{domain}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


mcp = FastMCP(
    "Poetry Lab",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    streamable_http_path="/mcp",
    transport_security=transport_security(config.NGROK_DOMAIN),
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


def create_app(token: str):
    """The MCP HTTP app wrapped so that every request needs the bearer token."""
    return BearerAuthMiddleware(mcp.streamable_http_app(), token)


def main() -> None:
    try:
        app = create_app(config.MCP_TOKEN)
    except AuthConfigError as err:
        sys.exit(f"Refusing to start: {err}")
    uvicorn.run(app, host=config.MCP_HOST, port=config.MCP_PORT, log_level="info")


if __name__ == "__main__":
    main()
