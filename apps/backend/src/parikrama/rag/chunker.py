"""
Document chunking with configurable strategy.

Uses RecursiveCharacterTextSplitter which tries to split at:
1. Paragraphs (\\n\\n)
2. Sentences (. ! ?)
3. Hindi sentence boundary (। purna viram)
4. Words (spaces)
5. Characters (last resort)

This preserves semantic coherence within each chunk.
512-token chunks with 50-token overlap work best for travel content:
large enough for hotel + pricing context, small enough for precise retrieval.
"""
from __future__ import annotations

import structlog

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "langchain-text-splitters is required. Run: uv add langchain-text-splitters"
    ) from e

logger = structlog.get_logger(__name__)

# ── Chunking parameters ────────────────────────────────────────────────────────
# Roughly 4 characters per token for English/Hindi mixed text.
CHARS_PER_TOKEN: int = 4
CHUNK_SIZE_TOKENS: int = 512
CHUNK_OVERLAP_TOKENS: int = 50

# Computed character counts (what the splitter actually uses)
CHUNK_SIZE_CHARS: int = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
CHUNK_OVERLAP_CHARS: int = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN

# Ordered list of separators — tries top-level first, falls back
_SEPARATORS: list[str] = [
    "\n\n",  # paragraphs
    "\n",  # newlines
    "। ",  # Hindi sentence boundary (purna viram + space)
    "।",  # Hindi sentence boundary (purna viram alone)
    ". ",  # English sentence
    "! ",
    "? ",
    ", ",
    " ",  # words
    "",  # characters (last resort)
]


def create_splitter(
    chunk_size: int = CHUNK_SIZE_CHARS,
    chunk_overlap: int = CHUNK_OVERLAP_CHARS,
) -> RecursiveCharacterTextSplitter:
    """Build a RecursiveCharacterTextSplitter with PariKrama's standard parameters.

    Args:
        chunk_size: Max chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks in characters.

    Returns:
        Configured splitter instance.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=_SEPARATORS,
        is_separator_regex=False,
    )


def chunk_text(
    text: str,
    metadata: dict | None = None,
) -> list[dict]:
    """Split text into overlapping chunks suitable for embedding.

    Each chunk dictionary contains:
    - ``content``: The chunk text.
    - ``chunk_index``: Position within the original document.
    - ``token_count``: Estimated token count (char_count / 4).
    - ``metadata``: Merged caller metadata plus ``chunk_index``.

    Args:
        text: Full document text to split.
        metadata: Optional metadata to embed in every chunk
                  (e.g., ``{"destination": "Manali", "document_id": "..."}``).

    Returns:
        List of chunk dictionaries, ordered by position.
    """
    if not text.strip():
        logger.warning("chunk_text_empty_input")
        return []

    splitter = create_splitter()
    raw_chunks = splitter.split_text(text)

    chunks: list[dict] = []
    for i, content in enumerate(raw_chunks):
        token_count = max(1, len(content) // CHARS_PER_TOKEN)
        chunks.append(
            {
                "content": content,
                "chunk_index": i,
                "token_count": token_count,
                "metadata": {**(metadata or {}), "chunk_index": i},
            }
        )

    avg_tokens = (
        sum(c["token_count"] for c in chunks) // len(chunks) if chunks else 0
    )
    logger.info(
        "text_chunked",
        total_chunks=len(chunks),
        avg_tokens=avg_tokens,
        total_chars=len(text),
    )
    return chunks


def chunk_pages(
    pages: list[str],
    metadata: dict | None = None,
) -> list[dict]:
    """Chunk a list of page texts (e.g., from PDF extraction).

    Each chunk gets a ``page`` key in its metadata.

    Args:
        pages: List of strings, one per page.
        metadata: Optional base metadata dict.

    Returns:
        Flat list of chunk dicts across all pages.
    """
    all_chunks: list[dict] = []
    global_index = 0

    for page_num, page_text in enumerate(pages, start=1):
        page_metadata = {**(metadata or {}), "page": page_num}
        page_chunks = chunk_text(page_text, metadata=page_metadata)
        for chunk in page_chunks:
            chunk["chunk_index"] = global_index
            chunk["metadata"]["chunk_index"] = global_index
            global_index += 1
        all_chunks.extend(page_chunks)

    return all_chunks
