"""Shared pytest fixtures for bayernwerk-mcp tests."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_orders():
    return [
        {"orderNumber": "1", "portalProcessStatuses": ["FINISHED"]},
        {"orderNumber": "2", "portalProcessStatuses": ["ACCEPTED"]},
    ]


@pytest.fixture
def mock_instance_tree():
    """A minimal "Anschluss" tree: one meter with a nested actor, as returned
    by MapClient.get_order_instances."""
    return {
        "meters": [
            {
                "itemType": "METER",
                "ivyId": "meter-1",
                "actors": [{"itemType": "ACTOR", "ivyId": "actor-1"}],
            }
        ]
    }
