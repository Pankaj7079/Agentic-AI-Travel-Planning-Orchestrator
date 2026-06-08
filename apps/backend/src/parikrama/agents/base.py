"""
Abstract BaseAgent — LangGraph-powered parent class for all PariKrama travel agents.

All agents inherit from BaseAgent and implement:
  - build_graph()  — define the LangGraph StateGraph
  - _system_prompt — property returning the agent's system instruction

The base class provides:
  - run(input) → AgentOutput  with full observability (logs, latency)
  - retrieve_context(state)   shared RAG retrieval node
  - A pre-wired LLMRouter and RAGService reference
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

from parikrama.agents.schemas import AgentInput, AgentOutput, AgentState
from parikrama.services.rag_service import RAGService  # imported here so tests can patch it

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract parent class for all PariKrama travel agents.

    Concrete agents must implement:
        build_graph() → CompiledStateGraph

    They should also set:
        agent_name: str  class attribute
        rag_query_template: str  f-string template for RAG query
    """

    agent_name: str = "BaseAgent"
    rag_query_template: str = "{query}"
    rag_top_k: int = 5

    def __init__(self, llm_router: LLMRouter, db: AsyncSession) -> None:
        self._router = llm_router
        self._db = db
        self._graph: CompiledStateGraph | None = None

    @property
    @abstractmethod
    def _system_prompt(self) -> str:
        """System instruction for the LLM. Override in each agent."""

    @abstractmethod
    def build_graph(self):  # type: ignore[return]
        """Build and compile the LangGraph StateGraph. Override in each agent."""

    def _get_graph(self):  # type: ignore[return]
        """Lazy-compile the graph on first call."""
        if self._graph is None:
            self._graph = self.build_graph()
        return self._graph

    # ── Public interface ────────────────────────────────────────────────────

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """Execute the agent pipeline end-to-end.

        Args:
            agent_input: Standardized AgentInput with query, user_id, etc.

        Returns:
            AgentOutput with content, provider, latency.
        """
        log = logger.bind(
            agent=self.agent_name,
            user_id=agent_input.user_id,
            query_snippet=agent_input.query[:60],
        )
        log.info("agent_run_started")
        start = time.monotonic()

        initial_state: AgentState = AgentState(
            messages=[],
            query=agent_input.query,
            user_id=agent_input.user_id,
            trip_id=agent_input.trip_id,
            budget=agent_input.budget,
            rag_context="",
            llm_response="",
            final_output=None,
            error=None,
        )

        try:
            graph = self._get_graph()
            final_state = await graph.ainvoke(initial_state)
            output: AgentOutput = final_state.get("final_output") or AgentOutput(
                content=final_state.get("llm_response", "No response generated."),
                agent=self.agent_name,
                provider="unknown",
                model="unknown",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            log.error("agent_run_failed", error=str(exc), latency_ms=latency)
            raise

        log.info(
            "agent_run_completed",
            latency_ms=output.latency_ms,
            provider=output.provider,
            rag_chunks=output.rag_chunks_used,
        )
        return output

    # ── Shared graph nodes ──────────────────────────────────────────────────

    async def _node_retrieve_context(self, state: AgentState) -> AgentState:
        """Shared LangGraph node: retrieve RAG context for the query."""
        rag = RAGService(self._db)
        rag_query = self.rag_query_template.format(
            query=state["query"],
            budget=state.get("budget", ""),
        )
        context = await rag.get_context_for_query(
            query=rag_query,
            top_k=self.rag_top_k,
            user_id=state["user_id"],
        )
        logger.debug(
            "rag_context_retrieved",
            agent=self.agent_name,
            context_len=len(context),
            had_results=bool(context),
        )
        state["rag_context"] = context
        return state

    async def _node_call_llm(self, state: AgentState) -> AgentState:
        """Shared LangGraph node: call the LLM router with context-enriched prompt."""
        rag_section = (
            f"\n\n## Relevant Knowledge Base Context\n{state['rag_context']}"
            if state.get("rag_context")
            else ""
        )
        prompt = f"{state['query']}{rag_section}"

        response = await self._router.generate(
            prompt=prompt,
            system=self._system_prompt,
            temperature=0.7,
        )

        state["llm_response"] = response.content
        state["llm_provider"] = response.provider  # type: ignore[assignment]
        state["llm_model"] = response.model  # type: ignore[assignment]
        state["llm_latency_ms"] = response.latency_ms  # type: ignore[assignment]
        state["llm_input_tokens"] = response.input_tokens  # type: ignore[assignment]
        state["llm_output_tokens"] = response.output_tokens  # type: ignore[assignment]
        return state
