"""MCP-protocol-level tests for the bayernwerk MCP server.

These tests call ``mcp.list_tools()`` and ``mcp.call_tool()`` directly on the
MCPServer instance, exercising the full MCP dispatch path (argument
validation, tool lookup, serialisation) without needing a real transport.
"""

import json
from unittest.mock import patch

import pytest

from bayernwerk_mcp.server import mcp

EXPECTED_TOOLS = {
    "map_list_orders",
    "map_get_order",
    "map_get_order_details",
    "map_get_order_documents",
    "map_get_order_notes",
    "map_get_order_instances",
    "map_list_order_instance_items",
    "map_sync_order_documents",
    "map_get_installer",
    "map_list_inverters",
    "map_list_storages",
    "map_list_product_orders",
    "efix_get_installer",
    "efix_list_installer_antraege",
    "efix_get_user_status",
    "efix_list_my_registered_events",
}


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_all_expected_tools_are_registered():
    tools = await mcp.list_tools()
    registered = {t.name for t in tools}
    assert EXPECTED_TOOLS == registered, f"Missing: {EXPECTED_TOOLS - registered}, Extra: {registered - EXPECTED_TOOLS}"


@pytest.mark.anyio
async def test_each_tool_has_description():
    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.description, f"Tool '{tool.name}' has no description"


@pytest.mark.anyio
async def test_map_get_order_has_order_id_parameter():
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "map_get_order")
    params = tool.input_schema.get("properties", {})
    assert "order_id" in params


# ---------------------------------------------------------------------------
# Tool call - map_list_orders
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_call_map_list_orders_returns_orders(mock_orders):
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockMapClient.return_value
        client.list_orders.return_value = mock_orders
        result = await mcp.call_tool("map_list_orders", {})

    data = _parse_result(result)
    orders = data["result"] if isinstance(data, dict) and "result" in data else data
    assert orders == mock_orders


@pytest.mark.anyio
async def test_call_map_get_order_with_order_id(mock_orders):
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockMapClient.return_value
        client.get_order.return_value = mock_orders[0]
        result = await mcp.call_tool("map_get_order", {"order_id": "1"})

    data = _parse_result(result)
    order = data["result"] if isinstance(data, dict) and "result" in data else data
    assert order == mock_orders[0]
    client.get_order.assert_called_once_with("1")


# ---------------------------------------------------------------------------
# Tool call - efix_get_user_status
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_call_efix_get_user_status():
    expected = {"role": "INSTALLER", "fullName": "Test User"}
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.EfixClient") as MockEfixClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockEfixClient.return_value
        client.get_user_status.return_value = expected
        result = await mcp.call_tool("efix_get_user_status", {})

    data = _parse_result(result)
    status = data["result"] if isinstance(data, dict) and "result" in data else data
    assert status == expected


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_result(result):
    """Extract the raw Python value returned by mcp.call_tool().

    Tools here are typed to return `Any` (the backend response shape is
    genuinely dynamic - see server.py), so mcp doesn't infer an output
    schema and leaves `structured_content` unset; fall back to parsing the
    JSON text content in that case. A list return is rendered as one
    TextContent block per item rather than a single JSON array, so
    reassemble those into a list unless there's exactly one block.
    """
    if result.structured_content is not None:
        return result.structured_content
    texts = [json.loads(block.text) for block in result.content]
    return texts[0] if len(texts) == 1 else texts
