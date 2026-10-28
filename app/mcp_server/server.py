"""Standalone MCP tool server. Run as its own service:  python -m app.mcp_server.server"""

import os

from mcp.server.fastmcp import FastMCP

from app.mcp_server.calculators import budget_guardrail, card_rewards

server = FastMCP(
    "ledger-dary-finance-tools",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


@server.tool()
def search_financial_literacy(query: str) -> str:
    """Search the web for general educational personal-finance information,
    not live market data or trading."""
    if not query or not query.strip():
        return "Search failed safely: provide a non-empty query."
    try:
        # ddgs scrapes search pages. Swap in a real search API (Brave, Tavily, Bing) for production.
        from ddgs import DDGS

        results = list(
            DDGS(timeout=10).text(query.strip() + " personal finance education", max_results=5)
        )
    except Exception as exc:
        return f"Search tool error ({type(exc).__name__}): service unavailable; do not fabricate results."
    if not results:
        return "No search results returned. Try a more specific query."
    return "\n".join(
        f"- {x.get('title', 'Untitled')}: {x.get('body', '')} Source: {x.get('href', '')}"
        for x in results[:5]
    )


@server.tool()
def calculate_budget_guardrail(monthly_limit: float, spent_so_far: float, days_remaining: int) -> str:
    """Calculate budget utilization, remaining amount and even daily target using USD values."""
    return budget_guardrail(monthly_limit, spent_so_far, days_remaining)


@server.tool()
def compare_user_provided_card_rewards(
    spending_category: str, monthly_spend: float, card_reward_rates: dict[str, float]
) -> str:
    """Estimate rewards for user-supplied credit-card percentage rates; never guess rates."""
    return card_rewards(spending_category, monthly_spend, card_reward_rates)


if __name__ == "__main__":
    server.run(transport="streamable-http")
