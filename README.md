# bayernwerk-mcp

[![Tests](https://github.com/the78mole/bayernwerk-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/the78mole/bayernwerk-mcp/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

MCP server for the Bayernwerk Netz **Mein.Auftragsportal (MAP)** and
**e-fix Installateur-Portal**, exposing both via the
[Model Context Protocol](https://modelcontextprotocol.io).

Built on top of the [bayernwerk-client](https://github.com/the78mole/bayernwerk-client)
library, which also ships a standalone CLI and can be used directly as a
Python library. This repository only adds the MCP interface on top - it's
an *inoffizieller* (unofficial) integration, reverse-engineered, not
supported or authorized by Bayernwerk/E.ON. Use at your own risk, only with
your own, authorized account.

> **Looking for the Python library or CLI?**
> Head over to [bayernwerk-client](https://github.com/the78mole/bayernwerk-client).

## Authentication

Both portals sit behind a Cloudflare-JS-challenge and a Salesforce Aura
login, so logging in always means a real, Playwright-driven browser - there's
no way around that. This server just decides *when* that browser opens, in
one of two modes:

### Automatic login (recommended if you're at the keyboard)

Set `MAP_EMAIL`/`MAP_PASSWORD` as environment variables on the MCP server
itself (in your MCP client's server config, e.g. `claude_desktop_config.json`
or `.vscode/mcp.json` - see [Configuration](#configuration-in-vs-code--claude-desktop)
below). Whenever a tool call finds no cached token, or a cached token has
expired, the server logs in for you automatically - a Chromium window briefly
opens on **the machine the server runs on** (headed by default, so you can
see and intervene if e.g. an unexpected MFA/consent prompt shows up), fills
in the credentials, and closes again once the token is captured. MAP and
e-fix share one Bayernwerk-Netz account, so one pair of env vars covers both.

Set `BAYERNWERK_LOGIN_HEADLESS=true` to suppress the visible window - only
worth it on a host nobody is watching, and more likely to get stuck on the
Cloudflare challenge (see the bayernwerk-client README for why headed is the
default).

Access tokens last about an hour and there's no reliable silent refresh, so
expect a browser flash roughly every hour during a long session - that's
normal, not a bug.

### Manual login (no credentials on the server)

Without `MAP_EMAIL`/`MAP_PASSWORD` configured, tool calls never open a
browser themselves. Install `bayernwerk-client` with its `login` extra and
run the CLI login once per service, outside of any MCP client, in a normal
terminal:

```bash
uv tool install "bayernwerk-client[login]"
playwright install chromium
bayernwerk map login
bayernwerk efix login
```

This caches a token under `~/.cache/bayernwerk-client/{map,efix}-tokens.json`,
which this server's tools then read directly. If a tool call reports an
authentication error (missing or expired token), re-run the matching `login`
command and retry.

## Tools

### MAP - Mein.Auftragsportal

| Tool | Description |
|------|-------------|
| `map_list_orders` | List all orders, optionally filtered to `finished=True`/`False` |
| `map_get_order` | Fetch a single order by ID |
| `map_get_order_details` | Additional detail data for an order |
| `map_get_order_documents` | List an order's documents (for download, see `map_sync_order_documents`) |
| `map_get_order_notes` | List an order's notes |
| `map_get_order_instances` | Raw "Anschluss" tree (meter → consumers/generators → inverters → storages/PV) |
| `map_list_order_instance_items` | Same tree, flattened into one deduplicated list |
| `map_sync_order_documents` | Download an order's missing documents into a local folder |
| `map_get_installer` | Own installer master data known to MAP |
| `map_list_inverters` | Inverter master data, filtered by `primary_energy_forms` |
| `map_list_storages` | Storage master data |
| `map_list_product_orders` | Product orders (separate from regular orders) |

### e-fix - Installateur-Portal

| Tool | Description |
|------|-------------|
| `efix_get_installer` | Own installer master data known to e-fix (more extensive than `map_get_installer`) |
| `efix_list_installer_antraege` | Own "Anträge" (applications) with status/type/date |
| `efix_get_user_status` | Account status: role, notification counters, subscription |
| `efix_list_my_registered_events` | Registered events/training sessions |

## Installation

### Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- A cached login token from `bayernwerk-client` (see [Authentication](#authentication))

### Install dependencies

```bash
uv sync
```

> `bayernwerk-client` isn't published on PyPI yet, so `pyproject.toml` currently
> pins it to a local editable checkout via `[tool.uv.sources]`. Once it's on
> PyPI, that override (and this note) go away.

### Start the server (development)

```bash
uv run bayernwerk-mcp
# or
uv run python -m bayernwerk_mcp.server
```

### Test with MCP Inspector

```bash
uv run mcp dev src/bayernwerk_mcp/server.py
```

## Configuration in VS Code / Claude Desktop

Add the server to your MCP configuration (`.vscode/mcp.json` or `claude_desktop_config.json`).
The `env` block is optional - add it to enable [automatic login](#automatic-login-recommended-if-youre-at-the-keyboard);
leave it out for [manual login](#manual-login-no-credentials-on-the-server) via the CLI instead.

**Local development (workspace checkout):**

```json
{
  "servers": {
    "bayernwerk": {
      "command": "bash",
      "args": [
        "-l",
        "-c",
        "uv --directory ${workspaceFolder} run bayernwerk-mcp"
      ],
      "env": {
        "MAP_EMAIL": "your@email.de",
        "MAP_PASSWORD": "your-password"
      }
    }
  }
}
```

**Install from GitHub (latest unreleased):**

```json
{
  "servers": {
    "bayernwerk": {
      "command": "bash",
      "args": [
        "-l",
        "-c",
        "uvx --from git+https://github.com/the78mole/bayernwerk-mcp.git bayernwerk-mcp"
      ],
      "env": {
        "MAP_EMAIL": "your@email.de",
        "MAP_PASSWORD": "your-password"
      }
    }
  }
}
```

Once both `bayernwerk-client` and `bayernwerk-mcp` are published on PyPI,
`uvx bayernwerk-mcp` will work directly without the `git+` install.

> **Note:** `bash -l` loads the login shell profile, which ensures `uvx`/`uv`
> are found in `~/.local/bin` without any additional `env` configuration.

> **Credentials in plain text:** `MAP_EMAIL`/`MAP_PASSWORD` end up unencrypted
> in your MCP client's config file (and in this process's environment) when
> set this way - treat that file like any other secret, and skip this if
> you'd rather keep credentials out of it entirely (use manual login instead).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAP_EMAIL` | - | Bayernwerk-Netz account email. If set together with `MAP_PASSWORD`, enables automatic login for both MAP and e-fix. |
| `MAP_PASSWORD` | - | Bayernwerk-Netz account password. |
| `BAYERNWERK_LOGIN_HEADLESS` | `false` | Set to `true` to run the automatic login's browser headless instead of visibly. |

## Local Development

```bash
# Set up project environment
uv sync --extra dev

# Linting & formatting
uv run ruff format .
uv run ruff check --fix .

# Tests
uv run pytest
```

## Related Projects

| Project | Description |
|---------|-------------|
| [bayernwerk-client](https://github.com/the78mole/bayernwerk-client) | Python client library (and CLI) this MCP server is built on |

## License

MIT
