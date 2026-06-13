"""LLM 模块单元测试：chat 参数构造、重试逻辑。不调用真实 API。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_service.client import chat
from app.ai_service.exceptions import LLMNotConfiguredError


@pytest.fixture
def mock_api_key():
    """chat 需 MINIMAX_API_KEY；单测不读真实 .env。"""
    with patch("app.ai_service.providers.minimax.MINIMAX_API_KEY", "test-key"):
        yield


class TestChatParams:
    @pytest.mark.asyncio
    async def test_chat_requires_api_key(self):
        with patch("app.ai_service.providers.minimax.MINIMAX_API_KEY", ""):
            with pytest.raises(LLMNotConfiguredError):
                await chat([{"role": "user", "content": "hi"}], max_retries=1)

    @pytest.mark.asyncio
    async def test_chat_think_true(self, mock_api_key):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hello"

        with patch(
            "app.ai_service.providers.minimax.MiniMaxProvider._get_client"
        ) as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get.return_value = mock_client

            result = await chat(
                [{"role": "user", "content": "hi"}],
                think=True,
                max_retries=1,
            )
            assert result == "hello"
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs.get("extra_body") is None

    @pytest.mark.asyncio
    async def test_chat_think_false(self, mock_api_key):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hello"

        with patch(
            "app.ai_service.providers.minimax.MiniMaxProvider._get_client"
        ) as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get.return_value = mock_client

            result = await chat(
                [{"role": "user", "content": "hi"}],
                think=False,
                max_retries=1,
            )
            assert result == "hello"
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["extra_body"] == {"reasoning_split": True}

    @pytest.mark.asyncio
    async def test_chat_empty_response_raises(self, mock_api_key):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = None

        with patch(
            "app.ai_service.providers.minimax.MiniMaxProvider._get_client"
        ) as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get.return_value = mock_client

            with pytest.raises(RuntimeError, match="彻底失败"):
                await chat(
                    [{"role": "user", "content": "hi"}],
                    max_retries=1,
                    base_delay_ms=0,
                )

    @pytest.mark.asyncio
    async def test_chat_retry_on_error(self, mock_api_key):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "ok"

        with patch(
            "app.ai_service.providers.minimax.MiniMaxProvider._get_client"
        ) as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[Exception("timeout"), mock_completion]
            )
            mock_get.return_value = mock_client

            result = await chat(
                [{"role": "user", "content": "hi"}],
                max_retries=2,
                base_delay_ms=0,
            )
            assert result == "ok"
            assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_all_retries_exhausted(self, mock_api_key):
        with patch(
            "app.ai_service.providers.minimax.MiniMaxProvider._get_client"
        ) as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("fail")
            )
            mock_get.return_value = mock_client

            with pytest.raises(RuntimeError, match="彻底失败"):
                await chat(
                    [{"role": "user", "content": "hi"}],
                    max_retries=2,
                    base_delay_ms=0,
                )
            assert mock_client.chat.completions.create.call_count == 2
