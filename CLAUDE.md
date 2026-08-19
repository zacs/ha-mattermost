# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Home Assistant custom component (HACS integration) that connects to Mattermost servers via a bot account. It supports a modern `notify` entity, a `mattermost.send_message` service (rich attachments, multi-channel targeting, local/remote file uploads), a legacy `notify.mattermost` action (soft-deprecated), a binary connectivity sensor, and an optional Assist chat bridge (Mattermost DMs/@mentions relayed to Home Assistant's conversation pipeline). All source lives under `custom_components/mattermost/`.

## Commands

```bash
# Format code (required before commit; CI enforces this)
black .
isort .

# Check formatting without modifying files (what CI actually runs)
black --check --diff .
isort --check-only --diff .

# Lint for critical errors only (undefined names, syntax errors) -- what CI runs
flake8 custom_components/ --count --select=E9,F63,F7,F82 --show-source --statistics

# Broader lint (unused imports etc.) -- not CI-enforced but worth running after refactors
flake8 custom_components/ tests/ --max-line-length=100 --extend-ignore=E203,W503

# Validate JSON config files
python3 -c "import json; json.load(open('custom_components/mattermost/manifest.json'))"
python3 -c "import json; json.load(open('custom_components/mattermost/translations/en.json'))"

# Run the test suite (pytest-homeassistant-custom-component; no real HA instance needed)
pip install -r requirements_test.txt
pytest tests/ -v
```

Black is configured for line-length 88, target py311 (`pyproject.toml`); isort uses the `black` profile. `pyproject.toml` also configures pytest (`asyncio_mode = "auto"`, `testpaths = ["tests"]`). CI (`.github/workflows/validate.yml`) runs style/lint/tests plus HACS validation (`hacs/action`) and Home Assistant's `hassfest` validator — the latter two can't be run locally, so keep `manifest.json`, `services.yaml`, and `translations/en.json`/`strings.json` in sync with each other and with HA integration conventions when changing config schema or services. It also has `workflow_dispatch`, so it can be re-run on demand from the Actions tab or `gh workflow run` without needing a new commit.

HACS's `<Validation issues>` and `<Validation topics>` checks require the exact GitHub repo running CI to have Issues enabled and at least one topic set. On a fork or dev clone that doesn't have those set, those two checks fail even though the integration itself is fine — don't spend time trying to "fix" them if that's the situation; every other CI job (style, lint, file structure, hassfest, and the pytest suite) staying green is the real signal to watch.

The `test` job's dependencies (`requirements_test.txt`) pin `homeassistant`, `pytest-homeassistant-custom-component`, `hassil`, and `home-assistant-intents` together as a matched set, not independently — `pytest-homeassistant-custom-component` doesn't pin `homeassistant` tightly enough for pip to resolve a compatible `hassil` on its own, and `hassil`'s API the `conversation` component needs changes between minor versions. If you bump one of these four, re-verify all four together (install fresh, run `pytest tests/`) rather than bumping in isolation. Also note the pinned `homeassistant` version requires Python ≥3.13.2, which is why the `test` job's `Setup Python` step is on 3.13 while the style/lint jobs stay on 3.11 (they don't need a `homeassistant` install).

`pytest-homeassistant-custom-component` pulls in a specific pinned `homeassistant` core version (plus `hassil`/`home-assistant-intents`, transitively required because `assist_bridge.py` imports `homeassistant.components.conversation`). There's no local HA instance to run the integration against interactively; the test suite (via `hass`/`MockConfigEntry` fixtures) and `aioresponses`-mocked HTTP calls are the closest available substitute for manually driving the integration.

## Architecture

**Config entry setup (`__init__.py`)** is the entry point. `async_setup` registers the domain-wide `mattermost.send_message` service (once, regardless of how many config entries exist) via `services.async_register_services`. `async_setup_entry`:
1. Normalizes the user-supplied server URL (`api.normalize_base_url` — strips `/api/v4` if present, infers `http://` vs `https://` for local IPs/hostnames vs public domains).
2. Constructs a `MattermostHTTPClient` (`api.py`) — a thin `aiohttp`-based wrapper around the Mattermost REST API (`/api/v4/...`) handling connection testing, posting messages, uploading files, fetching the bot's own identity, and resolving channel names to IDs.
3. Creates a `MattermostDataUpdateCoordinator` and calls `async_config_entry_first_refresh()` — a failure here raises `ConfigEntryNotReady`, which HA surfaces as a setup failure with automatic retry.
4. Forwards `PLATFORMS = [Platform.BINARY_SENSOR, Platform.NOTIFY]` via the standard config-entry mechanism (this is how the modern notify entity gets set up), then separately sets up the legacy notify platform via `discovery.async_load_platform` (this is how the deprecated `notify.mattermost` action gets registered) — both run side by side.
5. If `entry.options[CONF_ENABLE_ASSIST_BRIDGE]` is set, constructs and starts a `MattermostAssistBridge` (`assist_bridge.py`); stored in `hass.data[DOMAIN][entry_id][DATA_ASSIST_BRIDGE]` (`None` if disabled) and torn down in `async_unload_entry`.
6. Registers an options-update listener that reloads the entry on any options change (this is how toggling the Assist bridge on/off in the UI takes effect without a full re-add).

**Connectivity monitoring (`coordinator.py`)**: `MattermostDataUpdateCoordinator` polls `client.test_connection()` every `SCAN_INTERVAL_SECONDS` (300s, `const.py`). After `FAILURE_THRESHOLD` (3) consecutive failures it triggers `hass.config_entries.async_reload()` on itself, which re-runs `async_setup_entry` → re-raises `ConfigEntryNotReady` if still down, putting the integration into HA's native "failed to set up, will retry" state. Send failures elsewhere in the integration call `MattermostMessenger._async_request_health_refresh()` to force an out-of-band connectivity check rather than waiting for the poll interval.

**Message sending (`services.py`)**: `MattermostMessenger` is the single shared implementation of text/local-file/remote-file sending (three consumers: the legacy `notify.mattermost` service, the `NotifyEntity`, and `mattermost.send_message`). All three paths resolve channel names to IDs per-target via `client.resolve_channel_id` and collect `failed_targets`, raising a single `HomeAssistantError` at the end if any target failed — a partial failure across multiple targets does not stop delivery to the rest. Attachments get `author_name`/`author_icon` defaults injected (`_process_attachments`) unless the caller overrides them. Local files must pass `hass.config.is_allowed_path`; remote URLs must pass `hass.config.is_allowed_external_url` — both are Home Assistant security boundaries and must not be bypassed. `async_register_services` registers `mattermost.send_message` once, domain-wide, from `async_setup` (never per-entry — HA's convention for custom services); it routes a call to the right config entry via an explicit `config_entry_id` field, falling back to the single loaded entry if only one exists, else raising `ServiceValidationError`.

**Notify platform (`notify.py`)** contains two independent, coexisting setup paths, since they're invoked by two different HA-core mechanisms (legacy discovery vs. config-entry forwarding):
- Legacy: module-level `get_service()` returns `MattermostNotificationService` (a `BaseNotificationService` thin wrapper around `MattermostMessenger`). This is `notify.mattermost`, soft-deprecated: it logs a one-time warning and raises a persistent repair issue (`ISSUE_DEPRECATED_NOTIFY_SERVICE`) on first setup, but keeps working — do not remove without a further deprecation cycle.
- Modern: module-level `async_setup_entry()` creates a `MattermostNotifyEntity(NotifyEntity)`, one per config entry, sending only to that entry's configured default channel (no channel targeting or attachments — `NotifyEntityFeature` has no flag for that; richer functionality is intentionally exclusive to `mattermost.send_message`).

**Channel resolution**: `MattermostHTTPClient.resolve_channel_id` (`api.py`) is the single public entry point every consumer uses — do not open a session and call the "private" `_get_channel_id` directly from outside the client. It iterates all teams the bot belongs to, first trying the API channel name, then falling back to matching display name (with/without `#`). A 26-character alphanumeric input is treated as an already-resolved channel ID and returned as-is without a lookup. The Assist bridge's reply path is the one exception that does *not* use this — Mattermost's websocket `posted` event already carries a channel ID, not a name.

**Config flow (`config_flow.py`)**: `async_step_user` and `async_step_reconfigure` share logic via `_async_step_connect(user_input, is_reconfigure)`. `_async_try_connect` probes `/api/v4/system/ping` then `/api/v4/config/client`, falling back to `/api/v4/hooks/incoming` for tokens that lack config-read permission but can still authenticate (403 there still proves the token is valid). Multiple config entries (multiple Mattermost servers) are supported; entry titles are derived from the server hostname (`_title_for`) to keep them distinguishable in the UI. `MattermostOptionsFlowHandler` exposes the Assist bridge opt-in toggle (`CONF_ENABLE_ASSIST_BRIDGE`, default off — enabling it grants HA chat-command access to anyone who can DM/mention the bot) and an optional specific conversation agent (`CONF_ASSIST_AGENT_ID`). Only config-entry setup is supported — no YAML (`CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`).

**Assist bridge (`assist_bridge.py`, `websocket.py`)**: `MattermostWebSocketClient` is a thin transport layer — connects to `wss://<host>/api/v4/websocket`, sends the `authentication_challenge` frame, forwards `posted` events to a callback, reconnects with capped exponential backoff on drop. `MattermostAssistBridge` owns one of these, caches the bot's own user ID/username at setup (`client.get_me()`) to ignore self-authored posts (critical — otherwise its own reply loops back as a new `posted` event) and detect `@botname` mentions, and relays DMs (`channel_type == "D"`) or channel messages that mention the bot to `conversation.async_converse`, posting the reply back to the exact incoming channel ID. Because the integration depends on `homeassistant.components.conversation`, `manifest.json` declares `"dependencies": ["conversation"]`.

**Constants (`const.py`)**: all Mattermost attachment field names, service/option/data-key constants live here as `ATTR_*`/`CONF_*`/`DATA_*`; `services.py`'s voluptuous schemas and the attachment-processing code pull from this single source, so new attachment fields should be added here first.

## Conventions

- SSL verification is explicitly disabled (`ssl=False`) on all Mattermost API and websocket calls throughout the codebase — this is intentional, to support self-signed certs on local Mattermost instances. Preserve this if touching HTTP/websocket client code.
- `MattermostHTTPClient` methods generally catch broad `Exception`, log, and return `False`/`None` rather than raising — callers (`services.py`) are responsible for turning failures into `HomeAssistantError`.
- `manifest.json` is the source of truth for the integration version; bump it when publishing a release (the `release.yml` workflow validates but does not bump versions).
- `notify.mattermost` is soft-deprecated, not removed. Do not delete `get_service`/`MattermostNotificationService` from `notify.py` without a further explicit deprecation cycle.
