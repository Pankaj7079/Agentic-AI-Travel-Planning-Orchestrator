"""
Shared enums used across backend, worker, and MCP server.

Single source of truth — if you add a status, add it here.
"""

from enum import StrEnum


class TripStatus(StrEnum):
    """Trip lifecycle states."""

    PENDING = "pending"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AgentName(StrEnum):
    """Agent identifiers in the orchestration graph."""

    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    BOOKING = "booking"
    BUDGET = "budget"
    ITINERARY = "itinerary"


class AgentRunStatus(StrEnum):
    """Status of individual agent executions."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class DocumentStatus(StrEnum):
    """Document processing pipeline states."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    FAILED = "failed"


class NotificationType(StrEnum):
    """Notification categories for filtering and routing."""

    TRIP_UPDATE = "trip_update"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESULT = "approval_result"
    SYSTEM = "system"
    DOCUMENT_READY = "document_ready"


class ApprovalStatus(StrEnum):
    """Approval request states."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class LLMProvider(StrEnum):
    """LLM provider identifiers for routing and cost tracking."""

    GEMINI = "gemini"
    GROQ_LLAMA = "groq_llama"
    GROQ_MIXTRAL = "groq_mixtral"
