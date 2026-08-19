"""Shared message-sending logic and the mattermost.send_message service."""

from __future__ import annotations

import logging
import os
import tempfile
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant.const import CONF_PATH
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import config_validation as cv

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
    ATTR_MESSAGE,
    ATTR_PASSWORD,
    ATTR_PRETEXT,
    ATTR_TARGET,
    ATTR_TEXT,
    ATTR_THUMB_URL,
    ATTR_TITLE,
    ATTR_TITLE_LINK,
    ATTR_URL,
    ATTR_USERNAME,
    CONF_CONFIG_ENTRY_ID,
    CONF_DEFAULT_CHANNEL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HASS_CONFIG,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
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
        vol.Optional(ATTR_TITLE): str,
        vol.Optional(ATTR_TITLE_LINK): str,
        vol.Optional(ATTR_TEXT): str,
        vol.Optional(ATTR_FIELDS): list,
        vol.Optional(ATTR_IMAGE_URL): str,
        vol.Optional(ATTR_THUMB_URL): str,
        vol.Optional(ATTR_FOOTER): str,
        vol.Optional(ATTR_FOOTER_ICON): str,
    }
)

DATA_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Optional(ATTR_FILE): vol.Any(FILE_PATH_SCHEMA, FILE_URL_SCHEMA),
            vol.Optional(ATTR_ATTACHMENTS): [ATTACHMENT_SCHEMA],
        }
    ),
    None,
)

SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): str,
        vol.Optional(ATTR_TITLE): str,
        vol.Optional(ATTR_MESSAGE, default=""): str,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [str]),
        vol.Optional(ATTR_FILE): vol.Any(FILE_PATH_SCHEMA, FILE_URL_SCHEMA),
        vol.Optional(ATTR_ATTACHMENTS): [ATTACHMENT_SCHEMA],
    }
)


@callback
def _get_filename_from_url(url: str) -> str:
    """Return the filename of a passed URL."""
    parsed_url = urlparse(url)
    return os.path.basename(parsed_url.path)


@callback
def _sanitize_channel_names(channel_list: list[str]) -> list[str]:
    """Remove any # symbols from a channel list."""
    return [channel.lstrip("#") for channel in channel_list]


class MattermostMessenger:
    """Send text, local-file, and remote-file messages to Mattermost channels."""

    def __init__(self, hass: HomeAssistant, client, coordinator=None) -> None:
        """Initialize."""
        self._hass = hass
        self._client = client
        self._coordinator = coordinator

    async def async_send_text(
        self,
        targets: list[str],
        message: str,
        title: str | None,
        attachments: list[dict] | None = None,
    ) -> None:
        """Send a text-only message to Mattermost."""
        if title and message:
            full_message = f"**{title}**\n\n{message}"
        elif title:
            full_message = f"**{title}**"
        elif message:
            full_message = message
        else:
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
                channel_id = await self._client.resolve_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                post_kwargs = {}
                if attachments:
                    post_kwargs["props"] = {
                        "attachments": self._process_attachments(attachments)
                    }

                await self._client.post_message(channel_id, full_message, **post_kwargs)

            except Exception as err:
                _LOGGER.error("Failed to send message to %s: %s", target, err)
                failed_targets.append(target)

        if failed_targets:
            self._async_request_health_refresh()
            raise HomeAssistantError(
                f"Failed to send message to channels: {', '.join(failed_targets)}"
            )

    async def async_send_local_file(
        self,
        file_path: str,
        targets: list[str],
        message: str,
        title: str | None,
        attachments: list[dict] | None = None,
    ) -> None:
        """Upload a local file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_path(file_path):
            _LOGGER.error("Path does not exist or is not allowed: %s", file_path)
            raise HomeAssistantError(f"File path not allowed: {file_path}")

        if not os.path.isfile(file_path):
            _LOGGER.error("File does not exist: %s", file_path)
            raise HomeAssistantError(f"File does not exist: {file_path}")

        failed_targets = []

        for target in targets:
            try:
                channel_id = await self._client.resolve_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                full_message = f"**{title}**\n\n{message}" if title else message
                post_kwargs = {}
                if attachments:
                    post_kwargs["props"] = {
                        "attachments": self._process_attachments(attachments)
                    }
                await self._client.upload_file(
                    channel_id, file_path, full_message, **post_kwargs
                )

            except Exception as err:
                _LOGGER.error("Failed to send file to %s: %s", target, err)
                failed_targets.append(target)

        if failed_targets:
            self._async_request_health_refresh()
            raise HomeAssistantError(
                f"Failed to send file to channels: {', '.join(failed_targets)}"
            )

    async def async_send_remote_file(
        self,
        url: str,
        targets: list[str],
        message: str,
        title: str | None,
        *,
        attachments: list[dict] | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Upload a remote file (with message) to Mattermost."""
        if not self._hass.config.is_allowed_external_url(url):
            _LOGGER.error("URL is not allowed: %s", url)
            raise HomeAssistantError(f"URL not allowed: {url}")

        filename = _get_filename_from_url(url)

        session = aiohttp_client.async_get_clientsession(self._hass)

        auth = aiohttp.BasicAuth(username, password) if username and password else None

        try:
            async with session.get(url, auth=auth) as resp:
                resp.raise_for_status()
                file_content = await resp.read()
        except Exception as err:
            _LOGGER.error("Failed to download file from %s: %s", url, err)
            raise HomeAssistantError(f"Failed to download file from {url}: {err}")

        failed_targets = []

        for target in targets:
            try:
                channel_id = await self._client.resolve_channel_id(target)
                if not channel_id:
                    _LOGGER.error("Could not find channel: %s", target)
                    failed_targets.append(target)
                    continue

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{filename}"
                ) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name

                try:
                    full_message = f"**{title}**\n\n{message}" if title else message
                    post_kwargs = {}
                    if attachments:
                        post_kwargs["props"] = {
                            "attachments": self._process_attachments(attachments)
                        }
                    await self._client.upload_file(
                        channel_id, temp_file_path, full_message, **post_kwargs
                    )
                finally:
                    try:
                        os.unlink(temp_file_path)
                    except OSError:
                        pass

            except Exception as err:
                _LOGGER.error("Failed to send remote file to %s: %s", target, err)
                failed_targets.append(target)

        if failed_targets:
            self._async_request_health_refresh()
            raise HomeAssistantError(
                f"Failed to send file to channels: {', '.join(failed_targets)}"
            )

    def _async_request_health_refresh(self) -> None:
        """Ask the connectivity coordinator to re-check the server soon."""
        if self._coordinator is not None:
            self._hass.async_create_task(self._coordinator.async_request_refresh())

    @staticmethod
    def _process_attachments(attachments: list[dict]) -> list[dict]:
        """Add default author info to attachments if not specified."""
        processed = []
        for attachment in attachments:
            attachment_copy = attachment.copy()
            if "author_name" not in attachment_copy:
                attachment_copy["author_name"] = "Home Assistant"
            if "author_icon" not in attachment_copy:
                attachment_copy["author_icon"] = (
                    "https://www.home-assistant.io/images/" "favicon-192x192-full.png"
                )
            processed.append(attachment_copy)
        return processed


def _resolve_entry_id(hass: HomeAssistant, call: ServiceCall) -> str:
    """Resolve which config entry a mattermost.send_message call targets."""
    entries = hass.data.get(DOMAIN, {})
    requested_entry_id = call.data.get(CONF_CONFIG_ENTRY_ID)

    if requested_entry_id is not None:
        if requested_entry_id not in entries:
            raise ServiceValidationError(
                f"No loaded Mattermost config entry with id: {requested_entry_id}"
            )
        return requested_entry_id

    if len(entries) == 1:
        return next(iter(entries))

    if not entries:
        raise ServiceValidationError("No Mattermost config entries are loaded")

    raise ServiceValidationError(
        "Multiple Mattermost servers are configured; specify config_entry_id "
        "to select which one to send the message through"
    )


async def _handle_send_message(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the mattermost.send_message service call."""
    entry_id = _resolve_entry_id(hass, call)
    entry_data = hass.data[DOMAIN][entry_id]
    messenger = MattermostMessenger(
        hass, entry_data[DATA_CLIENT], entry_data.get(DATA_COORDINATOR)
    )

    message = call.data.get(ATTR_MESSAGE, "")
    title = call.data.get(ATTR_TITLE)
    target = call.data.get(ATTR_TARGET)
    if target is None:
        target = [entry_data[DATA_HASS_CONFIG][CONF_DEFAULT_CHANNEL]]
    targets = _sanitize_channel_names(target)
    attachments = call.data.get(ATTR_ATTACHMENTS)
    file_data = call.data.get(ATTR_FILE)

    if file_data is None:
        await messenger.async_send_text(targets, message, title, attachments)
        return

    if CONF_PATH in file_data:
        await messenger.async_send_local_file(
            file_data[CONF_PATH], targets, message, title, attachments
        )
        return

    await messenger.async_send_remote_file(
        file_data[ATTR_URL],
        targets,
        message,
        title,
        attachments=attachments,
        username=file_data.get(ATTR_USERNAME),
        password=file_data.get(ATTR_PASSWORD),
    )


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the mattermost.send_message service (domain-wide, once)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        return

    async def _service_handler(call: ServiceCall) -> None:
        await _handle_send_message(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        _service_handler,
        schema=SEND_MESSAGE_SCHEMA,
    )
