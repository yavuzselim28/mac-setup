import urllib.request
import ssl
from typing import Any
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import Response
import uvicorn
import contextlib

app_server = Server("http-fetch-mcp")

@app_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="http_get",
            description="Perform an HTTP GET request to a URL and return the response body.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                    "max_bytes": {"type": "integer", "default": 10000}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="fetch_release_notes",
            description="Fetch Kubernetes or OpenShift release notes for a specific version.",
            inputSchema={
                "type": "object",
                "properties": {
                    "version": {"type": "string", "description": "Version e.g. '1.35'"},
                    "type": {"type": "string", "default": "kubernetes"}
                },
                "required": ["version"]
            }
        )
    ]

@app_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "http_get":
        return await handle_http_get(arguments)
    elif name == "fetch_release_notes":
        return await handle_fetch_release_notes(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def handle_http_get(arguments: dict) -> list[TextContent]:
    url = arguments.get("url")
    max_bytes = arguments.get("max_bytes", 10000)
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "kagent-http-mcp/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            content = r.read(max_bytes).decode("utf-8", errors="replace")
            return [TextContent(type="text", text=f"HTTP {r.status}\n\n{content}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def handle_fetch_release_notes(arguments: dict) -> list[TextContent]:
    version = arguments.get("version", "1.35").lstrip("v").strip()
    parts = version.split(".")
    minor = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else version
    notes_type = arguments.get("type", "kubernetes")
    if notes_type == "kubernetes":
        url = f"https://raw.githubusercontent.com/kubernetes/kubernetes/master/CHANGELOG/CHANGELOG-{minor}.md"
        result = await handle_http_get({"url": url, "max_bytes": 15000})
        return [TextContent(type="text", text=f"Kubernetes {minor} Release Notes:\n\n{result[0].text}")]
    ocp_map = {"1.31":"4.15","1.32":"4.16","1.33":"4.17","1.34":"4.17","1.35":"4.18","1.36":"4.19"}
    ocp = ocp_map.get(minor, "4.17")
    url = f"https://docs.openshift.com/container-platform/{ocp}/release_notes/ocp-{ocp.replace('.', '-')}-release-notes.html"
    result = await handle_http_get({"url": url, "max_bytes": 10000})
    return [TextContent(type="text", text=f"OpenShift {ocp} Release Notes:\n\n{result[0].text}")]

session_manager = StreamableHTTPSessionManager(app=app_server, stateless=True)

@contextlib.asynccontextmanager
async def lifespan(app):
    async with session_manager.run():
        yield

starlette_app = Starlette(
    lifespan=lifespan,
    routes=[
        Mount("/mcp", app=session_manager.handle_request),
        Route("/health", endpoint=lambda r: Response("ok")),
    ]
)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host="0.0.0.0", port=8085)
