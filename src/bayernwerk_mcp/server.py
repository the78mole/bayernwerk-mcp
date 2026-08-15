"""
Bayernwerk MCP Server

Exposes the Bayernwerk Netz Mein.Auftragsportal (MAP) and e-fix installer
portal via the Model Context Protocol (MCP). Tools wrap the bayernwerk-client
library's MapClient and EfixClient.

Authentication is out of scope for this server: both portals sit behind a
Cloudflare-JS-challenge + Salesforce Aura login that only a real browser can
complete (see bayernwerk-client's README for why). Run `bayernwerk map login`
/ `bayernwerk efix login` from the bayernwerk-client CLI once (and again
whenever a tool call reports an expired/missing token) - this server only
ever reads the token cache those commands populate, it never launches a
browser itself.
"""

from collections.abc import Callable
from typing import Any

from bayernwerk_client.efix.client import EFIX_TOKEN_PATH, EfixClient
from bayernwerk_client.exceptions import ApiError, AuthenticationError
from bayernwerk_client.map.client import MAP_TOKEN_PATH, MapClient
from bayernwerk_client.map.formatting import is_order_finished
from bayernwerk_client.map.instances import iter_instance_items
from bayernwerk_client.tokens import TokenStore
from mcp.server.mcpserver import MCPServer

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "bayernwerk",
    instructions=(
        "Access to the Bayernwerk Netz Mein.Auftragsportal (MAP, `map_*` tools) and the "
        "e-fix installer portal (`efix_*` tools). Both need a one-time interactive login "
        "outside this server - if a tool reports an authentication error, tell the user to "
        "run `bayernwerk map login` or `bayernwerk efix login` (bayernwerk-client CLI) in a "
        "terminal, then retry. Order-related tools take a Bayernwerk order ID such as "
        "'2577481104', as seen in the portal or returned by map_list_orders."
    ),
)


def _map_call(fn: Callable[[MapClient], Any]) -> Any:
    """Run `fn` against a fresh MapClient loaded from the cached token, translating
    auth/API failures into an `{"error": ...}` dict instead of raising."""
    try:
        client = MapClient.from_token_store(TokenStore(MAP_TOKEN_PATH))
    except AuthenticationError as exc:
        return {"error": f"{exc} Run `bayernwerk map login` to authenticate."}
    try:
        return fn(client)
    except AuthenticationError as exc:
        return {"error": f"{exc} Run `bayernwerk map login` to re-authenticate."}
    except ApiError as exc:
        return {"error": str(exc)}
    finally:
        client.close()


def _efix_call(fn: Callable[[EfixClient], Any]) -> Any:
    """Same as `_map_call`, for the e-fix portal."""
    try:
        client = EfixClient.from_token_store(TokenStore(EFIX_TOKEN_PATH))
    except AuthenticationError as exc:
        return {"error": f"{exc} Run `bayernwerk efix login` to authenticate."}
    try:
        return fn(client)
    except AuthenticationError as exc:
        return {"error": f"{exc} Run `bayernwerk efix login` to re-authenticate."}
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
