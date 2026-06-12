"""LLM 模块单元测试：客户端单例、chat 参数构造、重试逻辑。不调用真实 API。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm import _get_client, chat


class TestGetClient:
    def test_singleton(self):
        import app.core.llm as mod
        mod._client = None
        c1 = _get_client()
        c2 = _get_client()
        assert c1 is c2

    def test_client_config(self):
        import app.core.llm as mod
        mod._client = None
        c = _get_client()
        assert c.api_key is not None
        assert c.base_url is not None
        mod._client = None


class TestChatParams:
    @pytest.mark.asyncio
    async def test_chat_think_true(self):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hello"

        with patch("app.core.llm._get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get.return_value = mock_client

            result = await chat(
                [{"role": "user", "content": "hi"}],
                think=True,
                max_retries=1,
            )
            assert result == "hello"
            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs.kwargs.get("extra_body") is None or call_kwargs.kwargs.kwargs.get("extra_body") == {}

    @pytest.mark.asyncio
    async def test_chat_think_false(self):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hello"

        with patch("app.core.llm._get_client") as mock_get:
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
    async def test_chat_empty_response_raises(self):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = None

        with patch("app.core.llm._get_client") as mock_get:
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
    async def test_chat_retry_on_error(self):
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "ok"

        with patch("app.core.llm._get_client") as mock_get:
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
    async def test_chat_all_retries_exhausted(self):
        with patch("app.core.llm._get_client") as mock_get:
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
