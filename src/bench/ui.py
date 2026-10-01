"""Rich/plain TUI for the benchmark run: live per-cell progress, warmup header, finish marker."""

from contextlib import nullcontext

from .client import RequestResult


class BenchTUI:
    def __init__(self, context_sizes: list[int], concurrency_levels: list[int], requests_per_cell: int, plain: bool = False):
        self.plain = plain
        self._order = [(s, c) for s in context_sizes for c in concurrency_levels]
        self._cells = {k: {"size": k[0], "conc": k[1], "n": requests_per_cell, "done": 0, "wall_s": None, "n_ok": 0, "phase": "pending"} for k in self._order}
        self._warmup = None
        self._finished = False
        self._total = self._ok = 0

    def on_request(self, size: int, conc: int | None, done: int, n: int, result: RequestResult) -> None:
        if conc is None:
            self._warmup = (size, done, n)
            self._total += 1
            self._ok += result.ok
            if self.plain:
                print(f"warmup: {size} tok: {result.error or 'ok'}", flush=True)
        else:
            cell = self._cells[(size, conc)]
            cell.update(done=done, n=n)
            cell["n_ok"] += result.ok
            self._warmup = None
            if cell["phase"] == "pending":
                cell["phase"] = "running"

    def on_cell(self, size: int, conc: int, wall_s: float, n_ok: int, n: int) -> None:
        cell = self._cells[(size, conc)]
        cell.update(wall_s=wall_s, n_ok=n_ok, n=n, phase="done")
        self._total += n
        self._ok += n_ok
        if self.plain:
            print(f"{size} tok x{conc}: {wall_s:.1f}s, {n_ok}/{n} ok", flush=True)

    def live(self):
        if self.plain:
            return nullcontext()
        from rich.console import Console
        from rich.live import Live
        return Live(console=Console(), auto_refresh=True, screen=False, get_renderable=self._render)

    def _render(self):
        from rich.console import Group
        from rich.table import Table
        table = Table(box=None)
        for col in ("ctx", "conc", "progress", "wall (s)", "status"):
            table.add_column(col)
        for c in (self._cells[k] for k in self._order):
            bar = "█" * c["done"] + "░" * (c["n"] - c["done"])
            status = "·" if c["phase"] == "pending" else "▶" if c["phase"] == "running" else "✓" if c["n_ok"] == c["n"] else f"✗ {c['n'] - c['n_ok']}/{c['n']}"
            table.add_row(f"{c['size'] // 1024}K", str(c["conc"]), f"{bar} {c['done']}/{c['n']}", "—" if c["wall_s"] is None else f"{c['wall_s']:.1f}", status)
        done = sum(c["phase"] == "done" for c in self._cells.values())
        header = "finished" if self._finished else (f"warming up {self._warmup[0]} tok ({self._warmup[1]}/{self._warmup[2]})" if self._warmup else f"measuring cell {done}/{len(self._cells)}")
        return Group(header, table)

    def finish(self) -> None:
        self._finished = True

    def finish_line(self, elapsed_s: float) -> str:
        return f"✓ finished in {int(elapsed_s // 60)}m {int(elapsed_s) % 60:02d}s — {self._ok}/{self._total} requests ok"
