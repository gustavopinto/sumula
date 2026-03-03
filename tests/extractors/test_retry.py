"""Unit tests for the retry mechanism — no network required."""
import asyncio
from unittest.mock import AsyncMock, call, patch

import pytest

from app.extractors._retry import with_retries


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    fn = AsyncMock(return_value="ok")
    result = await with_retries(fn, source="test")
    assert result == "ok"
    fn.assert_called_once()


@pytest.mark.asyncio
async def test_success_on_second_attempt():
    fn = AsyncMock(side_effect=[ValueError("fail"), "ok"])
    with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await with_retries(fn, source="test", max_attempts=3)
    assert result == "ok"
    assert fn.call_count == 2
    mock_sleep.assert_called_once_with(2.0)  # BASE_BACKOFF^1


@pytest.mark.asyncio
async def test_all_attempts_fail_returns_none():
    fn = AsyncMock(side_effect=RuntimeError("always fails"))
    with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock):
        result = await with_retries(fn, source="test", max_attempts=3)
    assert result is None
    assert fn.call_count == 3


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    fn = AsyncMock(side_effect=[ValueError(), ValueError(), ValueError()])
    with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await with_retries(fn, source="test", max_attempts=3)
    # attempt 1 fails → sleep 2^1=2; attempt 2 fails → sleep 2^2=4; attempt 3 fails → no sleep
    assert mock_sleep.call_args_list == [call(2.0), call(4.0)]


@pytest.mark.asyncio
async def test_no_retry_on_single_attempt():
    fn = AsyncMock(side_effect=ValueError("fail"))
    with patch("app.extractors._retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await with_retries(fn, source="test", max_attempts=1)
    assert result is None
    fn.assert_called_once()
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_does_not_raise_exception():
    """with_retries must never propagate an exception to the caller."""
    async def always_explodes():
        raise Exception("BOOM")

    result = await with_retries(always_explodes, source="test", max_attempts=3)
    assert result is None
