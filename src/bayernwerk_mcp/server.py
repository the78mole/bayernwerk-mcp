"""
Bayernwerk MCP Server

Exposes the Bayernwerk Netz Mein.Auftragsportal (MAP) and e-fix installer
portal via the Model Context Protocol (MCP). Tools wrap the bayernwerk-client
library's MapClient and EfixClient.

Both portals sit behind a Cloudflare-JS-challenge + Salesforce Aura login
that only a real browser can complete (see bayernwerk-client's README for
why), so logging in is always a Playwright-driven browser flow - this server
just decides *when* to trigger it:

- If MAP_EMAIL/MAP_PASSWORD are set in this process's environment (configured
  as env vars on the MCP server in e.g. claude_desktop_config.json), a tool
  call with no/expired cached token logs in automatically via
  bayernwerk_client's login_interactive - headed (visible browser) by
  default, since that's needed for the Cloudflare challenge and lets you
  handle an unexpected MFA/consent prompt if one appears. Set
  BAYERNWERK_LOGIN_HEADLESS=true to run headless instead (only worth it on a
  host nobody is watching, and more likely to get stuck on the Cloudflare
  challenge).
- Without those env vars, a missing/expired token instead returns an
  {"error": ...} telling you to run `bayernwerk map login` / `bayernwerk
  efix login` (the bayernwerk-client CLI) manually.

MAP and e-fix share one Bayernwerk-Netz account, so both use the same
MAP_EMAIL/MAP_PASSWORD - matching the bayernwerk-client CLI's own convention.
"""

import os
from collections.abc import Callable
from typing import Any

from bayernwerk_client.efix.client import EFIX_TOKEN_PATH, EfixClient
from bayernwerk_client.exceptions import ApiError, AuthenticationError
from bayernwerk_client.map.client import MAP_TOKEN_PATH, MapClient
from bayernwerk_client.map.formatting import is_order_finished
from bayernwerk_client.map.instances import iter_instance_items
from bayernwerk_client.tokens import TokenSet, TokenStore
from mcp.server.mcpserver import MCPServer

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "bayernwerk",
    instructions=(
        "Access to the Bayernwerk Netz Mein.Auftragsportal (MAP, `map_*` tools) and the "
        "e-fix installer portal (`efix_*` tools). If MAP_EMAIL/MAP_PASSWORD are configured "
        "on this server, missing/expired logins are handled automatically (a browser window "
        "may briefly appear on the server's machine). Otherwise, if a tool reports an "
        "authentication error, tell the user to run `bayernwerk map login` or `bayernwerk "
        "efix login` (bayernwerk-client CLI) in a terminal, then retry. Order-related tools "
        "take a Bayernwerk order ID such as '2577481104', as seen in the portal or returned "
        "by map_list_orders."
    ),
)


def _login_headless() -> bool:
    return os.environ.get("BAYERNWERK_LOGIN_HEADLESS", "").strip().lower() in ("1", "true", "yes")


def _login_from_env(service: str) -> TokenSet:
    """Run bayernwerk_client's Playwright login using MAP_EMAIL/MAP_PASSWORD.

    Args:
        service: "map" or "efix" - only picks the right login_interactive/CLI
            hint, both services read the same MAP_EMAIL/MAP_PASSWORD.
    """
    email = os.environ.get("MAP_EMAIL")
    password = os.environ.get("MAP_PASSWORD")
    if not email or not password:
        raise AuthenticationError(
            f"No cached {service} token and MAP_EMAIL/MAP_PASSWORD are not configured on "
            f"this server. Either set them as env vars in the MCP server config to enable "
            f"automatic login, or run `bayernwerk {service} login` manually."
        )
    if service == "map":
        from bayernwerk_client.map.auth import login_interactive
    else:
        from bayernwerk_client.efix.auth import login_interactive
    return login_interactive(email, password, headless=_login_headless())


def _map_call(fn: Callable[[MapClient], Any]) -> Any:
    """Run `fn` against a MapClient, auto-logging in via MAP_EMAIL/MAP_PASSWORD (if
    configured) whenever the cached token is missing or expires, and translating
    remaining auth/API failures into an `{"error": ...}` dict instead of raising."""
    store = TokenStore(MAP_TOKEN_PATH)
    try:
        tokens = store.load()
        if tokens is None:
            tokens = _login_from_env("map")
            store.save(tokens)
        client = MapClient(tokens, token_store=store, on_token_expired=lambda _old: _login_from_env("map"))
    except AuthenticationError as exc:
        return {"error": str(exc)}
    try:
        return fn(client)
    except AuthenticationError as exc:
        return {"error": str(exc)}
    except ApiError as exc:
        return {"error": str(exc)}
    finally:
        client.close()


def _efix_call(fn: Callable[[EfixClient], Any]) -> Any:
    """Same as `_map_call`, for the e-fix portal."""
    store = TokenStore(EFIX_TOKEN_PATH)
    try:
        tokens = store.load()
        if tokens is None:
            tokens = _login_from_env("efix")
            store.save(tokens)
        client = EfixClient(tokens, token_store=store, on_token_expired=lambda _old: _login_from_env("efix"))
    except AuthenticationError as exc:
        return {"error": str(exc)}
    try:
        return fn(client)
    except AuthenticationError as exc:
        return {"error": str(exc)}
    except ApiError as exc:
        return {"error": str(exc)}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# MAP tools (Mein.Auftragsportal, REST)
# ---------------------------------------------------------------------------


@mcp.tool()
def map_list_orders(finished: bool | None = None) -> Any:
    """List all orders ("Aufträge") from Mein.Auftragsportal.

    Args:
        finished: If True, only orders with status FINISHED. If False, only
            open (not yet finished) orders. If omitted, all orders.

    Returns:
        List of raw order dicts as returned by the portal backend.
    """

    def _run(client: MapClient) -> Any:
        orders = client.list_orders()
        if finished is True:
            return [order for order in orders if is_order_finished(order)]
        if finished is False:
            return [order for order in orders if not is_order_finished(order)]
        return orders

    return _map_call(_run)


@mcp.tool()
def map_get_order(order_id: str) -> Any:
    """Fetch a single order by its order ID.

    Args:
        order_id: Order number, e.g. "2577481104".

    Returns:
        Raw order dict (same shape as one entry from map_list_orders).
    """
    return _map_call(lambda client: client.get_order(order_id))


@mcp.tool()
def map_get_order_details(order_id: str) -> Any:
    """Fetch additional detail data for an order (separate endpoint from map_get_order).

    Args:
        order_id: Order number, e.g. "2577481104".
    """
    return _map_call(lambda client: client.get_order_details(order_id))


@mcp.tool()
def map_get_order_documents(order_id: str) -> Any:
    """List the documents attached to an order (filename, type, scan status, ...).

    To actually download documents, use map_sync_order_documents.

    Args:
        order_id: Order number, e.g. "2577481104".
    """
    return _map_call(lambda client: client.get_order_documents(order_id))


@mcp.tool()
def map_get_order_notes(order_id: str) -> Any:
    """List the notes attached to an order.

    Args:
        order_id: Order number, e.g. "2577481104".
    """
    return _map_call(lambda client: client.get_order_notes(order_id))


@mcp.tool()
def map_get_order_instances(order_id: str) -> Any:
    """Fetch the raw "Anschluss" (connection) tree of an order: meter -> consumers/
    generators -> inverters -> storages/PV, as nested by the backend.

    For a flat list instead of the raw nested tree, use map_list_order_instance_items.

    Args:
        order_id: Order number, e.g. "2577481104".
    """
    return _map_call(lambda client: client.get_order_instances(order_id))


@mcp.tool()
def map_list_order_instance_items(order_id: str) -> Any:
    """Flatten an order's "Anschluss" tree into a single list of items (meters,
    actors, inverters, storages, ...), deduplicated regardless of nesting.

    Equivalent to map_get_order_instances, but easier to scan: every item with
    an itemType field, in one flat list instead of a nested tree.

    Args:
        order_id: Order number, e.g. "2577481104".

    Returns:
        List of item dicts, each with at least itemType and usually schemaType/formData.
    """
    return _map_call(lambda client: list(iter_instance_items(client.get_order_instances(order_id))))


@mcp.tool()
def map_sync_order_documents(order_id: str, folder: str) -> dict[str, Any]:
    """Download an order's documents into a local folder, skipping ones already there.

    Compares the order's document list against files already present in `folder`
    (matched by filename) and downloads only the missing ones. Existing files are
    left untouched. `folder` is created if it doesn't exist.

    Args:
        order_id: Order number, e.g. "2577481104".
        folder: Local directory path to sync documents into.

    Returns:
        Dict with "downloaded" (list of filenames newly downloaded).
    """
    return _map_call(lambda client: {"downloaded": client.sync_order_documents(order_id, folder)})


@mcp.tool()
def map_get_installer() -> Any:
    """Fetch the own installer master data (company, address, contact) known to MAP."""
    return _map_call(lambda client: client.list_installers())


@mcp.tool()
def map_list_inverters(primary_energy_forms: list[str]) -> Any:
    """List inverter master data (available models).

    Args:
        primary_energy_forms: Required filter, e.g. ["PV"] or ["AC_STORAGE"].
    """
    return _map_call(lambda client: client.list_inverters(primary_energy_forms=primary_energy_forms))


@mcp.tool()
def map_list_storages() -> Any:
    """List storage master data (available battery models/capacities)."""
    return _map_call(lambda client: client.list_storages())


@mcp.tool()
def map_list_product_orders() -> Any:
    """List product orders (separate from the regular orders in map_list_orders)."""
    return _map_call(lambda client: client.list_product_orders())


# ---------------------------------------------------------------------------
# e-fix tools (Installateur-Portal, GraphQL)
# ---------------------------------------------------------------------------


@mcp.tool()
def efix_get_installer() -> Any:
    """Fetch the own installer master data known to e-fix (company, address, contact,
    grid-operator assignment, certification status, ...) - more extensive than
    map_get_installer, since e-fix maintains its own master data."""
    return _efix_call(lambda client: client.get_installer())


@mcp.tool()
def efix_list_installer_antraege() -> Any:
    """List the own "Anträge" (applications) with status, type/subtype and received date."""
    return _efix_call(lambda client: client.list_installer_antraege())


@mcp.tool()
def efix_get_user_status() -> Any:
    """Fetch the account status: role, notification counters, subscription status, name/email."""
    return _efix_call(lambda client: client.get_user_status())


@mcp.tool()
def efix_list_my_registered_events() -> Any:
    """List events/training sessions the account is registered for, with their dates."""
    return _efix_call(lambda client: client.list_my_registered_events())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the bayernwerk MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
