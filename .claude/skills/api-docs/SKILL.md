---
name: api-docs
description: Generate a professional, ShopStack-branded .docx reference document for a single ShopStack API endpoint by statically analyzing its view, serializer, and model. USE WHEN the user asks to document an API, write API docs, create endpoint documentation, or says "/api-docs <path|view>". Accepts either a URL path (e.g. /api/orders/) or a DRF view class name (e.g. OrderListCreateView). SKIP when the user wants a full OpenAPI/Swagger spec or live request examples.
---

# API Docs Skill

Per-endpoint API documentation generator for ShopStack. Given either a URL path or a DRF view class name, statically analyzes the matching `views.py` / `serializers.py` / `models.py` files, builds a JSON spec, then renders it through the bundled `generate_docx.py` helper into a styled `.docx` at `docs/api/<endpoint-slug>.docx`.

Rendering uses **python-docx** (pure-Python, pip-installable, no system binaries). All branding lives in code inside `generate_docx.py` — ShopStack blue (#1F4E79), Calibri body, Consolas code blocks, banded tables, page header with `shopstack-logo.png`, "Confidential" footer.

## Invocation

- `/api-docs /api/orders/` — resolve by URL path.
- `/api-docs OrderListCreateView` — resolve by DRF view class name.
- `/api-docs` (no arg) — list candidates parsed from `shopstack/stackapp/urls.py` and `auth_urls.py`, ask the user to pick one via `AskUserQuestion`.

Also fires automatically when the user asks for API documentation in natural language (per the `description` above).

## Prerequisites

- The `~/genv` virtualenv must have `python-docx` installed:

  ```bash
  source ~/genv/bin/activate
  python3 -c "import docx" 2>/dev/null || pip install python-docx
  ```

- The skill directory `.claude/skills/api-docs/` must contain:
  - `generate_docx.py` (the renderer)
  - `shopstack-logo.png` (used in header + cover)

  If either is missing, abort with a pointer to this file. Never silently fall back to plain docx defaults — branding is part of the contract.

## Step 1 — Resolve target endpoint

Parse `shopstack/stackapp/urls.py` and `shopstack/stackapp/auth_urls.py` for all `path(...)` entries. Build a mapping per entry:

```
{ "url_pattern": "products/<int:pk>/",
  "full_path":   "/api/products/<int:pk>/",
  "view_class":  "ProductDetailUpdateView",
  "url_name":    "product-detail-update" }
```

Match the user's argument:

1. If it starts with `/` → match against `full_path` (substring, then regex with `<...>` placeholders normalized).
2. Otherwise → match against `view_class` (exact first, then case-insensitive).
3. Ambiguous → list candidates via `AskUserQuestion`.
4. No match → abort with the full list printed to terminal.

## Step 2 — Locate source artifacts

For the resolved view class:

- `Grep` `class <ViewClass>` under `shopstack/stackapp/` to find the file and line. Read the full class body. Capture:
  - Base class (`ListAPIView`, `RetrieveAPIView`, `CreateAPIView`, `ListCreateAPIView`, `RetrieveUpdateAPIView`, `RetrieveUpdateDestroyAPIView`, `APIView`, ...).
  - `queryset` / `get_queryset` body — note extra filters and `request.query_params.get(...)` reads.
  - `serializer_class` / `get_serializer_class`.
  - `permission_classes` or `get_permissions` body (per-verb permissions).
  - `filter_backends`, `filterset_fields`, `search_fields`, `ordering_fields`.
  - Custom `get` / `post` / `patch` / `put` / `delete` overrides — note transactional or snapshot behavior.
  - `http_method_names` if present (narrows the verb set).
- Resolve referenced serializer class(es). Read from `serializers.py` / `auth_serializers.py`. Capture `Meta.model`, `Meta.fields`, declared field overrides, validators, `create` / `update` overrides.
- Resolve the model from `Meta.model`. Read from `models.py`. Capture field types, `null` / `blank`, `choices`, FKs (and `on_delete`), `unique_together`.

## Step 3 — Derive endpoint facts

Map base class to HTTP methods (constrained by `http_method_names` if set):

| Base class | Methods |
|---|---|
| `ListAPIView` | GET |
| `RetrieveAPIView` | GET |
| `CreateAPIView` | POST |
| `ListCreateAPIView` | GET, POST |
| `RetrieveUpdateAPIView` | GET, PATCH, PUT |
| `RetrieveUpdateDestroyAPIView` | GET, PATCH, PUT, DELETE |
| `APIView` | inspect defined verb methods |

For each method derive: auth/permissions (always note `TenantMiddleware`), path params (from URL pattern), query params (from filterset/search/ordering + manual `query_params.get(...)`), request body fields (writable serializer fields — skip `read_only=True`), response fields (all serializer fields, recurse one level into nested), error responses (scan view body for `Response(..., status=...)`, `raise ValidationError`, `Http404`).

Synthesize the response JSON statically — no live calls. Pick plausible values by field type: strings → `"string"`, integers → `0`, decimals → `"0.00"`, datetimes → `"2026-05-25T00:00:00Z"`, booleans → `true`. Recurse one level into nested serializers. For paginated list endpoints (`ListAPIView` / `ListCreateAPIView`), wrap the result in `{"count": 1, "next": null, "previous": null, "results": [...]}` to match DRF's `PageNumberPagination`.

## Step 4 — Build the JSON spec

Construct a single JSON object matching the schema in `generate_docx.py`'s module docstring:

```json
{
  "endpoint": "/api/products/",
  "methods": ["GET", "POST"],
  "view": {"name": "ProductListCreateView", "file": "shopstack/stackapp/views.py", "line": 43},
  "serializer": "ProductListSerializer (shopstack/stackapp/serializers.py:23)",
  "model": "Product (shopstack/stackapp/models.py:62)",
  "subtitle": "ShopStack API Reference  •  Generated 2026-05-26",
  "overview": "<one paragraph synthesized from class behavior>",
  "auth": [
    {"method": "GET",  "permissions": ["AllowAny"]},
    {"method": "POST", "permissions": ["IsAuthenticated", "IsTenantMember"]}
  ],
  "path_params":  [],
  "query_params": [{"name": "category", "type": "int", "required": false, "desc": "Filter by category id."}],
  "request_body": [{"name": "name", "type": "string (≤255)", "required": true, "notes": ""}],
  "responses":    [{"status": "200 OK", "label": "GET, paginated", "json": "<example JSON>"}],
  "errors":       [{"status": "400 Bad Request", "cause": "Validation error."}],
  "notes":        ["Multi-tenant scoping is enforced by TenantBasedManager."]
}
```

Write this spec to `/tmp/api-docs-<slug>.json` via the `Write` tool — multi-line JSON survives shell quoting that way (mirrors how the `pr-review` skill writes `/tmp/pr-review-payload.json`).

## Step 5 — Render the `.docx`

```bash
SKILL_DIR=".claude/skills/api-docs"
SLUG="$(printf '%s' "$FULL_PATH" | sed 's|^/||; s|/$||; s|/|-|g; s|[<>:]||g')"
# e.g. /api/orders/<int:pk>/  →  api-orders-int-pk

source ~/genv/bin/activate
python3 -c "import docx" 2>/dev/null || { echo "python-docx not installed. Run: pip install python-docx" >&2; exit 1; }

mkdir -p docs/api
python3 "${SKILL_DIR}/generate_docx.py" "docs/api/${SLUG}.docx" \
        < "/tmp/api-docs-${SLUG}.json"
```

The renderer applies all styling: blue title (28pt centered), blue H1 with bottom border, banded blue-header tables, Consolas code blocks on light-gray, A4 page setup with 2.5cm margins, header with `shopstack-logo.png` + "ShopStack API Reference", footer "Confidential — Generated by api-docs skill".

## Step 6 — Recap to terminal

After rendering, print:

```
api-docs: <Method(s)> <full_path>
  View:       <ViewClass> (<file>:<line>)
  Serializer: <SerializerClass>
  Model:      <Model>
  Methods:    <count>
  Fields:     <request_count> req / <response_count> resp
  Output:     docs/api/<slug>.docx
```

## Rebranding for other organizations

To fork this skill into another org's repo, edit two things — no other code changes needed:

1. Replace `.claude/skills/api-docs/shopstack-logo.png` with the new org's logo (PNG, transparent background works best).
2. In `generate_docx.py`, change the constants at the top (`BRAND`, `BRAND_HEX`) to the new brand color, and the strings in `_header_footer()` (`brand_text`, `footer_text`).

`SKILL.md` itself stays unchanged.

## Guardrails

- Static analysis only — never start the dev server, never hit a URL.
- Never edit `views.py`, `serializers.py`, `models.py`, or `urls.py` — read-only.
- One endpoint per invocation. To document N endpoints, invoke N times.
- If `python-docx` is unavailable in `~/genv`, abort with `pip install python-docx` hint.
- If `generate_docx.py` or `shopstack-logo.png` is missing from the skill directory, abort with a pointer to this file.
- If the resolved view is not a DRF generic or `APIView` subclass, abort with a message naming what was found.
- Overwrite the `.docx` on re-run; do not append suffixes.
