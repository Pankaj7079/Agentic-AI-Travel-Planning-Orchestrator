"""
ItineraryAgent — generates day-wise travel itineraries.

LangGraph flow:
  retrieve_context → call_llm → format_output

The agent RAG-searches for destination-specific knowledge before calling
the LLM, so it can include real hotel names, typical costs, and local tips
from uploaded travel guides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from parikrama.agents.base import BaseAgent
from parikrama.agents.prompts.itinerary import ITINERARY_SYSTEM_PROMPT
from parikrama.agents.schemas import AgentOutput, AgentState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter


class ItineraryAgent(BaseAgent):
    """Generates day-wise travel itineraries grounded in RAG knowledge.

    Usage::

        agent = ItineraryAgent(llm_router, db)
        output = await agent.run(AgentInput(
            query="Delhi to Manali 5 days budget 15000",
            user_id="<uuid>",
            budget=15000,
        ))
        print(output.content)
    """

    agent_name = "ItineraryAgent"
    rag_query_template = "travel itinerary {query} places to visit budget accommodation"
    rag_top_k = 5

    def __init__(self, llm_router: LLMRouter, db: AsyncSession) -> None:
        super().__init__(llm_router, db)

    @property
    def _system_prompt(self) -> str:
        return ITINERARY_SYSTEM_PROMPT

    def build_graph(self):  # type: ignore[return]
        """Build the ItineraryAgent LangGraph StateGraph."""
        graph = StateGraph(AgentState)

        graph.add_node("retrieve_context", self._node_retrieve_context)
        graph.add_node("call_llm", self._node_call_llm)
        graph.add_node("format_output", self._node_format_output)

        graph.set_entry_point("retrieve_context")
        graph.add_edge("retrieve_context", "call_llm")
        graph.add_edge("call_llm", "format_output")
        graph.add_edge("format_output", END)

        return graph.compile()

    async def _node_format_output(self, state: AgentState) -> AgentState:
        """Format the raw LLM response into a structured AgentOutput."""
        rag_ctx = state.get("rag_context", "")
        rag_chunks = len(rag_ctx.split("---")) if rag_ctx else 0

        state["final_output"] = AgentOutput(
            content=state["llm_response"],
            agent=self.agent_name,
            provider=str(state.get("llm_provider", "unknown")),
            model=str(state.get("llm_model", "unknown")),
            latency_ms=int(state.get("llm_latency_ms", 0)),
            rag_chunks_used=rag_chunks,
            metadata={
                "input_tokens": state.get("llm_input_tokens", 0),
                "output_tokens": state.get("llm_output_tokens", 0),
                "had_rag_context": bool(rag_ctx),
            },
        )
        return state
