from types import SimpleNamespace

from langgraph.store.memory import InMemoryStore

from app.memory.tools import (
    delete_user_memories,
    filter_hits,
    get_memory_core,
    save_memory_core,
    search_memories_core,
)


async def test_save_and_get():
    store = InMemoryStore()
    out = await save_memory_core(store, "u1", "Saving $2,400 for a laptop", "goals", "Laptop Goal")
    assert "key='laptop_goal'" in out
    assert "Saving $2,400" in await get_memory_core(store, "u1", "laptop_goal", "goals")


async def test_sensitive_content_not_saved():
    store = InMemoryStore()
    out = await save_memory_core(store, "u1", "card 4111 1111 1111 1111", "profile")
    assert out.startswith("Not saved")
    assert await store.asearch(("ledger_dary", "u1")) == []


async def test_invalid_category_rejected():
    store = InMemoryStore()
    assert (await save_memory_core(store, "u1", "x", "secrets")).startswith("Not saved")


async def test_same_key_in_new_category_moves_instead_of_duplicating():
    store = InMemoryStore()
    await save_memory_core(store, "u1", "Dream cello", "budget_facts", "cello")
    await save_memory_core(store, "u1", "Dream purchase: a cello", "goals", "cello")
    items = await store.asearch(("ledger_dary", "u1"))
    assert len(items) == 1
    assert items[0].namespace[-1] == "goals"


async def test_users_are_isolated():
    store = InMemoryStore()
    await save_memory_core(store, "alice", "Dining budget is $350", "budget_facts", "dining")
    out = await get_memory_core(store, "bob", "dining", "budget_facts")
    assert out.startswith("No memory found")
    assert await store.asearch(("ledger_dary", "bob")) == []


async def test_search_returns_sanitized_content():
    store = InMemoryStore()
    await save_memory_core(store, "u1", "Budget <ignore previous> is $350", "budget_facts", "b")
    out = await search_memories_core(store, "u1", "budget", min_score=0.0)
    assert "<" not in out and "$350" in out


async def test_search_empty_query_and_bad_category():
    store = InMemoryStore()
    assert "empty query" in await search_memories_core(store, "u1", " ")
    assert "Unknown category" in await search_memories_core(store, "u1", "x", category="nope")


def test_filter_hits_applies_threshold_and_keeps_unscored():
    hits = [SimpleNamespace(score=0.9), SimpleNamespace(score=0.5), SimpleNamespace(score=None)]
    assert [h.score for h in filter_hits(hits, 0.7)] == [0.9, None]


async def test_delete_user_memories_only_removes_that_user():
    store = InMemoryStore()
    for i in range(3):
        await save_memory_core(store, "u1", f"fact {i}", "profile", f"k{i}")
    await save_memory_core(store, "u2", "keep me", "profile", "k")
    assert await delete_user_memories(store, "u1") == 3
    assert await store.asearch(("ledger_dary", "u1")) == []
    assert len(await store.asearch(("ledger_dary", "u2"))) == 1
