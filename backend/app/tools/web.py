"""Web tools for search and fetching."""

from typing import Any

import httpx

from app.tools.base import Tool, ToolParameter, ToolResult, registry


class WebSearchTool(Tool):
    """Tool for web search using Brave Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(
            id="web_search",
            name="Web Search",
            description="Search the web using Brave Search",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query",
                ),
                ToolParameter(
                    name="count",
                    type="number",
                    description="Number of results (1-10)",
                    required=False,
                    default=5,
                ),
            ],
        )
        self.api_key = api_key

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute web search."""
        query = kwargs.get("query", "")
        count = min(int(kwargs.get("count", 5)), 10)

        if not query:
            return ToolResult(success=False, output="", error="No query provided")

        if not self.api_key:
            return ToolResult(
                success=False,
                output="",
                error="Brave Search API key not configured",
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": count},
                    headers={
                        "X-Subscription-Token": self.api_key,
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append(
                    f"**{item.get('title', 'No title')}**\n"
                    f"{item.get('url', '')}\n"
                    f"{item.get('description', '')}\n"
                )

            output = "\n---\n".join(results) if results else "No results found"

            return ToolResult(
                success=True,
                output=output,
                data={"result_count": len(results)},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output="", error=f"HTTP error: {e}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WebFetchTool(Tool):
    """Tool for fetching web pages."""

    def __init__(self) -> None:
        super().__init__(
            id="web_fetch",
            name="Web Fetch",
            description="Fetch content from a URL",
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="URL to fetch",
                ),
                ToolParameter(
                    name="max_chars",
                    type="number",
                    description="Maximum characters to return",
                    required=False,
                    default=10000,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Fetch URL content."""
        url = kwargs.get("url", "")
        max_chars = int(kwargs.get("max_chars", 10000))

        if not url:
            return ToolResult(success=False, output="", error="No URL provided")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "ClawdStudio/0.1"},
                    timeout=30,
                )
                response.raise_for_status()

            content = response.text[:max_chars]
            if len(response.text) > max_chars:
                content += f"\n\n[Truncated at {max_chars} chars]"

            return ToolResult(
                success=True,
                output=content,
                data={"url": str(response.url), "status": response.status_code},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output="", error=f"HTTP error: {e}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Register tools
registry.register(WebSearchTool())
registry.register(WebFetchTool())
