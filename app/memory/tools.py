"""Long-term (agent) memory.

The *_core functions hold the logic and take the store and user_id explicitly, so they can be
tested without an LLM. `make_memory_tools` wraps them as LangChain tools. The user_id is read from
the server-set run config, never from model arguments.
"""

import hashlib
import re
from typing import Any, Literal

from app.memory.guards import sanitize_for_prompt, validate_memory_content

APP_NS = "ledger_dary"
CATEGORIES = ("profile", "goals", "preferences", "budget_facts")
Category = Literal["profile", "goals", "preferences", "budget_facts"]


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_")[:48]


def _default_key(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content.lower()).strip()
    return "m_" + hashlib.sha1(normalized.encode()).hexdigest()[:10]


def filter_hits(hits: list[Any], min_score: float) -> list[Any]:
    """Drop weak semantic matches. Stores without scores (no index) keep everything."""
    return [h for h in hits if getattr(h, "score", None) is None or h.score >= min_score]


async def save_memory_core(
    store: Any, user_id: str, content: str, category: str, key: str = "", max_chars: int = 300
) -> str:
    if category not in CATEGORIES:
        return f"Not saved: category must be one of {', '.join(CATEGORIES)}."
    error = validate_memory_content(content, max_chars)
    if error:
        return f"Not saved: {error}."
    key = normalize_key(key) or _default_key(content)

    # A key is unique per user: remove it from other categories so facts are not duplicated.
    for other in CATEGORIES:
        if other != category:
            await store.adelete((APP_NS, user_id, other), key)

    await store.aput(
        (APP_NS, user_id, category),
        key,
        {"content": content.strip(), "category": category},
    )
    return f"Saved memory key='{key}' in category '{category}'."


async def get_memory_core(store: Any, user_id: str, key: str, category: str) -> str:
    if category not in CATEGORIES:
        return f"Unknown category '{category}'."
    item = await store.aget((APP_NS, user_id, category), normalize_key(key))
    if item is None:
        return f"No memory found for key='{key}' in category '{category}'."
    return f"[{category}/{item.key}] {sanitize_for_prompt(item.value.get('content', ''))}"


async def search_memories_core(
    store: Any,
    user_id: str,
    query: str,
    category: str = "",
    limit: int = 5,
    min_score: float = 0.7,
    max_chars: int = 300,
) -> str:
    if not query.strip():
        return "Search skipped: empty query."
    if category and category not in CATEGORIES:
        return f"Unknown category '{category}'. Use one of: {', '.join(CATEGORIES)}."
    prefix = (APP_NS, user_id) + ((category,) if category else ())
    hits = await store.asearch(prefix, query=query.strip(), limit=min(max(limit, 1), 10))
    hits = filter_hits(hits, min_score)
    if not hits:
        return "No relevant memories found."
    return "\n".join(
        f"[{h.namespace[-1]}/{h.key}] {sanitize_for_prompt(h.value.get('content', ''), max_chars)}"
        for h in hits
    )


async def delete_user_memories(store: Any, user_id: str) -> int:
    """Delete every memory for a user (right-to-erasure). Returns the number removed."""
    removed = 0
    while True:
        items = await store.asearch((APP_NS, user_id), limit=100)
        if not items:
            return removed
        for item in items:
            await store.adelete(tuple(item.namespace), item.key)
            removed += 1


def _user_id(runtime: Any) -> str:
    user_id = (runtime.config.get("configurable") or {}).get("user_id")
    if not user_id:
        raise ValueError("user_id missing from run config")
    return str(user_id)


def make_memory_tools(min_score: float = 0.7, max_chars: int = 300) -> list[Any]:
    from langchain.tools import ToolRuntime, tool

    @tool
    async def save_memory(
        content: str, category: Category, runtime: ToolRuntime, key: str = ""
    ) -> str:
        """Save a durable fact about the user (profile, goal, preference or budget fact).
        Use when the user states something worth remembering across conversations.
        Never save SSNs, card or bank-account numbers or passwords.
        Reuse a short descriptive key (e.g. 'laptop_goal') to update an existing memory."""
        return await save_memory_core(
            runtime.store, _user_id(runtime), content, category, key, max_chars
        )

    @tool
    async def get_memory(key: str, category: Category, runtime: ToolRuntime) -> str:
        """Retrieve one saved memory by its exact key and category."""
        return await get_memory_core(runtime.store, _user_id(runtime), key, category)

    @tool
    async def search_memories(
        query: str, runtime: ToolRuntime, category: str = "", limit: int = 5
    ) -> str:
        """Search long-term memories by meaning using a text query.
        Optionally restrict to one category: profile, goals, preferences, budget_facts."""
        return await search_memories_core(
            runtime.store, _user_id(runtime), query, category, limit, min_score, max_chars
        )

    return [save_memory, get_memory, search_memories]
