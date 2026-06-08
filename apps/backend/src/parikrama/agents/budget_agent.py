"""
BudgetAgent — breaks down a trip budget into realistic cost categories.

LangGraph flow:
  retrieve_context → call_llm → format_output

The agent extracts a budget from the query, searches RAG for local
pricing data, then generates a structured cost breakdown table.
"""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from parikrama.agents.base import BaseAgent
from parikrama.agents.prompts.budget import BUDGET_SYSTEM_PROMPT
from parikrama.agents.schemas import AgentOutput, AgentState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.llm.router import LLMRouter


class BudgetAgent(BaseAgent):
    """Breaks down a trip budget into transport, stay, food, and activities.

    Usage::

        agent = BudgetAgent(llm_router, db)
        output = await agent.run(AgentInput(
            query="Budget breakdown Delhi to Manali 5 days 15000 rupees",
            user_id="<uuid>",
            budget=15000,
        ))
        print(output.content)
    """

    agent_name = "BudgetAgent"
    rag_query_template = "cost price budget {query} accommodation transport food"
    rag_top_k = 4

    def __init__(self, llm_router: LLMRouter, db: AsyncSession) -> None:
        super().__init__(llm_router, db)

    @property
    def _system_prompt(self) -> str:
        return BUDGET_SYSTEM_PROMPT

    def build_graph(self):  # type: ignore[return]
        """Build the BudgetAgent LangGraph StateGraph."""
        graph = StateGraph(AgentState)

        graph.add_node("extract_budget", self._node_extract_budget)
        graph.add_node("retrieve_context", self._node_retrieve_context)
        graph.add_node("call_llm", self._node_call_llm)
        graph.add_node("format_output", self._node_format_output)

        graph.set_entry_point("extract_budget")
        graph.add_edge("extract_budget", "retrieve_context")
        graph.add_edge("retrieve_context", "call_llm")
        graph.add_edge("call_llm", "format_output")
        graph.add_edge("format_output", END)

        return graph.compile()

    async def _node_extract_budget(self, state: AgentState) -> AgentState:
        """Extract numeric budget from query text if not already provided."""
        if state.get("budget"):
            return state
        # Try to extract a number from query like "budget 15000" or "₹15,000"
        query = state["query"]
        match = re.search(r"(?:₹|rs\.?|inr|budget)?\s*([\d,]+)", query, re.IGNORECASE)
        if match:
            budget_str = match.group(1).replace(",", "")
            with contextlib.suppress(ValueError):
                state["budget"] = float(budget_str)
        return state

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
                "extracted_budget": state.get("budget"),
                "input_tokens": state.get("llm_input_tokens", 0),
                "output_tokens": state.get("llm_output_tokens", 0),
                "had_rag_context": bool(rag_ctx),
            },
        )
        return state
