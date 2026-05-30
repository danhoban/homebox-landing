# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
# Install dependencies
pip install -r requirements.txt

# Run (must be executed from the project root)
python -m app.main

# Also works directly
python app/main.py
```

The server reads `.env` from the project root.

## Architecture

This is a stdlib-only Python HTTP server (`http.server.ThreadingHTTPServer`) — no Flask, no Jinja2, no WSGI. It sits behind nginx, which handles TLS and routes external QR code scans (originally `/a/{asset_id}`) to `/landing?ref=/a/{asset_id}`. Internal network traffic bypasses this server entirely and goes straight to Homebox.

**Request flow:**
1. `main.py` receives `GET /landing?ref=/a/{asset_id}`
2. `homebox.py` calls `GET /api/v1/assets/{asset_id}` to resolve asset → UUID, then `GET /api/v1/items/{uuid}` for full detail
3. Item tags are matched against `TEMPLATE_N_TAG` config to select a template
4. `notifier.py` fires the matched template's Apprise URLs in a background thread
5. `renderer.py` builds a context dict and renders via `string.Template` (not Jinja2)
6. HTML response is returned with security headers

**Template rendering:** `base.html` provides the outer shell with inlined CSS and the ROT13 JS decoder. Child templates (`plant.html`, `item.html`, `fallback.html`, `not_found.html`) provide `${body_content}`. All substitution uses `string.Template.safe_substitute()`. Conditional sections (hero image, fields, care notes) are pre-computed as HTML strings in `renderer.py` before template substitution, since `string.Template` has no conditionals.

**Contact obfuscation (3 layers):** href ROT13-encoded in `data-contact` attribute → decoded client-side on DOMContentLoaded; display text split across `<span>` elements with a hidden decoy span; entire contact section hidden behind a click-to-reveal button. All three layers are applied in `renderer.py:render_contact_link()`.

**Photo proxying:** `GET /landing/photo/{item_uuid}/{attachment_id}` fetches image bytes from Homebox internally and streams them back. Bytes are cached in a module-level dict in `homebox.py` for the process lifetime.

## Configuration

All config lives in `.env` (loaded via `python-dotenv`). See `.env.example` for the full schema. Key structure:

- `HOMEBOX_*` — connection credentials
- `TEMPLATE_DEFAULT` / `TEMPLATE_N_TAG` / `TEMPLATE_N_FILE` / `TEMPLATE_N_NOTIFY` / `TEMPLATE_N_NOTIFY_TITLE` / `TEMPLATE_N_NOTIFY_BODY` — tag→template mapping with per-template Apprise notification config; templates are matched in order 1…N, first match wins
- `CONTACT_N_TYPE` / `CONTACT_N_LABEL` / `CONTACT_N_VALUE` — public contact details
- `SERVER_HOST` / `SERVER_PORT` / `LOG_LEVEL`

Notification title/body support three substitution tokens: `{name}` (item name), `{ip}` (client IP, resolved from `X-Forwarded-For` / `X-Real-IP` proxy headers with fallback to the raw socket address), and `{description}` (item description from Homebox).

## Key constraints

- No new dependencies without good reason — the stdlib + `apprise`, `markdown`, `python-dotenv`, `requests` are intentional and sufficient
- All Homebox API data rendered into HTML must go through `html.escape()` before insertion
- Field values detected as URLs must pass `_is_safe_url()` (http/https only) before being rendered as links
- `string.Template` has no conditionals — any branching in templates must be resolved to HTML strings in `renderer.py` before substitution
- The Homebox instance is considered trusted; markdown in item notes is rendered without sanitisation
