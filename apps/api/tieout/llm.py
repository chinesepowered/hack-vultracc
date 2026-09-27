"""Vultr Serverless Inference client (OpenAI-compatible). The only LLM provider in this codebase."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from openai import APIError, APITimeoutError, AsyncOpenAI

from .config import settings

log = logging.getLogger("tieout.llm")


@dataclass
class LLMReply:
    message: object
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    finish_reason: str | None
    reasoning: str | None


class LLM:
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 fallback_model: str | None = None, timeout: float = 90):
        self.client = AsyncOpenAI(base_url=base_url or settings.inference_base_url, api_key=api_key or settings.inference_api_key,
                                  timeout=timeout, max_retries=0)
        self.model = model or settings.model_main
        self.fallback_model = fallback_model or settings.model_fast

    async def chat(self, messages: list[dict], *, tools: list[dict] | None = None, temperature: float = 0.1,
                   max_tokens: int = 8192, model: str | None = None) -> LLMReply:
        """Chat completion with retries and backoff, then one attempt on the fallback model."""
        models = [model or self.model]
        if self.fallback_model and self.fallback_model not in models:
            models.append(self.fallback_model)
        last: Exception | None = None
        for m_i, m in enumerate(models):
            attempts = 3 if m_i == 0 else 2
            for attempt in range(attempts):
                t0 = time.monotonic()
                try:
                    kwargs = dict(model=m, messages=messages, temperature=temperature, max_tokens=max_tokens)
                    if tools:
                        kwargs.update(tools=tools, tool_choice="auto")
                    if settings.reasoning_effort and m == self.model:
                        kwargs["extra_body"] = {"reasoning_effort": settings.reasoning_effort}
                    resp = await self.client.chat.completions.create(**kwargs)
                    choice = resp.choices[0]
                    usage = resp.usage
                    extra = getattr(choice.message, "model_extra", None) or {}
                    reasoning = extra.get("reasoning_content") or extra.get("reasoning")
                    return LLMReply(
                        message=choice.message, model=m,
                        tokens_in=getattr(usage, "prompt_tokens", 0) or 0, tokens_out=getattr(usage, "completion_tokens", 0) or 0,
                        latency_ms=int((time.monotonic() - t0) * 1000), finish_reason=choice.finish_reason,
                        reasoning=reasoning if isinstance(reasoning, str) else None,
                    )
                except (APIError, APITimeoutError, asyncio.TimeoutError) as exc:
                    last = exc
                    status = getattr(exc, "status_code", None)
                    log.warning("inference error model=%s attempt=%d status=%s: %s", m, attempt + 1, status, str(exc)[:200])
                    if status in (400, 401, 403, 404, 422):
                        break
                    await asyncio.sleep(1.5 * (2 ** attempt))
        raise RuntimeError(f"inference failed after retries and fallback: {last}")

    async def models(self) -> list[str]:
        page = await self.client.models.list()
        return sorted(m.id for m in page.data)
