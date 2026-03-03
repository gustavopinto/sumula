"""Async retry utility for extractors. Max 3 attempts, exponential backoff."""
import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 3
BASE_BACKOFF = 2.0  # seconds; attempt N waits BASE_BACKOFF^N


async def with_retries(
    coro_fn: Callable[[], Awaitable[T]],
    source: str = "",
    max_attempts: int = MAX_ATTEMPTS,
) -> T | None:
    """
    Call coro_fn up to max_attempts times.
    Returns the result on first success.
    Returns None (soft failure) if all attempts fail — never raises.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn()
        except Exception as exc:
            if attempt < max_attempts:
                wait = BASE_BACKOFF ** attempt
                logger.warning(
                    "[%s] tentativa %d/%d falhou: %s — aguardando %.0fs",
                    source, attempt, max_attempts, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "[%s] falhou após %d tentativas: %s — não tentará novamente",
                    source, max_attempts, exc,
                )
    return None
