"""Constants for the Mattermost integration."""

from typing import Final

ATTR_ATTACHMENTS = "attachments"
ATTR_AUTHOR_ICON = "author_icon"
ATTR_AUTHOR_LINK = "author_link"
ATTR_AUTHOR_NAME = "author_name"
ATTR_COLOR = "color"
ATTR_FALLBACK = "fallback"
ATTR_FIELDS = "fields"
ATTR_FILE = "file"
ATTR_FOOTER = "footer"
ATTR_FOOTER_ICON = "footer_icon"
ATTR_IMAGE_URL = "image_url"
ATTR_MESSAGE = "message"
ATTR_PASSWORD = "password"
ATTR_PATH = "path"
ATTR_PRETEXT = "pretext"
ATTR_TARGET = "target"
ATTR_TEXT = "text"
ATTR_THUMB_URL = "thumb_url"
ATTR_TITLE = "title"
ATTR_TITLE_LINK = "title_link"
ATTR_URL = "url"
ATTR_USERNAME = "username"

CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_DEFAULT_CHANNEL = "default_channel"
CONF_ENABLE_ASSIST_BRIDGE = "enable_assist_bridge"
CONF_ASSIST_AGENT_ID = "assist_agent_id"

DATA_ASSIST_BRIDGE = "assist_bridge"
DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DEFAULT_ENABLE_ASSIST_BRIDGE = False
DEFAULT_NAME = "Mattermost"
DEFAULT_TIMEOUT_SECONDS = 30
DOMAIN: Final = "mattermost"

ISSUE_DEPRECATED_NOTIFY_SERVICE = "deprecated_notify_service"

SERVICE_SEND_MESSAGE = "send_message"

# How often to poll the Mattermost server to verify connectivity.
SCAN_INTERVAL_SECONDS = 300

MATTERMOST_DATA = "data"
DATA_HASS_CONFIG = "mattermost_hass_config"
