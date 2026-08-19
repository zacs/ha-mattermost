"""Fixtures for the Mattermost integration tests."""

from __future__ import annotations

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mattermost.api import MattermostHTTPClient
from custom_components.mattermost.const import CONF_DEFAULT_CHANNEL, DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

TEST_URL = "https://mattermost.example.com"
TEST_TOKEN = "test-token-1234567890"
TEST_CHANNEL = "general"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test in this suite."""
    yield


@pytest.fixture(autouse=True)
async def _setup_homeassistant_component(hass):
    """Set up HA's core 'homeassistant' component.

    Our manifest declares 'conversation' as a dependency, and HA loads
    dependencies even just to initiate a config flow. conversation's default
    agent setup reaches into the core 'homeassistant' component's exposed-
    entities data, which -- unlike in a real HA instance -- is not already
    set up by the bare pytest-homeassistant-custom-component hass fixture.
    """
    await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for the Mattermost integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Mattermost (mattermost.example.com)",
        data={
            "url": TEST_URL,
            "api_key": TEST_TOKEN,
            CONF_DEFAULT_CHANNEL: TEST_CHANNEL,
        },
        unique_id=f"{TEST_URL}_{TEST_TOKEN[:8]}",
    )


@pytest.fixture
def mattermost_client(hass) -> MattermostHTTPClient:
    """Return a real MattermostHTTPClient pointed at the test server."""
    return MattermostHTTPClient(hass, TEST_URL, TEST_TOKEN)
