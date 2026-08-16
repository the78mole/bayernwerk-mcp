"""Unit tests for bayernwerk-mcp tool functions.

All tests patch the module-level MapClient/EfixClient/TokenStore, so no real
HTTP requests, token files, or browsers are involved.
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
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            client = MockMapClient.return_value
            client.list_orders.return_value = mock_orders
            result = map_list_orders()
        assert result == mock_orders
        client.close.assert_called_once()

    def test_finished_true_filters_to_finished_orders(self, mock_orders):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            MockMapClient.return_value.list_orders.return_value = mock_orders
            result = map_list_orders(finished=True)
        assert result == [mock_orders[0]]

    def test_finished_false_filters_to_open_orders(self, mock_orders):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            MockMapClient.return_value.list_orders.return_value = mock_orders
            result = map_list_orders(finished=False)
        assert result == [mock_orders[1]]

    def test_no_cached_token_and_no_env_creds_returns_error_dict(self, monkeypatch):
        monkeypatch.delenv("MAP_EMAIL", raising=False)
        monkeypatch.delenv("MAP_PASSWORD", raising=False)
        with patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore:
            MockTokenStore.return_value.load.return_value = None
            result = map_list_orders()
        assert "error" in result
        assert "bayernwerk map login" in result["error"]

    def test_no_cached_token_but_env_creds_logs_in_automatically(self, monkeypatch, mock_orders):
        monkeypatch.setenv("MAP_EMAIL", "test@example.com")
        monkeypatch.setenv("MAP_PASSWORD", "secret")
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
            patch("bayernwerk_client.map.auth.login_interactive") as mock_login,
        ):
            store = MockTokenStore.return_value
            store.load.return_value = None
            mock_login.return_value = "fresh-tokens"
            MockMapClient.return_value.list_orders.return_value = mock_orders

            result = map_list_orders()

        mock_login.assert_called_once_with("test@example.com", "secret", headless=False)
        store.save.assert_called_once_with("fresh-tokens")
        MockMapClient.assert_called_once()
        assert MockMapClient.call_args.args[0] == "fresh-tokens"
        assert result == mock_orders

    def test_expired_token_during_call_relogs_in_with_env_creds(self, monkeypatch, mock_orders):
        monkeypatch.setenv("MAP_EMAIL", "test@example.com")
        monkeypatch.setenv("MAP_PASSWORD", "secret")
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
            patch("bayernwerk_client.map.auth.login_interactive") as mock_login,
        ):
            MockTokenStore.return_value.load.return_value = object()
            mock_login.return_value = "renewed-tokens"
            client = MockMapClient.return_value
            client.list_orders.return_value = mock_orders

            map_list_orders()

            # `on_token_expired` is passed in as a callback, not called by us -
            # simulate MapClient itself invoking it, as `_send` would on expiry.
            on_token_expired = MockMapClient.call_args.kwargs["on_token_expired"]
            renewed = on_token_expired("old-tokens")

        assert renewed == "renewed-tokens"
        mock_login.assert_called_once_with("test@example.com", "secret", headless=False)

    def test_headless_env_var_is_passed_through(self, monkeypatch):
        monkeypatch.setenv("MAP_EMAIL", "test@example.com")
        monkeypatch.setenv("MAP_PASSWORD", "secret")
        monkeypatch.setenv("BAYERNWERK_LOGIN_HEADLESS", "true")
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient"),
            patch("bayernwerk_client.map.auth.login_interactive") as mock_login,
        ):
            MockTokenStore.return_value.load.return_value = None
            mock_login.return_value = "tokens"
            map_list_orders()
        mock_login.assert_called_once_with("test@example.com", "secret", headless=True)

    def test_expired_token_during_call_without_env_creds_returns_error_dict(self, monkeypatch, mock_orders):
        monkeypatch.delenv("MAP_EMAIL", raising=False)
        monkeypatch.delenv("MAP_PASSWORD", raising=False)
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            client = MockMapClient.return_value
            client.list_orders.side_effect = AuthenticationError("token expired")
            result = map_list_orders()
        assert "error" in result
        client.close.assert_called_once()

    def test_api_error_returns_error_dict(self, mock_orders):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            client = MockMapClient.return_value
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
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockMapClient.return_value
        getattr(client, method_name).return_value = {"ok": True}
        result = tool_fn(*args)
    assert result == {"ok": True}
    getattr(client, method_name).assert_called_once_with(*args)
    client.close.assert_called_once()


@pytest.mark.parametrize("tool_fn,method_name,args", SIMPLE_MAP_TOOLS)
def test_map_passthrough_tool_returns_error_on_api_error(tool_fn, method_name, args):
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockMapClient.return_value
        getattr(client, method_name).side_effect = ApiError(404, "not found")
        result = tool_fn(*args)
    assert "error" in result
    client.close.assert_called_once()


# ---------------------------------------------------------------------------
# map_list_inverters
# ---------------------------------------------------------------------------


class TestMapListInverters:
    def test_passes_primary_energy_forms_as_keyword(self):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            MockMapClient.return_value.list_inverters.return_value = [{"model": "X"}]
            result = map_list_inverters(["PV"])
        assert result == [{"model": "X"}]
        MockMapClient.return_value.list_inverters.assert_called_once_with(primary_energy_forms=["PV"])


# ---------------------------------------------------------------------------
# map_list_order_instance_items
# ---------------------------------------------------------------------------


class TestMapListOrderInstanceItems:
    def test_flattens_nested_tree(self, mock_instance_tree):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            client = MockMapClient.return_value
            client.get_order_instances.return_value = mock_instance_tree
            result = map_list_order_instance_items("2577481104")
        assert {item["itemType"] for item in result} == {"METER", "ACTOR"}
        client.get_order_instances.assert_called_once_with("2577481104")


# ---------------------------------------------------------------------------
# map_sync_order_documents
# ---------------------------------------------------------------------------


class TestMapSyncOrderDocuments:
    def test_wraps_downloaded_list_in_dict(self, tmp_path):
        with (
            patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
            patch("bayernwerk_mcp.server.MapClient") as MockMapClient,
        ):
            MockTokenStore.return_value.load.return_value = object()
            client = MockMapClient.return_value
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
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.EfixClient") as MockEfixClient,
    ):
        MockTokenStore.return_value.load.return_value = object()
        client = MockEfixClient.return_value
        getattr(client, method_name).return_value = {"ok": True}
        result = tool_fn()
    assert result == {"ok": True}
    getattr(client, method_name).assert_called_once_with()
    client.close.assert_called_once()


@pytest.mark.parametrize("tool_fn,method_name", SIMPLE_EFIX_TOOLS)
def test_efix_passthrough_tool_returns_error_on_missing_token_and_creds(tool_fn, method_name, monkeypatch):
    monkeypatch.delenv("MAP_EMAIL", raising=False)
    monkeypatch.delenv("MAP_PASSWORD", raising=False)
    with patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore:
        MockTokenStore.return_value.load.return_value = None
        result = tool_fn()
    assert "error" in result
    assert "bayernwerk efix login" in result["error"]


def test_efix_missing_token_with_env_creds_logs_in_automatically(monkeypatch):
    monkeypatch.setenv("MAP_EMAIL", "test@example.com")
    monkeypatch.setenv("MAP_PASSWORD", "secret")
    with (
        patch("bayernwerk_mcp.server.TokenStore") as MockTokenStore,
        patch("bayernwerk_mcp.server.EfixClient") as MockEfixClient,
        patch("bayernwerk_client.efix.auth.login_interactive") as mock_login,
    ):
        store = MockTokenStore.return_value
        store.load.return_value = None
        mock_login.return_value = "fresh-tokens"
        MockEfixClient.return_value.get_user_status.return_value = {"role": "INSTALLER"}

        result = efix_get_user_status()

    mock_login.assert_called_once_with("test@example.com", "secret", headless=False)
    store.save.assert_called_once_with("fresh-tokens")
    assert result == {"role": "INSTALLER"}
