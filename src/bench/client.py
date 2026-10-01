"""Streaming chat-completion client with TTFT, generation timing, usage capture, and transient retry."""

import json
import time
from dataclasses import dataclass

import httpx


@dataclass
class RequestResult:
    context_size: int
    concurrency: int
    warmup: bool
    ok: bool
    error: str | None
    prompt_tokens: int
    completion_tokens: int
    ttft_ms: float
    gen_ms: float
    wall_ms: float


async def request_completion(
    client: httpx.AsyncClient,
    *,
    model: str,
    options: dict,
    prompt: str,
    max_tokens: int,
    timeout_s: float,
    context_size: int,
    concurrency: int,
    warmup: bool,
    retries: int = 1,
) -> RequestResult:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        **options,
    }
    t_start = time.perf_counter()
    for _ in range(retries + 1):
        t0 = time.perf_counter()
        t_first = t_last = usage = error = None
        transient = False
        try:
            async with client.stream("POST", "/chat/completions", json=body, timeout=timeout_s) as resp:
                if resp.status_code >= 400:
                    error = f"http {resp.status_code}"
                    transient = resp.status_code >= 500
                else:
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            payload = None
                        if not isinstance(payload, dict):
                            error = "malformed sse"
                            break
                        if isinstance(payload.get("usage"), dict):
                            usage = payload["usage"]
                        choices = payload.get("choices")
                        first = choices[0] if isinstance(choices, list) and choices else None
                        delta = first.get("delta") if isinstance(first, dict) else None
                        if isinstance(delta, dict) and any(delta.get(k) for k in ("content", "reasoning", "reasoning_content")):
                            now = time.perf_counter()
                            if t_first is None:
                                t_first = now
                            t_last = now
        except httpx.TransportError as exc:
            error = str(exc) or type(exc).__name__
            transient = True
        if not transient:
            break
    ok = t_first is not None and usage is not None and error is None
    if not ok:
        error = error or ("no usage in stream" if t_first is not None else "empty stream")
        t_first = t_last = None
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    ttft_ms = (t_first - t0) * 1000 if t_first is not None else 0.0
    gen_ms = (t_last - t_first) * 1000 if t_first is not None else 0.0
    wall_ms = (time.perf_counter() - t_start) * 1000
    return RequestResult(
        context_size,
        concurrency,
        warmup,
        ok,
        error,
        prompt_tokens,
        completion_tokens,
        ttft_ms,
        gen_ms,
        wall_ms,
    )
