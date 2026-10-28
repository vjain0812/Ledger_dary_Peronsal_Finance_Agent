from typing import Any

from app.config import Settings
from app.prompts import MEMORY_PROMPT


def text_of(result: dict) -> str:
    content = result["messages"][-1].content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content


def tool_calls_this_turn(result: dict) -> list[str]:
    """Tool names called since the last human message."""
    messages = result["messages"]
    start = 0
    for i, m in enumerate(messages):
        if getattr(m, "type", None) == "human":
            start = i
    return [c["name"] for m in messages[start:] for c in (getattr(m, "tool_calls", None) or [])]


def build_embeddings(settings: Settings) -> Any:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings.embed_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        output_dimensionality=settings.embed_dims,
    )


def build_agent(settings: Settings, tools: list[Any], checkpointer: Any, store: Any) -> Any:
    from langchain.agents import create_agent
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=settings.model_name,
        api_key=settings.google_api_key.get_secret_value(),
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=MEMORY_PROMPT,
        checkpointer=checkpointer,
        store=store,
    )
