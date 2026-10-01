"""Writes timestamped run artifacts: requests.jsonl, summary.csv, report.md."""

import csv
import dataclasses
import json
from datetime import datetime
from pathlib import Path

from .client import RequestResult
from .runner import CellResult


def _derive(r: RequestResult) -> dict:
    return {
        "pp_tps": r.prompt_tokens / (r.ttft_ms / 1000) if r.ok and r.ttft_ms > 0 else None,
        "tg_tps": r.completion_tokens / (r.gen_ms / 1000) if r.ok and r.gen_ms > 0 else None,
    }


def _pct(s: list[float], q: float) -> float:
    return s[min(len(s) - 1, int(q * len(s)))]


def _cell_row(cell: CellResult) -> list[str]:
    ok = [r for r in cell.results if r.ok]
    n_ok, n = len(ok), len(cell.results)
    row = [str(cell.context_size), str(cell.concurrency), str(n_ok), str(n - n_ok), f"{(n - n_ok) / n:.3f}" if n else ""]
    if not ok:
        return row + [""] * 9
    t = sorted(r.ttft_ms for r in ok)
    pps = [r.prompt_tokens / (r.ttft_ms / 1000) for r in ok if r.ttft_ms > 0]
    tgs = [r.completion_tokens / (r.gen_ms / 1000) for r in ok if r.gen_ms > 0]
    return row + [
        f"{sum(r.prompt_tokens for r in ok) / n_ok:.1f}",
        f"{sum(t) / n_ok:.1f}",
        f"{_pct(t, 0.5):.1f}",
        f"{_pct(t, 0.95):.1f}",
        f"{_pct(t, 0.99):.1f}",
        f"{sum(pps) / len(pps):.1f}" if pps else "",
        f"{sum(tgs) / len(tgs):.1f}" if tgs else "",
        f"{sum(r.completion_tokens for r in ok) / cell.wall_s:.1f}" if cell.wall_s > 0 else "",
        f"{cell.wall_s:.1f}",
    ]


def write_report(out_dir: Path | str, cells: list[CellResult], warmups: list[RequestResult], model: str, endpoint: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(out_dir) / ts
    d.mkdir(parents=True, exist_ok=True)
    reqs = warmups + [r for c in cells for r in c.results]
    with (d / "requests.jsonl").open("w") as f:
        f.writelines(json.dumps({**dataclasses.asdict(r), **_derive(r), "model": model, "endpoint": endpoint}) + "\n" for r in reqs)
    rows = [_cell_row(c) for c in cells]
    with (d / "summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["context_size", "concurrency", "n_ok", "n_err", "error_rate", "avg_prompt_tokens", "ttft_mean_ms", "ttft_p50_ms",
                    "ttft_p95_ms", "ttft_p99_ms", "pp_tps", "tg_tps", "agg_tps", "wall_s"])
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in reqs:
        if r.error:
            counts[r.error] = counts.get(r.error, 0) + 1
    lines = [f"# LLM benchmark — {model}", "", f"- endpoint: {endpoint}", f"- run: {ts}", "",
             "| context (target) | avg prompt tok | conc | ok/err | TTFT p50 (ms) | TTFT p95 (ms) | PP (tok/s) | TG (tok/s) | agg (tok/s) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += ["| " + " | ".join("-" if v == "" else v for v in (r[0], r[5], r[1], f"{r[2]}/{r[3]}", r[7], r[8], r[10], r[11], r[12])) + " |" for r in rows]
    if counts:
        lines += ["", "## Errors"] + [f"- {e}: {c}" for e, c in sorted(counts.items(), key=lambda kv: -kv[1])]
    (d / "report.md").write_text("\n".join(lines) + "\n")
    return d
