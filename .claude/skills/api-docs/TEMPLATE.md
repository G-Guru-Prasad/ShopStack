# Document Template — Format Reference

`generate_docx.py` produces a clean enterprise-style API specification document. The visual model is the typical "API reference" document — a small org logo, a title, then a sequence of `Heading 1` sections separated by tables and code blocks. No fancy cover page, no banded tables, no page header/footer.

## Layout (top to bottom)

1. **Logo strip** — org logo (`shopstack-logo.png`, ~9.5cm wide), centered above the title.
2. **Title** — uses Word's built-in `Title` style. The text comes from the `title` field of the JSON spec.
3. **Endpoint** — `Heading 1`, followed by the HTTP method + path in Consolas (e.g. `GET /api/products/`).
4. **Description** — `Heading 1`, then a paragraph of plain text describing what the endpoint does.
5. **Authentication & Permissions** — `Heading 1`, then a 2-column table (Requirement | Detail).
6. **Path Parameters** — `Heading 1`, then a 4-column table (Parameter | Type | Required | Description), or "None." in italics.
7. **Query Parameters** — `Heading 1`, then a 4- or 5-column table (the optional `Format` column appears only if any param defines one). Optional `Heading 2` sub-blocks describe non-trivial rules (e.g. "Date Range Rules").
8. **Request Body** — `Heading 1`, then either a paragraph (e.g. "None.") or a 4-column field table.
9. **Response — `<variant>`** — `Heading 1` per response variant (e.g. one for a list, one for a detail, or one for foreclosure vs. cancellation). Each variant block contains:
   - status line ("HTTP 200 OK"),
   - a JSON example as a Consolas, light-gray-shaded code block,
   - a `Heading 2` "`<Variant>` Response Fields" table (Field | Description),
   - optional trailing note paragraphs.
10. **Error Responses** — `Heading 1`, then a 2-column table (HTTP | Condition).

## Styling

- **Page**: US Letter (8.5 × 11 in), 1-inch margins on every side.
- **Body font**: Calibri 11pt (Word's `Normal` default).
- **Title / headings**: Word's built-in `Title`, `Heading 1`, `Heading 2` styles — no custom colored headings.
- **Tables**: `Table Grid` base style; header row uses `#F3F3F3` shading with **bold** black text; body rows have no banding; thin gray (`#BFBFBF`) borders on every cell.
- **Code / JSON blocks**: Consolas 10pt with `#F3F3F3` paragraph shading. Zero space-before/space-after so consecutive lines hug.
- **No** page header, footer, page numbers, TOC, or cover image. Keep the document focused on content.

## Rebranding for another organization

1. Replace `.claude/skills/api-docs/shopstack-logo.png` with the new org's logo (rendered centered at ~9.5cm wide; adjust the `Cm(9.5)` call in `_logo_strip` if the new logo's aspect ratio needs different sizing).
2. Optionally adjust the `HEADER_FILL` / `BORDER_GRAY` constants at the top of `generate_docx.py` if the new org's spec template uses different neutral tones.

No edits to `SKILL.md` are required.

## Reference exemplar

The design mirrors `GET Prepayment API (Broker).docx` from the loans org — a clean, share-ready enterprise API spec. Each section in that doc maps 1:1 onto a renderer in `generate_docx.py`:

| Reference section | Renderer |
|---|---|
| Title | `Document.add_paragraph(..., style='Title')` |
| Endpoint | `_h1` + `_para(..., mono=True)` |
| Description | `_h1` + `_para` |
| Authentication & Permissions | `_render_auth` |
| Path Parameters | `_render_path_params` |
| Query Parameters + Date Range Rules sub-section | `_render_query_params` (subsections via `query_param_subsections`) |
| Request Body | `_render_request_body` |
| Response — Foreclosure / Response — Cancellation | `_render_responses` (one entry per variant) |
| Error Responses | `_render_errors` |
