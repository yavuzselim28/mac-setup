import asyncio
import os
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

server = Server("http-fetch-mcp")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="http_get",
            description="Fetches a URL via HTTP GET and returns the response body as text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                    "headers": {"type": "object", "description": "Optional HTTP headers", "additionalProperties": {"type": "string"}}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="fetch_release_notes",
            description="Fetches release notes or changelog from a GitHub repository tag/release.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "GitHub repo in format owner/repo (e.g. openshift/rosa)"},
                    "tag": {"type": "string", "description": "Release tag or version (e.g. v4.17.0). Optional — omit for latest."}
                },
                "required": ["repo"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "http_get":
        url = arguments["url"]
        headers = arguments.get("headers", {})
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers=headers)
            return [TextContent(type="text", text=f"Status: {resp.status_code}\n\n{resp.text[:8000]}")]

    elif name == "fetch_release_notes":
        repo = arguments["repo"]
        tag = arguments.get("tag")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}" if tag else f"https://api.github.com/repos/{repo}/releases/latest"
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                body = data.get("body", "No release notes available.")
                return [TextContent(type="text", text=f"Release: {data.get('tag_name')}\nPublished: {data.get('published_at')}\n\n{body[:8000]}")]
            else:
                return [TextContent(type="text", text=f"Error {resp.status_code}: {resp.text[:2000]}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Mount("/messages/", app=sse.handle_post_message),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8085)
