"""Bridges Mattermost DMs/mentions to Home Assistant's Assist conversation pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant

from .api import MattermostHTTPClient
from .const import CONF_ASSIST_AGENT_ID
from .websocket import MattermostWebSocketClient

_LOGGER = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I didn't understand that."


class MattermostAssistBridge:
    """Relays Mattermost DMs and @mentions to Assist and posts back the reply."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MattermostHTTPClient
    ) -> None:
        """Initialize the bridge."""
        self._hass = hass
        self._entry = entry
        self._client = client
        self._bot_user_id: str | None = None
        self._mention_re: re.Pattern | None = None
        self._ws_client = MattermostWebSocketClient(
            hass, client.base_url, client.token, self._async_handle_posted_event
        )

    async def async_setup(self) -> None:
        """Fetch the bot's own identity and start the websocket listener."""
        user_data = await self._client.get_me()
        if user_data is not None:
            self._bot_user_id = user_data.get("id")
            bot_username = user_data.get("username")
            if bot_username:
                self._mention_re = re.compile(
                    rf"@{re.escape(bot_username)}\b", re.IGNORECASE
                )
        self._ws_client.async_start()

    async def async_unload(self) -> None:
        """Stop the websocket listener."""
        await self._ws_client.async_stop()

    async def _async_handle_posted_event(self, event: dict[str, Any]) -> None:
        """Handle a single 'posted' websocket event."""
        data = event.get("data", {})
        try:
            post = json.loads(data.get("post", "{}"))
        except ValueError:
            _LOGGER.debug("Could not parse post payload from websocket event")
            return

        if not post:
            return

        if self._bot_user_id and post.get("user_id") == self._bot_user_id:
            return  # Ignore our own posts (avoid reply loops).

        message = post.get("message", "")
        channel_id = post.get("channel_id")

        if data.get("channel_type") == "D":
            text = message
        elif self._mention_re and self._mention_re.search(message):
            text = self._mention_re.sub("", message).strip()
        else:
            return

        if not text or not channel_id:
            return

        conversation_id = f"mattermost-{post.get('user_id')}-{channel_id}"
        agent_id = self._entry.options.get(CONF_ASSIST_AGENT_ID) or None

        try:
            result = await conversation.async_converse(
                self._hass,
                text=text,
                conversation_id=conversation_id,
                context=Context(),
                language=self._hass.config.language,
                agent_id=agent_id,
            )
            speech = result.response.speech.get("plain", {}).get("speech")
            reply = speech or FALLBACK_REPLY
        except Exception:
            _LOGGER.exception("Error relaying Mattermost message to Assist")
            reply = FALLBACK_REPLY

        await self._client.post_message(channel_id, reply)
