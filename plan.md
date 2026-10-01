# LLM latency/throughput benchmark — plan

## Goal
Benchmark an OpenAI-compatible endpoint (initially: HyperQwen `qwen3.8-27b`) across a matrix of
**context sizes** × **concurrency levels**, measuring per request:

- **TTFT** — time to first token (ms): from request sent to first streamed content chunk
- **PP** — prompt processing (prefill) throughput: `prompt_tokens / TTFT` (tokens/s)
- **TG** — token generation (decode) throughput: `completion_tokens / (t_last − t_first)` (tokens/s)

Aggregated per cell: mean / p50 / p95 / p99 TTFT, mean PP, mean TG, aggregate output tok/s, error rate.

## Target (from `~/.config/opencode/opencode.json`, provider `HyperQwen`)
- Model id: `qwen3.8-27b`
- Endpoint: `http://192.168.1.110:18020/v1/`
- API key: from `.env` (`HYPERQWEN_API_KEY`)
- Model limits: context 153600, input 32768, output 32768

## Method
- Streaming chat completions: `POST /chat/completions` with `stream: true` and
  `stream_options: { include_usage: true }` so the final SSE chunk carries token usage.
- **Thinking off** (`enable_thinking: false`, exposed as a config flag) so reasoning tokens
  don't inflate TTFT/TG. Re-enable via config if we want to benchmark with thinking.
- Deterministic filler prompts sized to a target token count (repeated text); verified against
  server-reported `usage.prompt_tokens`. Max context capped at model input limit (32768).
- Per cell: `warmup` requests (1) to prime the server, then `requests_per_cell` measured requests,
  with at most `concurrency` in flight (asyncio semaphore). Fixed `max_tokens` output for all cells.
- Per-request timeout, one retry on transient errors, failures recorded not dropped.

## Default matrix (all in `config.yaml`)
| dimension      | values                          |
| -------------- | ------------------------------- |
| context sizes  | 1K, 4K, 8K, 16K, 32K tokens     |
| concurrency    | 1, 2, 4, 8                      |
| output         | fixed `max_tokens` (default 256)|

## Files
| file             | purpose                                          |
| ---------------- | ------------------------------------------------ |
| `plan.md`        | this document                                    |
| `config.yaml`    | model id, endpoint, request options, matrix      |
| `.env`           | `HYPERQWEN_API_KEY` (secret, gitignored)         |
| `.env.example`   | placeholder key                                  |
| `.gitignore`     | `.env`, `results/`, `__pycache__/`               |
| `src/bench/`     | code (not written yet)                           |

## Implementation outline (after explicit go-ahead)
1. **Python 3 + asyncio + httpx** (SSE streaming), `pyyaml`, `python-dotenv` — minimal deps.
2. `client.py` — streaming request; timestamp each SSE chunk; capture usage from final chunk.
3. `prompts.py` — build deterministic filler prompt for a target token size.
4. `runner.py` — matrix loop: warmup per context size, semaphore-bounded concurrency, timeout/retry.
5. `report.py` — write `results/<timestamp>/requests.jsonl`, `summary.csv`, `report.md`
   (table: context × concurrency → TTFT / PP / TG).
6. `main.py` — load `.env` + `config.yaml`, run, print summary; `--smoke` flag for a single short request.
7. Verify: smoke test → full run → inspect report.

## Open questions
1. Thinking off by default? (currently yes, for clean PP/TG; flag in config to flip)
2. Python or Node/TS for the runner? (plan assumes Python)
3. Max context: 32K (model input limit) — test higher against the 153600 context limit?
4. Concurrency ceiling: 8 — single local server, higher levels risk saturating it.
