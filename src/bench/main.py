"""Benchmark CLI: --smoke does one request; default runs the matrix and writes the report."""

import sys
from pathlib import Path

if __package__ is None:  # direct script run (python src/bench/main.py): re-execute as bench.main
    import runpy
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    runpy.run_module("bench.main", run_name="__main__")
    raise SystemExit(0)

import argparse, asyncio, os

import httpx, yaml
from dotenv import load_dotenv

from .client import request_completion
from .prompts import filler_prompt
from .report import write_report
from .runner import run_benchmark

SMOKE_TARGET = 256


async def _smoke(cfg: dict, api_key: str) -> None:
    model, bench = cfg["model"], cfg["benchmark"]
    timeout = bench["timeout_seconds"]
    async with httpx.AsyncClient(base_url=model["endpoint"], headers={"Authorization": f"Bearer {api_key}"},
                                 timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        r = await request_completion(client, model=model["id"], options=model.get("options") or {},
                                     prompt=filler_prompt(SMOKE_TARGET), max_tokens=32, timeout_s=timeout,
                                     context_size=SMOKE_TARGET, concurrency=1, warmup=False, retries=0)
    print(f"smoke: {r.ok} prompt={r.prompt_tokens}tok completion={r.completion_tokens}tok ttft={r.ttft_ms:.0f}ms gen={r.gen_ms:.0f}ms {r.error or ''}".rstrip())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()
    load_dotenv()
    api_key = os.environ.get("HYPERQWEN_API_KEY") or ""
    if not api_key:
        print("error: HYPERQWEN_API_KEY not set (.env)", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(Path(args.config).read_text())
    model, report_dir = cfg["model"], cfg["report"]["output_dir"]
    if args.smoke:
        asyncio.run(_smoke(cfg, api_key))
    else:
        cells, warmups = asyncio.run(run_benchmark(cfg, api_key))
        d = write_report(report_dir, cells, warmups, model["id"], model["endpoint"])
        print(f"report: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
