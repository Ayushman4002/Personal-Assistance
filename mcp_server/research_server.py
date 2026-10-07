from fastmcp import FastMCP
from ddgs import DDGS

mcp = FastMCP("Research Tools")


@mcp.tool
def search_web(query: str) -> str:
    """
    Search the web for current AI and technology information.
    """

    results = []

    try:
        with DDGS() as ddgs:
            search_results = ddgs.text(
                query,
                max_results=10
            )

            for result in search_results:
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", "")
                })

    except Exception as e:
        return f"Search failed: {str(e)}"

    if not results:
        return f"No search results found for: {query}"

    return str(results)


if __name__ == "__main__":
    mcp.run()