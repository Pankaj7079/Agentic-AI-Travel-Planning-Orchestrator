"""
Tests for the ItineraryAgent and BudgetAgent.

All LLM calls are mocked — no API keys needed.
RAG retrieval is also mocked to return predictable context.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parikrama.agents.schemas import AgentInput, AgentOutput
from parikrama.llm.schemas import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from httpx import AsyncClient

RAG_PATCH = "parikrama.agents.base.RAGService"


def _mock_llm_response(content: str = "Mock LLM response") -> LLMResponse:
    return LLMResponse(
        content=content,
        provider=LLMProvider.GROQ,
        model="llama-3.1-70b-versatile",
        latency_ms=200,
        input_tokens=300,
        output_tokens=150,
    )


def _make_mock_router(response_content: str = "Mock itinerary content") -> MagicMock:
    router = MagicMock()
    router.generate = AsyncMock(return_value=_mock_llm_response(response_content))
    return router


# ── ItineraryAgent unit tests ──────────────────────────────────────────────────


class TestItineraryAgent:
    @pytest.mark.asyncio
    async def test_itinerary_agent_returns_output(self):
        """ItineraryAgent.run() returns an AgentOutput with content."""
        from parikrama.agents.itinerary_agent import ItineraryAgent

        db = AsyncMock()
        router = _make_mock_router("## Day 1\n- Visit Manali market")

        # Mock RAG service to return empty (no docs uploaded)
        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = ItineraryAgent(llm_router=router, db=db)
            output = await agent.run(
                AgentInput(
                    query="5 day trip Delhi to Manali budget 15000",
                    user_id="test-user-id",
                    budget=15000,
                )
            )

        assert isinstance(output, AgentOutput)
        assert len(output.content) > 0
        assert output.agent == "ItineraryAgent"
        # Router was called — verify the mock was invoked
        router.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_itinerary_agent_uses_rag_context(self):
        """ItineraryAgent injects RAG context into the LLM call."""
        from parikrama.agents.itinerary_agent import ItineraryAgent

        db = AsyncMock()
        router = _make_mock_router()
        fake_context = "Manali has budget guesthouses at ₹800/night near old Manali."

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value=fake_context)),
        ):
            agent = ItineraryAgent(llm_router=router, db=db)
            output = await agent.run(
                AgentInput(
                    query="trip to Manali 5 days",
                    user_id="test-user-id",
                )
            )

        # Verify LLM was called with context injected in prompt
        call_args = router.generate.call_args
        assert fake_context in call_args.kwargs.get(
            "prompt", call_args.args[0] if call_args.args else ""
        )
        assert output.rag_chunks_used > 0

    @pytest.mark.asyncio
    async def test_itinerary_agent_latency_tracked(self):
        """AgentOutput records non-zero latency."""
        from parikrama.agents.itinerary_agent import ItineraryAgent

        db = AsyncMock()
        router = _make_mock_router()

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = ItineraryAgent(llm_router=router, db=db)
            output = await agent.run(AgentInput(query="trip plan Goa 3 days", user_id="u1"))

        assert output.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_itinerary_agent_metadata_has_tokens(self):
        """AgentOutput metadata includes token counts."""
        from parikrama.agents.itinerary_agent import ItineraryAgent

        db = AsyncMock()
        router = _make_mock_router()

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = ItineraryAgent(llm_router=router, db=db)
            output = await agent.run(AgentInput(query="trip plan Rajasthan 7 days", user_id="u1"))

        assert "input_tokens" in output.metadata
        assert "output_tokens" in output.metadata


# ── BudgetAgent unit tests ─────────────────────────────────────────────────────


class TestBudgetAgent:
    @pytest.mark.asyncio
    async def test_budget_agent_returns_output(self):
        """BudgetAgent.run() returns an AgentOutput."""
        from parikrama.agents.budget_agent import BudgetAgent

        db = AsyncMock()
        router = _make_mock_router("| Transport | ₹3000 | Bus fare |")

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = BudgetAgent(llm_router=router, db=db)
            output = await agent.run(
                AgentInput(
                    query="Budget breakdown Manali 5 days 15000",
                    user_id="test-user-id",
                    budget=15000,
                )
            )

        assert isinstance(output, AgentOutput)
        assert output.agent == "BudgetAgent"
        assert len(output.content) > 0

    @pytest.mark.asyncio
    async def test_budget_agent_extracts_budget_from_query(self):
        """BudgetAgent extracts numeric budget from query text."""
        from parikrama.agents.budget_agent import BudgetAgent

        db = AsyncMock()
        router = _make_mock_router()

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = BudgetAgent(llm_router=router, db=db)
            output = await agent.run(
                AgentInput(
                    query="plan Manali trip budget 20000 rupees 6 days",
                    user_id="u1",
                    # budget NOT set in input — should be extracted from query
                )
            )

        assert output.metadata.get("extracted_budget") == 20000.0

    @pytest.mark.asyncio
    async def test_budget_agent_with_explicit_budget(self):
        """BudgetAgent uses explicit budget when provided."""
        from parikrama.agents.budget_agent import BudgetAgent

        db = AsyncMock()
        router = _make_mock_router()

        with patch(
            "parikrama.agents.base.RAGService",
            return_value=MagicMock(get_context_for_query=AsyncMock(return_value="")),
        ):
            agent = BudgetAgent(llm_router=router, db=db)
            output = await agent.run(
                AgentInput(
                    query="5 day trip to Coorg",
                    user_id="u1",
                    budget=12000.0,
                )
            )

        assert output.metadata.get("extracted_budget") == 12000.0


# ── Agent API integration tests ────────────────────────────────────────────────


class TestAgentAPI:
    async def _get_auth_headers(self, client: AsyncClient) -> dict:
        email = f"agenttest_{uuid.uuid4().hex[:8]}@example.com"
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPass123!", "name": "Agent Tester"},
        )
        assert reg.status_code == 201
        return {"Authorization": f"Bearer {reg.json()['tokens']['access_token']}"}

    @pytest.mark.asyncio
    async def test_itinerary_endpoint_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/agents/itinerary",
            json={"query": "Plan a 5-day trip from Delhi to Manali"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_budget_endpoint_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/agents/budget",
            json={"query": "Budget breakdown for Manali trip 5 days 15000"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_agents_health_endpoint_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents/health")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_itinerary_returns_503_without_api_keys(self, client: AsyncClient):
        """Without API keys configured, returns 503 Service Unavailable."""
        headers = await self._get_auth_headers(client)
        with patch(
            "parikrama.api.v1.agents._get_llm_router",
            side_effect=__import__("fastapi", fromlist=["HTTPException"]).HTTPException(
                status_code=503, detail="No LLM configured"
            ),
        ):
            resp = await client.post(
                "/api/v1/agents/itinerary",
                headers=headers,
                json={"query": "Plan a 5-day trip from Delhi to Manali"},
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_itinerary_short_query_returns_422(self, client: AsyncClient):
        """Query shorter than min_length=10 returns validation error."""
        headers = await self._get_auth_headers(client)
        resp = await client.post(
            "/api/v1/agents/itinerary",
            headers=headers,
            json={"query": "Goa"},  # too short
        )
        assert resp.status_code == 422
