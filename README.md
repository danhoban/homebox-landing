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

- Docker, or Python 3.9+
- A reverse proxy handling TLS (nginx, Caddy, Traefik, etc.)
- A running Homebox instance

## Installation

### Docker (recommended)

```bash
# Pull the image
docker pull ghcr.io/danhoban/homebox-landing:latest

# Create your config
cp .env.example .env
# Edit .env with your Homebox credentials and contact details

# Run with docker compose (see docs/docker-compose.yml)
docker compose -f docs/docker-compose.yml up -d
```

A sample [`docs/docker-compose.yml`](docs/docker-compose.yml) is provided. It binds the server to `127.0.0.1:8080` and mounts your `.env` file into the container.

### From source

```bash
git clone https://github.com/danhoban/homebox-landing.git
cd homebox-landing
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Homebox credentials and contact details
python -m app.main
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
| `TEMPLATE_N_NOTIFY_TITLE` / `TEMPLATE_N_NOTIFY_BODY` | Optional custom notification text; supports `{name}`, `{ip}`, `{description}` tokens |
| `CONTACT_N_TYPE` / `CONTACT_N_LABEL` / `CONTACT_N_VALUE` | Public contact details (numbered from 1) |
| `SERVER_HOST` / `SERVER_PORT` | Bind address (default `127.0.0.1:8080`) |

See `.env.example` for full documentation and examples.

## Docker image

The image is published to GHCR on every push to `main` and tagged `latest` plus the short commit SHA:

```
ghcr.io/danhoban/homebox-landing:latest
ghcr.io/danhoban/homebox-landing:sha-<commit>
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

The notification title and body are plain strings with optional substitution tokens:

| Token | Value |
|---|---|
| `{name}` | Item name from Homebox |
| `{ip}` | Client IP address (reads `X-Forwarded-For` / `X-Real-IP` from your reverse proxy, falls back to the raw socket address) |
| `{description}` | Item description from Homebox (empty string if not set) |

Example:
```
TEMPLATE_DEFAULT_NOTIFY_BODY={name} was scanned from {ip} — {description}
```

## Licence

This project is licensed under the GNU General Public License v3. See [LICENCE](LICENCE) for details.
