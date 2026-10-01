# agentic-benchmark

LLM latency/throughput benchmark for OpenAI-compatible endpoints (e.g. vLLM).
Runs a context-size × concurrency matrix of streaming chat completions and
measures per request: TTFT, prefill throughput (PP), decode throughput (TG).
Each run writes a per-request JSONL, a per-cell CSV, and a Markdown report.

## Quick start

```bash
cp .env.example .env   # set HYPERQWEN_API_KEY (the key lives in .env, not config.yaml)
./run.sh               # creates .venv if missing, syncs deps, runs the full matrix from config.yaml
./run.sh --smoke       # one short request (256-token prompt, 32 output tokens); prints a summary, writes nothing
```

`run.sh` forwards extra arguments to the CLI, so `./run.sh --config other.yaml` works too.
Manual equivalent, without run.sh (from the repo root):

```bash
PYTHONPATH=src .venv/bin/python -m bench.main --config config.yaml
# or: python src/bench/main.py --config config.yaml
```

Flags: `--smoke` (single request) and `--config <path>` (default `config.yaml`).

The full run shows a live progress table (one line per warmup and per cell when stdout is piped/non-TTY) and ends with a `✓ finished in Mm SSs` line plus the report path.

## Configuration

All in `config.yaml` (the API key is not here):

| key | default | meaning |
|---|---|---|
| `model.id` | `qwen3.8-27b` | model id sent in each request |
| `model.provider` | `HyperQwen` | descriptive label only — not read by the code |
| `model.endpoint` | `http://192.168.1.110:18020/v1/` | base URL of the OpenAI-compatible server |
| `model.options.chat_template_kwargs.enable_thinking` | `false` | thinking on/off; the server only honors this inside `chat_template_kwargs` (top-level is ignored) |
| `benchmark.context_sizes` | `[1024, 4096, 8192, 16384, 32768]` | target prompt token counts |
| `benchmark.concurrency_levels` | `[1, 2, 4, 8]` | max in-flight requests per cell |
| `benchmark.requests_per_cell` | `8` | measured requests per (context, concurrency) cell |
| `benchmark.warmup_per_context` | `1` | warmup request before each context size's cells (the runner currently issues exactly one) |
| `benchmark.max_tokens` | `256` | fixed output length for all requests |
| `benchmark.timeout_seconds` | `300` | per-request HTTP timeout |
| `benchmark.retries` | `1` | extra attempts after a transient error (HTTP ≥500, transport failure) |
| `report.output_dir` | `results` | directory for run artifacts |
| `report.formats` | `[jsonl, csv, md]` | artifact formats (all three are always written) |

## How it works

- Prompts are deterministic filler text sized to the target with a chars/token heuristic (`CHARS_PER_TOKEN = 4.4` in `src/bench/prompts.py`); no tokenizer — sizing is calibrated against the server-reported `usage.prompt_tokens`.
- Each request is a streaming `POST /chat/completions` with `stream_options: {include_usage: true}`; the final SSE chunk carries the server's `prompt_tokens`/`completion_tokens`.
- One warmup per context size (concurrency 1) is sent before that size's cells to prime the server.
- Each cell runs `requests_per_cell` requests under an asyncio semaphore of its concurrency level, against a hard per-request deadline of `timeout_seconds × (retries + 1) + 30` seconds (630s with defaults); transient errors are retried, failures are recorded, not dropped.
- Metrics: TTFT = request start → first streamed token (ms); PP = `prompt_tokens / TTFT` (tok/s); TG = `completion_tokens / (t_last − t_first)` (tok/s); per-cell aggregate = total completed tokens / cell wall time. Usage counts come from the server: with thinking on, reasoning streams as `reasoning` deltas and is counted in TTFT/TG and in `completion_tokens`; thinking is off by default.

## Output

Each run writes `results/<timestamp>/` (`report.output_dir`; `results/` is gitignored):

- `requests.jsonl` — one line per request, including warmups: `ok`, `error`, token counts, `ttft_ms`/`gen_ms`/`wall_ms`, derived `pp_tps`/`tg_tps`.
- `summary.csv` — one row per cell: ok/err counts, TTFT mean/p50/p95/p99 (ms), mean PP/TG (tok/s), aggregate tok/s, cell wall time.
- `report.md` — human context × concurrency table, plus an error-count section when errors occur.

## License

MIT — see `LICENSE`.
