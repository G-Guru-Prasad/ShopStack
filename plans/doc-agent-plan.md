# Plan: `doc_agent` — Developer Documentation Q&A Agent

## Context

The team wants a small, developer-facing AI assistant integrated into ShopStack
that answers internal documentation questions (runbooks, onboarding, deployment,
architecture). The use case is laid out in `ai-agent-use-case.md` at the repo
root: a four-component system (Guardrails → TaskAgent → Orchestrator → Verifier)
that retrieves grounded answers from internal docs and refuses unsafe requests.

The agent is **not** customer-facing and **not** tenant-scoped. It is an internal
productivity tool for ShopStack engineers. The corpus lives as plain Markdown
files in a fixed folder inside the repo, so the docs ship with the code and can
be reviewed/version-controlled like everything else.

The outcome: a `doc_agent` Django app exposing a REST API and a minimal Django
template chat UI, backed by pgvector for retrieval and Anthropic Claude for
all reasoning steps (guardrails, drafting, verification).

## Architecture overview

- New Django app: `shopstack/doc_agent/`, registered in `INSTALLED_APPS`.
- Corpus: `shopstack/doc_agent/corpus/` (curated `.md` / `.txt` / `.docx` files, hand-written).
- Retrieval: pgvector extension on the existing `shopstack_db` Postgres database.
- LLM: Anthropic Claude (via `anthropic` SDK), wrapped in `doc_agent/llm.py`
  so every call site is mockable in tests.
- Embeddings: Voyage `voyage-3` (1024 dims), wrapped in `doc_agent/embeddings.py`.
- Synchronous request pipeline — no Celery, no Redis. Each query is ~3 LLM
  calls and a vector lookup; that comfortably fits in an HTTP request.
- Shared corpus, per-user conversation history. No `TenantBaseModel` inheritance.

## Module layout

```
shopstack/doc_agent/
  __init__.py
  apps.py
  models.py                       # Document, DocumentChunk, Conversation, Message
  migrations/                     # incl. VectorExtension migration
  llm.py                          # AnthropicClient wrapper (single import site)
  embeddings.py                   # embed_texts(batch) -> list[list[float]]
  chunker.py                      # split_document(text, path) -> list[Chunk]
  retriever.py                    # top_k(query_vec, k=6) -> list[DocumentChunk]
  guardrails.py                   # Guardrails.check(question, history)
  task_agent.py                   # TaskAgent.draft(question, chunks, history, feedback)
  verifier.py                     # Verifier.check(draft, used_chunks)
  orchestrator.py                 # Orchestrator.run(user, question, conv_id)
  views.py                        # AskAPIView, ConversationListView, ConversationDetailView, ChatPageView
  serializers.py
  urls.py
  templates/doc_agent/chat.html
  corpus/                         # curated knowledge base
    runbooks/
    onboarding/
    architecture/
  management/commands/ingest_docs.py
  tests/
    __init__.py
    factories.py
    test_chunker.py
    test_ingest_docs.py
    test_guardrails.py
    test_retriever.py
    test_task_agent.py
    test_verifier.py
    test_orchestrator.py
    test_views.py
```

Project URLconf wires:
- `/api/agent/...`  → `doc_agent.urls` (DRF endpoints)
- `/agent/`         → `ChatPageView` (template UI)

## Data model (`doc_agent/models.py`)

None of these inherit from `TenantBaseModel`. Shared corpus, per-user history.

**`Document`**
- `source_path` (CharField, unique) — path **relative to the corpus root**,
  e.g. `runbooks/deploy-staging.md`. Portable, makes citation strings clean.
- `kind` (CharField, choices: `runbook`, `onboarding`, `architecture`, `other`).
- `content_hash` (CharField, length 64) — SHA256 of file contents; lets the
  ingest command skip unchanged files.
- `indexed_at` (DateTimeField, `auto_now=True`).

**`DocumentChunk`**
- `document` (FK → `Document`, `on_delete=CASCADE`).
- `chunk_index` (PositiveIntegerField).
- `text` (TextField) — raw chunk content.
- `embedding` (`pgvector.django.VectorField(dimensions=1024)`).
- `start_line`, `end_line` (PositiveIntegerField, nullable) — for citation
  links back to source.
- `Meta.unique_together = ("document", "chunk_index")`.
- `Meta.indexes`: `HnswIndex` on `embedding` with `vector_cosine_ops`.

**`Conversation`**
- `user` (FK → `auth.User`, `on_delete=CASCADE`).
- `title` (CharField, derived from first user message, truncated to 80 chars).
- `created_at`, `updated_at`.

**`Message`**
- `conversation` (FK → `Conversation`, `on_delete=CASCADE`).
- `role` (CharField, choices: `user`, `assistant`, `system`).
- `content` (TextField).
- `cited_chunks` (M2M → `DocumentChunk`, blank=True) — populated only for
  `assistant` messages.
- `guardrails_verdict` (JSONField, nullable) — stored for audit/debugging.
- `verifier_verdict` (JSONField, nullable).
- `not_fully_verified` (BooleanField, default False) — set when the verifier
  fails after `MAX_REVISIONS` attempts.
- `created_at`.

**Migrations:** the first migration runs `pgvector.django.VectorExtension`
(`CREATE EXTENSION IF NOT EXISTS vector;`) before creating model tables.

## Request lifecycle (Orchestrator)

`POST /api/agent/ask/`  with `{"question": "...", "conversation_id": <optional>}`
runs this pipeline synchronously inside the request:

```
1. Orchestrator: load-or-create Conversation for request.user; persist user Message.
2. Guardrails (Claude call):
     in  -> {question, recent_history}
     out -> {allowed, reason, intent, topic}
   If allowed=False: persist assistant Message with safe refusal text and return.
3. Retriever:
     embed(question) -> top_k=6 chunks via pgvector cosine distance.
   If zero chunks above similarity threshold: return "I don't have docs on that."
4. TaskAgent (Claude call):
     in  -> {question, retrieved_chunks, recent_history, verifier_feedback?}
     out -> {draft_answer, used_chunk_ids}
5. Verifier (Claude call):
     in  -> {draft_answer, used_chunks}
     out -> {grounded, issues, revised_answer}
   - grounded=True            -> final_answer = draft_answer.
   - grounded=False + revised -> final_answer = revised_answer.
   - grounded=False + no rev  -> loop back to step 4 with verifier feedback.
   - Hard cap: MAX_REVISIONS=2. After cap, return latest draft with
     not_fully_verified=True.
6. Orchestrator: persist assistant Message with cited_chunks M2M and both
   verdict JSON blobs.
7. Return {message_id, answer, citations: [{source_path, start_line, end_line, snippet}]}.
```

**Bounded knobs (defined in `doc_agent/orchestrator.py`):**
- `MAX_REVISIONS = 2`
- `HISTORY_WINDOW = 4`  (last N messages passed to Guardrails / TaskAgent)
- `RETRIEVAL_TOP_K = 6`
- `SIMILARITY_FLOOR = 0.25`  (cosine distance threshold for "no docs" short-circuit)

The orchestrator is a single `run(...)` function — sequential calls with a
small revision loop. No state machine framework.

## Component contracts

Each agent class has one public method and a strict input/output dict shape
so they are trivially mockable.

**`Guardrails.check(question: str, history: list[dict]) -> dict`**
- System prompt enforces JSON output: `{allowed, reason, intent, topic}`.
- Refusal categories: secrets / credentials, prod DB access, destructive ops,
  off-topic / personal queries.

**`TaskAgent.draft(question, chunks, history, verifier_feedback=None) -> dict`**
- Prompt instructs Claude to cite chunk IDs inline (`[chunk:42]`) and to say
  "I don't have docs on that" when chunks don't cover the question.
- Output: `{draft_answer, used_chunk_ids}`.

**`Verifier.check(draft_answer, used_chunks) -> dict`**
- Prompt: every factual claim must be supported by provided chunks; list
  unsupported claims.
- Output: `{grounded, issues, revised_answer}`.

**`Orchestrator.run(user, question, conversation_id) -> AssistantResponse`**
- Wires the four above, persists DB rows, enforces revision cap.

All Claude calls go through `doc_agent/llm.py` (single Anthropic SDK import
site). Tests stub this one module.

## Ingestion command

`python manage.py ingest_docs [--force]`

- Walks `shopstack/doc_agent/corpus/` recursively for `*.md`, `*.txt`, and
  `*.docx`.
- Per file: SHA256 → compare with `Document.content_hash` → skip if unchanged
  (unless `--force`).
- For `.docx` files: extract plain text via `python-docx` (`docx.Document(path)`,
  iterate paragraphs) before chunking. Treat the extracted text as Markdown-less
  plain text — the chunker falls back to its windowed mode for these.
- Chunker (`doc_agent/chunker.py`): split on Markdown headings first; long
  sections (and all non-Markdown sources) fall back to ~800-token windows with
  100-token overlap.
- Calls `embeddings.embed_texts(batch)` batched 32 at a time.
- Replaces all `DocumentChunk` rows for a changed document inside
  `transaction.atomic()`.
- Deletes `Document` rows whose `source_path` no longer exists on disk.
- Prints a summary: added / updated / unchanged / removed.

## API & UI

**REST API (DRF, requires `request.user.is_authenticated`):**
- `POST /api/agent/ask/`                          → run orchestrator.
- `GET  /api/agent/conversations/`                → list current user's conversations.
- `GET  /api/agent/conversations/<id>/`           → full message history with citations.

These views do **not** use `ThreadVariables` or tenant routing — shared corpus,
no tenant scoping.

**Template UI:** `GET /agent/` renders `chat.html`:
- Left pane: list of the user's past conversations.
- Right pane: message thread for the active conversation.
- Bottom: input box; submits via plain `fetch()` POST to the API (no JS framework).
- Each assistant message shows citation chips that link to the rendered
  Markdown of `corpus/<source_path>`.

## Tests (`doc_agent/tests/`)

Every component gets a test module. All tests use a stub `AnthropicClient`
injected at module level so CI never makes real API calls.

- `test_chunker.py` — Markdown heading splits; long sections fall back to
  windowed chunks with overlap; chunk metadata (start/end line) correct.
- `test_ingest_docs.py` — fresh ingest creates rows; unchanged file skipped;
  modified file re-chunks; deleted file purged; `--force` re-ingests
  everything. Uses `override_settings(DOC_AGENT_CORPUS_DIR=tmp_dir)`.
- `test_guardrails.py` — stub returns `allowed=False` for a secrets question
  → orchestrator returns refusal without retrieval; `allowed=True` passes
  through. Asserts `guardrails_verdict` is persisted.
- `test_retriever.py` — seeded chunks with known embeddings; `top_k` returns
  expected order; empty result triggers "I don't have docs on that" path.
- `test_task_agent.py` — given stub chunks, draft contains `[chunk:N]`
  markers; `used_chunk_ids` matches markers.
- `test_verifier.py` — stub returns `grounded=False` once then `True`
  → orchestrator does exactly one revision loop; `grounded=False` for 3
  attempts → returns latest draft with `not_fully_verified=True`; verdict
  persisted.
- `test_orchestrator.py` — full happy-path integration with all four stubs;
  asserts `Message` rows, M2M `cited_chunks`, both JSON verdict fields are
  populated.
- `test_views.py` — DRF `APIClient`: unauthenticated → 401; authenticated
  POST to `/api/agent/ask/` → 200 with citations payload; GET conversations
  list scoped to current user.
- `factories.py` — Factory Boy factories for `User`, `Document`,
  `DocumentChunk`, `Conversation`, `Message`, consistent with PR #5.

All tests run under `coverage.py`. The existing CI gate (`--fail-under=94`)
must continue to pass; `.coveragerc` already excludes migrations and
`test*.py` so the new app contributes only product code to the denominator.

## Settings additions (`shopstack/shopstack/settings.py`)

- Add `"pgvector"` and `"doc_agent"` to `INSTALLED_APPS`.
- Add `DOC_AGENT_CORPUS_DIR = BASE_DIR / "doc_agent" / "corpus"`.
- Add `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` read from environment with
  empty-string defaults so tests run without keys.
- Add `DOC_AGENT_EMBEDDING_MODEL = "voyage-3"` and
  `DOC_AGENT_CHAT_MODEL = "claude-sonnet-4-6"`.

## Dependencies

Add to `requirements.txt`:
- `anthropic`
- `voyageai`
- `pgvector`  (Django integration)
- `python-docx`  (extract text from `.docx` corpus files)

## Reusable existing utilities

- The CI coverage gate in `.github/workflows/ci.yml` and `.coveragerc` already
  cover this app once it's added under `shopstack/` — no workflow changes
  needed.
- `tests/factories.py` follows the Factory Boy pattern established in PR #5.
- DRF view + serializer style mirrors `stackapp/views.py` for consistency.

## Plan-file mirroring

Per `CLAUDE.md` Plan Mode rules, this plan must also be written into the repo
at `plans/doc-agent-plan.md` before execution begins. (The current file lives
in `~/.claude/plans/` because it's the harness plan file; the in-repo copy is
required by the project convention.)

## Verification

End-to-end manual verification after implementation:

1. `source ~/genv/bin/activate && cd shopstack`
2. `python3 manage.py migrate` — confirms pgvector extension migration runs.
3. Seed a few `.md` files under `shopstack/doc_agent/corpus/runbooks/`.
4. `python3 manage.py ingest_docs` — confirm summary shows N added.
5. Re-run `ingest_docs`: confirm all files reported as unchanged.
6. Modify one file, re-run: confirm exactly that file reported as updated.
7. Start the server: `python3 manage.py runserver`.
8. Log in as a user, visit `/agent/`, ask "How do I deploy to staging?"
   → confirm answer with citation chips, both verdicts visible in the
   resulting `Message` row in Django admin.
9. Ask a refusal-class question ("what's the prod DB password?")
   → confirm safe refusal, no retrieval call made, `guardrails_verdict`
   persisted with `allowed=False`.

Automated verification:
- `python3 manage.py test doc_agent --keepdb` — all new test modules pass.
- `coverage run --rcfile=.coveragerc manage.py test && coverage report
  --fail-under=94` — global gate still passes.
