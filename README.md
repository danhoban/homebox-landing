# Homebox External Landing Page

A lightweight Python HTTP server that intercepts external QR code scans for a self-hosted [Homebox](https://github.com/sysadminsmedia/homebox) inventory instance and serves a public-facing landing page. When someone outside your network scans a QR code, they see a clean, mobile-friendly page with item details and your contact information — instead of a login screen.

Internal network traffic continues to reach Homebox directly, unchanged.

## How It Works

Your reverse proxy detects external visitors and redirects them from `/a/{asset_id}` to `/landing?ref=/a/{asset_id}`. The Python server handles that request by:

1. Looking up the asset in Homebox via `GET /api/v1/assets/{asset_id}`
2. Fetching full item detail via `GET /api/v1/items/{uuid}`
3. Matching the item's tags against your configured tag→template mappings
4. Firing an Apprise notification in a background thread
5. Rendering and returning an HTML page

## Templates

Three page types are included out of the box:

- **plant.html** — hero photo, tag pills, latin name, detail grid, care notes (markdown), contact reveal
- **item.html** — lost item page with SVG hero, item details, asset reference, contact reveal
- **fallback.html** — shown when Homebox is unreachable
- **not_found.html** — shown when the asset ID doesn't match anything

Tag→template mapping is fully configurable. You can add your own templates by placing an HTML file in `templates/` and pointing a `TEMPLATE_N` entry at it.

## Requirements

- Python 3.9+
- nginx (for TLS termination and internal/external routing)
- A running Homebox instance

## Installation

```bash
git clone https://github.com/danhoban/homebox-landing.git
cd homebox-landing
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Homebox credentials and contact details
```

## Configuration

All configuration is in `.env`. Copy `.env.example` to get started. Key settings:

| Variable | Description |
|---|---|
| `HOMEBOX_URL` | Internal or external Homebox URL |
| `HOMEBOX_USERNAME` / `HOMEBOX_PASSWORD` | Homebox credentials |
| `TEMPLATE_DEFAULT` | Fallback template filename |
| `TEMPLATE_N_TAG` / `TEMPLATE_N_FILE` | Tag→template mapping (numbered from 1) |
| `TEMPLATE_N_NOTIFY` | Apprise notification URLs for this template (comma-separated) |
| `TEMPLATE_N_NOTIFY_TITLE` / `TEMPLATE_N_NOTIFY_BODY` | Optional custom notification text; supports `{name}` token |
| `CONTACT_N_TYPE` / `CONTACT_N_LABEL` / `CONTACT_N_VALUE` | Public contact details (numbered from 1) |
| `SERVER_HOST` / `SERVER_PORT` | Bind address (default `127.0.0.1:8080`) |

See `.env.example` for full documentation and examples.

## Running

```bash
python -m app.main
```

For production, run via systemd:

```ini
[Unit]
Description=Homebox public landing page
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/homebox-landing
ExecStart=/usr/bin/python3 -m app.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Reverse Proxy Integration

The Python server binds to `127.0.0.1` only and is not directly internet-facing. Your reverse proxy (nginx, Caddy, Traefik, etc.) should:

1. Detect whether the request is from an internal or external client
2. For **external** requests: redirect `/a/{asset_id}` → `/landing?ref=/a/{asset_id}` (302)
3. Proxy `/landing` and `/landing/photo/` to `127.0.0.1:8080`
4. Continue proxying everything else directly to Homebox as normal

Apply rate limiting to `/landing` at the proxy level — the app itself does no rate limiting.

A sample nginx configuration is provided in [`docs/nginx.conf`](docs/nginx.conf).

## Notifications

Notifications are powered by [Apprise](https://github.com/caronc/apprise), which supports 80+ services including Home Assistant webhooks, Ntfy, Pushover, Slack, and more. Configure notification URLs per template in `.env`.

## Licence

This project is licensed under the GNU General Public License v3. See [LICENCE](LICENCE) for details.
