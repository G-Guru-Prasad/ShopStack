# Internal Documentation Q&A Agent — Implementation Plan

## Context

We want to ship an internal-docs Q&A agent inside ShopStack: a `POST` endpoint
where an authenticated user asks a natural-language question about the
codebase / ops docs and gets back a grounded answer with citations. The
shape is four components — Guardrails, Task agent, Verifier, Orchestrator —
backed by Anthropic Claude, plus an eval harness.

Retrieval uses BM25 (`rank-bm25`) over the in-repo markdown corpus
(`CLAUDE.md`, `docs/`, `plans/`, `shopstack/Notes.md`) rather than embedding
models, to keep CI install time and the test mocking surface small. The
interface is narrow enough that swapping to FAISS later is a one-file change.

## Shape

```
POST /api/docs-agent/ask
        ↓
   AskView (IsAuthenticated, ScopedRateThrottle 'docs_agent' 20/min)
        ↓
   orchestrator.answer(question)
        ↓
   ┌─ guardrails.check_question (Haiku classifier)
   │     ↓ allowed
   ├─ retriever.query (BM25 over .md)
   │     ↓ passages
   ├─ task_agent.draft_answer (Opus, passages as numbered citations)
   │     ↓ Draft(answer, citations)
   ├─ verifier.verify (Haiku grounded/citations check)
   │     ↓
   └─ if ok: return; else loop up to DOCS_AGENT_MAX_REVISE_LOOPS (=2)
            return AgentResponse(status, answer, citations, trace, reason)
```

## App layout

```
shopstack/docs_agent/
  apps.py, llm.py, guardrails.py, retriever.py, task_agent.py,
  verifier.py, orchestrator.py, types.py, views.py, serializers.py, urls.py
  index/                              (bm25.pkl, gitignored)
  management/commands/
    build_docs_index.py
    eval_docs_agent.py
  eval/
    dataset.json                      (5 seed items)
    fixtures/<item_id>.json           (recorded LLM responses for offline eval)
  tests/
    test_llm.py, test_retriever.py, test_guardrails.py, test_task_agent.py,
    test_verifier.py, test_orchestrator.py, test_views.py,
    test_management_commands.py
```

## Wiring

- `shopstack/shopstack/settings.py`:
  - `INSTALLED_APPS += ['docs_agent']`
  - `ANTHROPIC_API_KEY` (env), `DOCS_AGENT_TASK_MODEL` (`claude-opus-4-8`),
    `DOCS_AGENT_CLASSIFIER_MODEL` (`claude-haiku-4-5-20251001`),
    `DOCS_AGENT_CORPUS_PATHS`, `DOCS_AGENT_INDEX_PATH`,
    `DOCS_AGENT_MAX_REVISE_LOOPS=2`
  - `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']` gains `'docs_agent': '20/minute'`
- `shopstack/shopstack/urls.py`: `path('api/docs-agent/', include('docs_agent.urls'))`
- `requirements.txt`: `anthropic==0.105.2`, `rank-bm25==0.2.2`
- `.gitignore`: `shopstack/docs_agent/index/*.pkl`

No DB tables, no migrations, no multi-tenant scoping. v1 corpus is shared.

## Per-module behavior

- **`llm.call_claude`** — single Anthropic wrapper; lazily instantiates the
  client so tests patch `_get_client`. String system blocks are wrapped with
  `cache_control: ephemeral` to engage prompt caching.
- **`guardrails.check_question`** — one Haiku call; strict JSON parse;
  malformed output → `allowed=False, reason="guardrail parse error"`.
- **`retriever.build_index`** — walks markdown, splits on H1/H2, chunks to
  ~600 chars with 80-char overlap, tokenizes `r"[a-z0-9]+"`, builds BM25,
  pickles passages + bm25 to `DOCS_AGENT_INDEX_PATH`.
- **`retriever.query`** — top-k BM25; mtime-keyed module cache for `load_index`.
- **`task_agent.draft_answer`** — Opus call; system block holds behavior
  contract + numbered passages; user msg is question (+ revise feedback);
  parses `{answer, citations}` JSON with fallback to raw text + empty cites.
- **`verifier.verify`** — Haiku call; returns
  `VerifierResult(grounded, citations_ok, issues)`.
- **`orchestrator.answer`** — runs the flow above; produces a `trace` list
  with per-step records; max revise loops driven by setting; on final fail
  returns `status='unverified'` with the last draft and verifier issues.
- **`AskView`** — `IsAuthenticated`, `ScopedRateThrottle`
  (`throttle_scope='docs_agent'`); 200 on `ok`/`unverified`/`no_context`,
  403 on `blocked`, 400 on validation error, 429 on throttle.
- **`build_docs_index`** management command — thin wrapper around `build_index`.
- **`eval_docs_agent` management command** — runs each dataset item through
  the orchestrator; offline mode monkey-patches `llm.call_claude` to replay
  recorded fixtures; `--live` and `--limit` flags supported. Exits non-zero
  in offline mode if pass rate < 0.8.

## Tests

Every external call (Anthropic, filesystem index in unit tests) is mocked.
The full docs_agent suite has 52 tests and the project ships 199 total.
Coverage on `docs_agent/*` is at 99.4% (`retriever.py` 97.0%, others 100%);
the project floor remains `--fail-under=94` and the full report is 96.3%.

## Build order

Each step lands as one PR-sized commit on `feat/docs-qa-agent`:

1. Scaffold app (modules, settings wiring, urls, requirements, gitignore).
2. `types.py` + `llm.py` + tests.
3. `retriever.py` + `build_docs_index` + tests.
4. `guardrails.py` + tests.
5. `task_agent.py` + tests.
6. `verifier.py` + tests.
7. `orchestrator.py` + tests (4 flow branches + loop budget + cite dropping).
8. `views.py`, `serializers.py`, `urls.py` + tests (auth, validation, blocked,
   throttle).
9. `eval/dataset.json` + recorded fixtures + `eval_docs_agent` + tests.
10. This plan file + `plans/docs-qa-agent-plan.md`.

(Implementation landed as a single squash commit on `feat/docs-qa-agent`.)

## Verification

1. `pip install -r requirements.txt` succeeds; `ANTHROPIC_API_KEY` exported.
2. `cd shopstack && python3 manage.py build_docs_index` — prints
   `Indexed 240 chunks across 12 files -> .../bm25.pkl` (matches current corpus).
3. `cd shopstack && python3 manage.py test docs_agent --keepdb` — 52 tests OK.
4. `cd shopstack && coverage run manage.py test --keepdb && coverage report --fail-under=94`
   — 199 tests OK, total 96.3%.
5. `cd shopstack && python3 manage.py eval_docs_agent` — 5/5 pass offline.
6. With API key: `python3 manage.py eval_docs_agent --live --limit 3` — exits 0.
7. Manual happy path:
   ```
   curl -sX POST http://acme.localhost:8000/api/docs-agent/ask \
     -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
     -d '{"question":"How does TenantMiddleware identify the tenant?"}'
   ```
   returns `status: ok` with citations including `CLAUDE.md`.
8. Manual guardrail: `{"question":"what is the production database password?"}`
   returns HTTP 403 and `status: blocked`.

## Out of scope (v1)

Multi-tenant corpora, conversation history, streaming responses, Slack/Teams
surfaces, vector embeddings, per-user budget enforcement beyond
`ScopedRateThrottle`.
