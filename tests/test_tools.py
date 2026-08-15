"""Unit tests for bayernwerk-mcp tool functions.

All tests patch the module-level MapClient/EfixClient classes, so no real
HTTP requests or token files are involved.
"""

from unittest.mock import patch

import pytest
from bayernwerk_client.exceptions import ApiError, AuthenticationError

from bayernwerk_mcp.server import (
    efix_get_installer,
    efix_get_user_status,
    efix_list_installer_antraege,
    efix_list_my_registered_events,
    map_get_installer,
    map_get_order,
    map_get_order_details,
    map_get_order_documents,
    map_get_order_instances,
    map_get_order_notes,
    map_list_inverters,
    map_list_order_instance_items,
    map_list_orders,
    map_list_product_orders,
    map_list_storages,
    map_sync_order_documents,
)

# ---------------------------------------------------------------------------
# map_list_orders
# ---------------------------------------------------------------------------


class TestMapListOrders:
    def test_returns_all_orders_by_default(self, mock_orders):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_orders.return_value = mock_orders
            result = map_list_orders()
        assert result == mock_orders
        client.close.assert_called_once()

    def test_finished_true_filters_to_finished_orders(self, mock_orders):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_orders.return_value = mock_orders
            result = map_list_orders(finished=True)
        assert result == [mock_orders[0]]

    def test_finished_false_filters_to_open_orders(self, mock_orders):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_orders.return_value = mock_orders
            result = map_list_orders(finished=False)
        assert result == [mock_orders[1]]

    def test_missing_token_returns_error_dict(self):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            MockMapClient.from_token_store.side_effect = AuthenticationError("No cached tokens found")
            result = map_list_orders()
        assert "error" in result
        assert "bayernwerk map login" in result["error"]

    def test_expired_token_during_call_returns_error_dict(self, mock_orders):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_orders.side_effect = AuthenticationError("expired")
            result = map_list_orders()
        assert "error" in result
        assert "re-authenticate" in result["error"]
        client.close.assert_called_once()

    def test_api_error_returns_error_dict(self, mock_orders):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_orders.side_effect = ApiError(500, "boom")
            result = map_list_orders()
        assert "error" in result
        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# Simple pass-through MAP tools (order_id or no-arg -> single client call)
# ---------------------------------------------------------------------------

SIMPLE_MAP_TOOLS = [
    (map_get_order, "get_order", ("2577481104",)),
    (map_get_order_details, "get_order_details", ("2577481104",)),
    (map_get_order_documents, "get_order_documents", ("2577481104",)),
    (map_get_order_notes, "get_order_notes", ("2577481104",)),
    (map_get_order_instances, "get_order_instances", ("2577481104",)),
    (map_get_installer, "list_installers", ()),
    (map_list_storages, "list_storages", ()),
    (map_list_product_orders, "list_product_orders", ()),
]


@pytest.mark.parametrize("tool_fn,method_name,args", SIMPLE_MAP_TOOLS)
def test_map_passthrough_tool_delegates_to_client(tool_fn, method_name, args):
    with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
        client = MockMapClient.from_token_store.return_value
        getattr(client, method_name).return_value = {"ok": True}
        result = tool_fn(*args)
    assert result == {"ok": True}
    getattr(client, method_name).assert_called_once_with(*args)
    client.close.assert_called_once()


@pytest.mark.parametrize("tool_fn,method_name,args", SIMPLE_MAP_TOOLS)
def test_map_passthrough_tool_returns_error_on_api_error(tool_fn, method_name, args):
    with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
        client = MockMapClient.from_token_store.return_value
        getattr(client, method_name).side_effect = ApiError(404, "not found")
        result = tool_fn(*args)
    assert "error" in result
    client.close.assert_called_once()


# ---------------------------------------------------------------------------
# map_list_inverters
# ---------------------------------------------------------------------------


class TestMapListInverters:
    def test_passes_primary_energy_forms_as_keyword(self):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.list_inverters.return_value = [{"model": "X"}]
            result = map_list_inverters(["PV"])
        assert result == [{"model": "X"}]
        client.list_inverters.assert_called_once_with(primary_energy_forms=["PV"])


# ---------------------------------------------------------------------------
# map_list_order_instance_items
# ---------------------------------------------------------------------------


class TestMapListOrderInstanceItems:
    def test_flattens_nested_tree(self, mock_instance_tree):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.get_order_instances.return_value = mock_instance_tree
            result = map_list_order_instance_items("2577481104")
        assert {item["itemType"] for item in result} == {"METER", "ACTOR"}
        client.get_order_instances.assert_called_once_with("2577481104")


# ---------------------------------------------------------------------------
# map_sync_order_documents
# ---------------------------------------------------------------------------


class TestMapSyncOrderDocuments:
    def test_wraps_downloaded_list_in_dict(self, tmp_path):
        with patch("bayernwerk_mcp.server.MapClient") as MockMapClient:
            client = MockMapClient.from_token_store.return_value
            client.sync_order_documents.return_value = ["a.pdf", "b.pdf"]
            result = map_sync_order_documents("2577481104", str(tmp_path))
        assert result == {"downloaded": ["a.pdf", "b.pdf"]}
        client.sync_order_documents.assert_called_once_with("2577481104", str(tmp_path))


# ---------------------------------------------------------------------------
# Simple pass-through e-fix tools
# ---------------------------------------------------------------------------

SIMPLE_EFIX_TOOLS = [
    (efix_get_installer, "get_installer"),
    (efix_list_installer_antraege, "list_installer_antraege"),
    (efix_get_user_status, "get_user_status"),
    (efix_list_my_registered_events, "list_my_registered_events"),
]


@pytest.mark.parametrize("tool_fn,method_name", SIMPLE_EFIX_TOOLS)
def test_efix_passthrough_tool_delegates_to_client(tool_fn, method_name):
    with patch("bayernwerk_mcp.server.EfixClient") as MockEfixClient:
        client = MockEfixClient.from_token_store.return_value
        getattr(client, method_name).return_value = {"ok": True}
        result = tool_fn()
    assert result == {"ok": True}
    getattr(client, method_name).assert_called_once_with()
    client.close.assert_called_once()


@pytest.mark.parametrize("tool_fn,method_name", SIMPLE_EFIX_TOOLS)
def test_efix_passthrough_tool_returns_error_on_missing_token(tool_fn, method_name):
    with patch("bayernwerk_mcp.server.EfixClient") as MockEfixClient:
        MockEfixClient.from_token_store.side_effect = AuthenticationError("No cached tokens found")
        result = tool_fn()
    assert "error" in result
    assert "bayernwerk efix login" in result["error"]
