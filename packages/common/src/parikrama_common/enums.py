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


class TransportType(StrEnum):
    """
    Supported transport modes for Indian travel.

    The booking agent searches across all three types and
    returns options sorted by value-for-money.
    """

    BUS = "bus"  # Volvo, sleeper, semi-sleeper (RedBus, AbhiBus)
    TRAIN = "train"  # IRCTC classes: SL, 3A, 2A, 1A, CC
    FLIGHT = "flight"  # Domestic airlines (IndiGo, SpiceJet, etc.)


class TransportClass(StrEnum):
    """
    Sub-classes within each transport type.

    Used by the booking agent to match user's budget tier.
    """

    # Bus classes
    BUS_ORDINARY = "ordinary"
    BUS_SEMI_SLEEPER = "semi_sleeper"
    BUS_SLEEPER = "sleeper"
    BUS_VOLVO_AC = "volvo_ac"
    BUS_LUXURY = "luxury"

    # Train classes (IRCTC)
    TRAIN_GENERAL = "general"  # GN — unreserved
    TRAIN_SLEEPER = "sleeper"  # SL
    TRAIN_AC_3TIER = "ac_3tier"  # 3A
    TRAIN_AC_2TIER = "ac_2tier"  # 2A
    TRAIN_AC_FIRST = "ac_first"  # 1A
    TRAIN_AC_CHAIR = "ac_chair"  # CC

    # Flight classes
    FLIGHT_ECONOMY = "economy"
    FLIGHT_BUSINESS = "business"


class UserRole(StrEnum):
    """User roles for authorization."""

    USER = "user"
    ADMIN = "admin"


class AuthProvider(StrEnum):
    """Authentication provider types."""

    LOCAL = "local"  # email + password
    GOOGLE = "google"  # Google OAuth
