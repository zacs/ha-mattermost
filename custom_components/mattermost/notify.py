"""Mattermost platform for notify component."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_TARGET,
    ATTR_TITLE,
    BaseNotificationService,
)
from homeassistant.const import CONF_PATH
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_ATTACHMENTS,
    ATTR_AUTHOR_ICON,
    ATTR_AUTHOR_LINK,
    ATTR_AUTHOR_NAME,
    ATTR_COLOR,
    ATTR_FALLBACK,
    ATTR_FIELDS,
    ATTR_FILE,
    ATTR_FOOTER,
    ATTR_FOOTER_ICON,
    ATTR_IMAGE_URL,
    ATTR_PASSWORD,
    ATTR_PATH,
    ATTR_PRETEXT,
    ATTR_TEXT,
    ATTR_THUMB_URL,
)
from .const import ATTR_TITLE as CONST_ATTR_TITLE
from .const import (
    ATTR_TITLE_LINK,
    ATTR_URL,
    ATTR_USERNAME,
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_HASS_CONFIG,
    DOMAIN,
    MATTERMOST_DATA,
)

_LOGGER = logging.getLogger(__name__)

FILE_PATH_SCHEMA = vol.Schema({vol.Required(CONF_PATH): str})

FILE_URL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_URL): str,
        vol.Inclusive(ATTR_USERNAME, "credentials"): str,
        vol.Inclusive(ATTR_PASSWORD, "credentials"): str,
    }
)

ATTACHMENT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_FALLBACK): str,
        vol.Optional(ATTR_COLOR): str,
        vol.Optional(ATTR_PRETEXT): str,
        vol.Optional(ATTR_AUTHOR_NAME): str,
        vol.Optional(ATTR_AUTHOR_LINK): str,
        vol.Optional(ATTR_AUTHOR_ICON): str,
        vol.Optional(CONST_ATTR_TITLE): str,
        vol.Optional(ATTR_TITLE_LINK): str,
        vol.Optional(ATTR_TEXT): str,
        vol.Optional(ATTR_FIELDS): list,
        vol.Optional(ATTR_IMAGE_URL): str,
        vol.Optional(ATTR_THUMB_URL): str,
        vol.Optional(ATTR_FOOTER): str,
        vol.Optional(ATTR_FOOTER_ICON): str,
    }
)

DATA_FILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FILE): vol.Any(FILE_PATH_SCHEMA, FILE_URL_SCHEMA),
    }
)

DATA_TEXT_ONLY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ATTACHMENTS): [ATTACHMENT_SCHEMA],
    }
)

DATA_SCHEMA = vol.All(vol.Any(DATA_FILE_SCHEMA, DATA_TEXT_ONLY_SCHEMA, None))


def get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> MattermostNotificationService | None:
    """Set up the Mattermost notification service."""
    if discovery_info is None:
        # Get the config entry data
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if DATA_CLIENT in entry_data:
                return MattermostNotificationService(
                    hass,
                    entry_data[DATA_CLIENT],
                    entry_data[DATA_HASS_CONFIG],
                )
        _LOGGER.warning("No Mattermost config entry data found")
    else:
        # Discovery info contains the data directly
        if DATA_CLIENT in discovery_info:
            return MattermostNotificationService(
                hass,
                discovery_info[DATA_CLIENT],
                discovery_info[DATA_HASS_CONFIG],
            )
        _LOGGER.warning(
            "No Mattermost data in discovery info, keys available: %s",
            list(discovery_info.keys()) if discovery_info else "None",
        )

    _LOGGER.error("Failed to create Mattermost notification service")
    return None


@callback
def _get_filename_from_url(url: str) -> str:
    """Return the filename of a passed URL."""
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)


@callback
def _sanitize_channel_names(channel_list: list[str]) -> list[str]:
    """Remove any # symbols from a channel list."""
    return [channel.lstrip("#") for channel in channel_list]


class MattermostNotificationService(BaseNotificationService):
    """Define the Mattermost notification logic."""

    def __init__(
        self,
        hass: HomeAssistant,
        client,  # MattermostHTTPClient from __init__.py
        config: dict[str, str],
    ) -> None:
        """Initialize."""
        _LOGGER.info("Initializing MattermostNotificationService")
        self._hass = hass
        self._client = client
        self._config = config
        _LOGGER.debug("MattermostNotificationService initialized")

        # Check service registry access
        try:
            notify_services = list(hass.services.async_services_for_domain("notify"))
            _LOGGER.debug("Available notify services: %d", len(notify_services))
        except Exception as e:
            _LOGGER.debug("Could not access service registry: %s", e)

    @property
    def name(self) -> str:
        """Return the name of the notification service."""
        return "mattermost"

    async def async_setup(self, hass, service_name, target_service_name_prefix):
        """Store the data for the notify service."""
        try:
            result = await super().async_setup(
                hass, service_name, target_service_name_prefix
            )
            return result
        except Exception as e:
            _LOGGER.error("Error in async_setup: %s", e, exc_info=True)
            raise

    async def async_register_services(self):
        """Create or update the notify services."""
        try:
            result = await super().async_register_services()
            return result
        except Exception as e:
            _LOGGER.error("Error in async_register_services: %s", e, exc_info=True)
            raise

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        """Send a message to Mattermost."""
        data = kwargs.get(ATTR_DATA) or {}

        try:
            DATA_SCHEMA(data)
        except vol.Invalid as err:
            _LOGGER.error("Invalid message data: %s", err)
            data = {}

        title = kwargs.get(ATTR_TITLE)
        targets = _sanitize_channel_names(
            kwargs.get(ATTR_TARGET, [self._config[CONF_DEFAULT_CHANNEL]])
        )

        # Message Type 1: A text-only message (possibly with attachments)
        if ATTR_FILE not in data:
            return await self._async_send_text_message(
                targets, message, title, data.get(ATTR_ATTACHMENTS)
            )

        # Message Type 2: A file message
        file_data = data[ATTR_FILE]
        if CONF_PATH in file_data:
            return await self._async_send_local_file_message(
                file_data[CONF_PATH], targets, message, title
            )

        return await self._async_send_remote_file_message(
            file_data[ATTR_URL],
            targets,
            message,
            title,
            username=file_data.get(ATTR_USERNAME),
            password=file_data.get(ATTR_PASSWORD),
        )

    async def _async_send_text_message(
        self,
        targets: list[str],
        message: str,
        title: str | None,
        attachments: list[dict] | None = None,
    ) -> None:
        """Send a text-only message to Mattermost."""
        # Build the message text
        if title and message:
            full_message = f"**{title}**\n\n{message}"
        elif title:
            full_message = f"**{title}**"
        elif message:
            full_message = message
        else:
            # No title or message - only allow if we have attachments
            if attachments:
                full_message = ""  # Empty message with attachments is valid
            else:
                _LOGGER.warning(
                    "Skipping notification: no message, title, or attachments provided"
                )
                return

        failed_targets = []

        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                # Prepare post data
                post_kwargs = {}
                if attachments:
                    # Add default author info to attachments if not specified
                    processed_attachments = []
                    for attachment in attachments:
                        attachment_copy = attachment.copy()
                        if "author_name" not in attachment_copy:
                            attachment_copy["author_name"] = "Home Assistant"
                        if "author_icon" not in attachment_copy:
                            attachment_copy["author_icon"] = (
                                "https://www.home-assistant.io/images/"
                                "favicon-192x192-full.png"
                            )
                        processed_attachments.append(attachment_copy)

                    post_kwargs["props"] = {"attachments": processed_attachments}

                # Send the message using our HTTP client
                await self._client.post_message(channel_id, full_message, **post_kwargs)

            except Exception as err:
                _LOGGER.error("Failed to send message to %s: %s", target, err)
                failed_targets.append(target)

        # Raise exception if any targets failed
        if failed_targets:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(
                f"Failed to send message to channels: {', '.join(failed_targets)}"
            )

    async def _async_send_local_file_message(
        self,
        file_path: str,
        targets: list[str],
        message: str,
        title: str | None,
    ) -> None:
        """Upload a local file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_path(file_path):
            _LOGGER.error("Path does not exist or is not allowed: %s", file_path)
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(f"File path not allowed: {file_path}")

        if not os.path.isfile(file_path):
            _LOGGER.error("File does not exist: %s", file_path)
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(f"File does not exist: {file_path}")

        failed_targets = []

        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                # Upload the file using our HTTP client
                full_message = f"**{title}**\n\n{message}" if title else message
                await self._client.upload_file(channel_id, file_path, full_message)

            except Exception as err:
                _LOGGER.error("Failed to send file to %s: %s", target, err)
                failed_targets.append(target)

        # Raise exception if any targets failed
        if failed_targets:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(
                f"Failed to send file to channels: {', '.join(failed_targets)}"
            )

    async def _async_send_remote_file_message(
        self,
        url: str,
        targets: list[str],
        message: str,
        title: str | None,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Upload a remote file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_external_url(url):
            _LOGGER.error("URL is not allowed: %s", url)
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(f"URL not allowed: {url}")

        filename = _get_filename_from_url(url)

        # Get aiohttp session from Home Assistant
        from homeassistant.helpers import aiohttp_client

        session = aiohttp_client.async_get_clientsession(self._hass)

        # Fetch the remote file
        auth = aiohttp.BasicAuth(username, password) if username and password else None

        try:
            async with session.get(url, auth=auth) as resp:
                resp.raise_for_status()
                file_content = await resp.read()
        except Exception as err:
            _LOGGER.error("Failed to download file from %s: %s", url, err)
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(f"Failed to download file from {url}: {err}")

        # Save to temporary file and upload using our HTTP client
        import tempfile

        failed_targets = []

        for target in targets:
            try:
                # Get channel ID
                channel_id = await self._async_get_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{filename}"
                ) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name

                try:
                    # Upload using our HTTP client
                    full_message = f"**{title}**\n\n{message}" if title else message
                    await self._client.upload_file(
                        channel_id, temp_file_path, full_message
                    )
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_file_path)
                    except OSError:
                        pass

            except Exception as err:
                _LOGGER.error("Failed to send remote file to %s: %s", target, err)
                failed_targets.append(target)

        # Raise exception if any targets failed
        if failed_targets:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(
                f"Failed to send file to channels: {', '.join(failed_targets)}"
            )

    async def _async_get_channel_id(self, channel_name: str) -> str | None:
        """Get channel ID from channel name or return channel ID if already provided."""
        try:
            # Remove # prefix if present
            channel_name = channel_name.lstrip("#")

            # Check if it's already a channel ID
            # (Mattermost channel IDs are 26 character alphanumeric strings)
            if len(channel_name) == 26 and channel_name.isalnum():
                _LOGGER.debug(
                    "Input appears to be a channel ID already: %s", channel_name
                )
                return channel_name

            # Use our HTTP client to get the channel ID from channel name
            async with aiohttp.ClientSession() as session:
                channel_id = await self._client._get_channel_id(session, channel_name)
                if channel_id:
                    _LOGGER.debug(
                        "Resolved channel name '%s' to ID: %s", channel_name, channel_id
                    )
                    return channel_id
                else:
                    _LOGGER.error("Could not resolve channel name: %s", channel_name)
                    return None

        except Exception as err:
            _LOGGER.error("Could not find channel %s: %s", channel_name, err)
            return None
