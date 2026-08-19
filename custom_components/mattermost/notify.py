"""Mattermost platform for the notify component (legacy service + notify entity)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_TARGET,
    ATTR_TITLE,
    BaseNotificationService,
    NotifyEntity,
    NotifyEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PATH, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_ATTACHMENTS,
    ATTR_FILE,
    ATTR_PASSWORD,
    ATTR_URL,
    ATTR_USERNAME,
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HASS_CONFIG,
    DOMAIN,
)
from .services import DATA_SCHEMA, MattermostMessenger, _sanitize_channel_names

_LOGGER = logging.getLogger(__name__)

_deprecation_warned = False


def get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> MattermostNotificationService | None:
    """Set up the legacy Mattermost notification service (deprecated)."""
    if discovery_info is None:
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if DATA_CLIENT in entry_data:
                return MattermostNotificationService(
                    hass,
                    entry_data[DATA_CLIENT],
                    entry_data[DATA_HASS_CONFIG],
                    entry_data.get(DATA_COORDINATOR),
                )
        _LOGGER.warning("No Mattermost config entry data found")
    else:
        if DATA_CLIENT in discovery_info:
            return MattermostNotificationService(
                hass,
                discovery_info[DATA_CLIENT],
                discovery_info[DATA_HASS_CONFIG],
                discovery_info.get(DATA_COORDINATOR),
            )
        _LOGGER.warning(
            "No Mattermost data in discovery info, keys available: %s",
            list(discovery_info.keys()) if discovery_info else "None",
        )

    _LOGGER.error("Failed to create Mattermost notification service")
    return None


class MattermostNotificationService(BaseNotificationService):
    """Legacy notify.mattermost service.

    Deprecated in favor of the Mattermost notify entity and the
    mattermost.send_message service. Kept working (soft deprecation) so
    existing automations do not break; logs a warning and raises a repair
    issue on setup rather than failing calls.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client,
        config: dict[str, str],
        coordinator=None,
    ) -> None:
        """Initialize."""
        self._hass = hass
        self._client = client
        self._config = config
        self._messenger = MattermostMessenger(hass, client, coordinator)

        global _deprecation_warned
        if not _deprecation_warned:
            _deprecation_warned = True
            _LOGGER.warning(
                "notify.mattermost is deprecated and will be removed in a future "
                "release. Use the Mattermost notify entity or the "
                "mattermost.send_message service instead."
            )

    @property
    def name(self) -> str:
        """Return the name of the notification service."""
        return "mattermost"

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        """Send a message to Mattermost."""
        data = kwargs.get(ATTR_DATA) or {}

        try:
            DATA_SCHEMA(data)
        except Exception as err:
            _LOGGER.error("Invalid message data: %s", err)
            data = {}

        title = kwargs.get(ATTR_TITLE)
        targets = _sanitize_channel_names(
            kwargs.get(ATTR_TARGET, [self._config[CONF_DEFAULT_CHANNEL]])
        )
        attachments = data.get(ATTR_ATTACHMENTS)

        if ATTR_FILE not in data:
            return await self._messenger.async_send_text(
                targets, message, title, attachments
            )

        file_data = data[ATTR_FILE]
        if CONF_PATH in file_data:
            return await self._messenger.async_send_local_file(
                file_data[CONF_PATH], targets, message, title, attachments
            )

        return await self._messenger.async_send_remote_file(
            file_data[ATTR_URL],
            targets,
            message,
            title,
            attachments=attachments,
            username=file_data.get(ATTR_USERNAME),
            password=file_data.get(ATTR_PASSWORD),
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mattermost notify entity."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    messenger = MattermostMessenger(
        hass, entry_data[DATA_CLIENT], entry_data.get(DATA_COORDINATOR)
    )
    default_channel = entry.data[CONF_DEFAULT_CHANNEL]
    async_add_entities([MattermostNotifyEntity(entry, messenger, default_channel)])


class MattermostNotifyEntity(NotifyEntity):
    """Notify entity that sends messages to the entry's default channel."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(
        self,
        entry: ConfigEntry,
        messenger: MattermostMessenger,
        default_channel: str,
    ) -> None:
        """Initialize the notify entity."""
        self._messenger = messenger
        self._default_channel = default_channel
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Mattermost",
            configuration_url=entry.data.get(CONF_URL),
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a message to the entry's default Mattermost channel."""
        try:
            await self._messenger.async_send_text(
                [self._default_channel], message, title
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(f"Failed to send Mattermost message: {err}")
