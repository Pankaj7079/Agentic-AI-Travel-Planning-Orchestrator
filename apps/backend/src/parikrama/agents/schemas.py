"""
Shared agent types — input, output, and LangGraph state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from langgraph.graph.message import add_messages


@dataclass
class AgentInput:
    """Standardized input for all PariKrama travel agents."""

    query: str  # Natural language user request
    user_id: str  # Authenticated user UUID string
    trip_id: str | None = None  # Optional linked trip record
    budget: float | None = None  # Numeric budget in INR (if relevant)
    context: dict = field(default_factory=dict)  # Extra metadata / overrides


@dataclass
class AgentOutput:
    """Standardized output from all PariKrama travel agents."""

    content: str  # Main LLM response (markdown-formatted)
    agent: str  # Agent class name, e.g. "ItineraryAgent"
    provider: str  # "gemini" or "groq"
    model: str  # Model name used
    latency_ms: int  # Total wall-clock time in ms
    rag_chunks_used: int = 0  # Number of RAG context chunks injected
    metadata: dict = field(default_factory=dict)  # Agent-specific output metadata


# ── LangGraph State ────────────────────────────────────────────────────────────


class AgentState(dict):  # type: ignore[type-arg]
    """LangGraph state dict shared across all nodes in an agent graph.

    Uses Annotated[list, add_messages] for messages so LangGraph can
    correctly append rather than overwrite the message history.
    """

    messages: Annotated[list, add_messages]
    query: str
    user_id: str
    trip_id: str | None
    budget: float | None
    rag_context: str  # Formatted RAG chunks for LLM injection
    llm_response: str  # Raw LLM output
    final_output: AgentOutput | None
    error: str | None
