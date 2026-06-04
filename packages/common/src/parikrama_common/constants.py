"""Shared constants used across all PariKrama services."""

# API versioning
API_V1_PREFIX = "/api/v1"

# pagination defaults
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# token limits for LLM calls
MAX_CONTEXT_TOKENS = 8192
MAX_OUTPUT_TOKENS = 4096

# RAG defaults
DEFAULT_CHUNK_SIZE_TOKENS = 512
DEFAULT_CHUNK_OVERLAP_TOKENS = 50
DEFAULT_EMBEDDING_DIMENSION = 384

# approval timeout (seconds)
APPROVAL_TIMEOUT_SECONDS = 3600  # 1 hour

# rate limits
AUTH_RATE_LIMIT = "5/minute"
REGISTER_RATE_LIMIT = "3/minute"
API_RATE_LIMIT = "100/minute"
TRIP_RATE_LIMIT = "10/minute"
