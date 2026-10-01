"""Benchmark matrix runner: per-context-size warmup, semaphore-bounded cells, hard per-request deadline."""

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from .client import RequestResult, request_completion
from .prompts import filler_prompt


@dataclass
class CellResult:
    context_size: int
    concurrency: int
    wall_s: float
    results: list[RequestResult] = field(default_factory=list)


def _req(client, prompt, size, conc, warmup, common):
    return request_completion(client, prompt=prompt, context_size=size, concurrency=conc, warmup=warmup, **common)


async def _deadline(coro, size, conc, warmup, deadline):
    try:
        return await asyncio.wait_for(coro, timeout=deadline)
    except asyncio.TimeoutError:
        return RequestResult(size, conc, warmup, False, "deadline", 0, 0, 0.0, 0.0, deadline * 1000)
    except Exception as exc: return RequestResult(size, conc, warmup, False, str(exc) or type(exc).__name__, 0, 0, 0.0, 0.0, deadline * 1000)


async def _cell_request(sem, coro, size, conc, deadline):
    async with sem:
        return await _deadline(coro, size, conc, False, deadline)


async def run_benchmark(cfg: dict, api_key: str) -> tuple[list[CellResult], list[RequestResult]]:
    model = cfg["model"]
    bench = cfg["benchmark"]
    deadline = bench["timeout_seconds"] * (bench["retries"] + 1) + 30
    common = dict(model=model["id"], options=model.get("options") or {}, max_tokens=bench["max_tokens"],
                  timeout_s=bench["timeout_seconds"], retries=bench["retries"])
    prompts: dict[int, str] = {}
    warmups: list[RequestResult] = []
    cells: list[CellResult] = []
    async with httpx.AsyncClient(base_url=model["endpoint"], headers={"Authorization": f"Bearer {api_key}"},
                                 timeout=httpx.Timeout(bench["timeout_seconds"], connect=10.0)) as client:
        for size in bench["context_sizes"]:
            prompt = prompts.setdefault(size, filler_prompt(size))
            warmups.append(await _deadline(_req(client, prompt, size, 1, True, common), size, 1, True, deadline))
            for conc in bench["concurrency_levels"]:
                t0 = time.perf_counter()
                sem = asyncio.Semaphore(conc)
                results = await asyncio.gather(
                    *(_cell_request(sem, _req(client, prompt, size, conc, False, common), size, conc, deadline)
                      for _ in range(bench["requests_per_cell"])))
                wall_s = time.perf_counter() - t0
                cells.append(CellResult(size, conc, wall_s, results))
                print(f"{size} tok x{conc}: {wall_s:.1f}s, {sum(r.ok for r in results)}/{len(results)} ok", flush=True)
    return cells, warmups
