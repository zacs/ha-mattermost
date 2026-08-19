"""Tests for custom_components.mattermost.api."""

from __future__ import annotations

from aioresponses import aioresponses

from custom_components.mattermost.api import normalize_base_url

from .conftest import TEST_URL

CHANNEL_ID = "a" * 26


class TestNormalizeBaseUrl:
    """Tests for normalize_base_url."""

    def test_bare_local_hostname_defaults_http(self) -> None:
        assert normalize_base_url("192.168.1.100:8065") == "http://192.168.1.100:8065"

    def test_bare_public_domain_defaults_https(self) -> None:
        assert normalize_base_url("chat.example.com") == "https://chat.example.com"

    def test_strips_api_v4_suffix(self) -> None:
        assert (
            normalize_base_url("https://chat.example.com/api/v4")
            == "https://chat.example.com"
        )

    def test_already_schemed_url_passthrough(self) -> None:
        assert normalize_base_url("http://localhost:8065") == "http://localhost:8065"

    def test_localhost_defaults_http(self) -> None:
        assert normalize_base_url("localhost:8065") == "http://localhost:8065"


class TestResolveChannelId:
    """Tests for MattermostHTTPClient.resolve_channel_id."""

    async def test_26_char_id_shortcut_no_http_call(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            result = await mattermost_client.resolve_channel_id(CHANNEL_ID)
        assert result == CHANNEL_ID
        assert len(mocked.requests) == 0

    async def test_resolve_by_api_name(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(
                f"{TEST_URL}/api/v4/users/me/teams",
                payload=[{"id": "team1", "name": "team1"}],
            )
            mocked.get(
                f"{TEST_URL}/api/v4/teams/team1/channels/name/general",
                payload={"id": CHANNEL_ID},
            )
            result = await mattermost_client.resolve_channel_id("general")
        assert result == CHANNEL_ID

    async def test_resolve_by_display_name_fallback(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(
                f"{TEST_URL}/api/v4/users/me/teams",
                payload=[{"id": "team1", "name": "team1"}],
            )
            mocked.get(
                f"{TEST_URL}/api/v4/teams/team1/channels/name/general",
                status=404,
            )
            mocked.get(
                f"{TEST_URL}/api/v4/users/me/teams/team1/channels",
                payload=[{"id": CHANNEL_ID, "display_name": "#general"}],
            )
            result = await mattermost_client.resolve_channel_id("general")
        assert result == CHANNEL_ID

    async def test_not_found_returns_none(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(
                f"{TEST_URL}/api/v4/users/me/teams",
                payload=[{"id": "team1", "name": "team1"}],
            )
            mocked.get(
                f"{TEST_URL}/api/v4/teams/team1/channels/name/missing",
                status=404,
            )
            mocked.get(
                f"{TEST_URL}/api/v4/users/me/teams/team1/channels",
                payload=[],
            )
            result = await mattermost_client.resolve_channel_id("missing")
        assert result is None

    async def test_strips_hash_prefix(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            result = await mattermost_client.resolve_channel_id(f"#{CHANNEL_ID}")
        assert result == CHANNEL_ID
        assert len(mocked.requests) == 0


class TestConnectionAndMessaging:
    """Tests for test_connection/post_message/upload_file happy and failure paths."""

    async def test_connection_success(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(f"{TEST_URL}/api/v4/config/client", status=200, payload={})
            mocked.get(
                f"{TEST_URL}/api/v4/users/me",
                status=200,
                payload={"username": "bot", "is_bot": True},
            )
            assert await mattermost_client.test_connection() is True

    async def test_connection_failure_bad_auth(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(f"{TEST_URL}/api/v4/config/client", status=200, payload={})
            mocked.get(f"{TEST_URL}/api/v4/users/me", status=401, body="unauthorized")
            assert await mattermost_client.test_connection() is False

    async def test_connection_failure_unreachable(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.get(f"{TEST_URL}/api/v4/config/client", status=500, body="oops")
            assert await mattermost_client.test_connection() is False

    async def test_post_message_full_flow(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.post(f"{TEST_URL}/api/v4/posts", status=201, payload={"id": "p1"})
            result = await mattermost_client.post_message(CHANNEL_ID, "hello")
        assert result is True

    async def test_post_message_failure_status(self, mattermost_client) -> None:
        with aioresponses() as mocked:
            mocked.post(f"{TEST_URL}/api/v4/posts", status=500, body="error")
            result = await mattermost_client.post_message(CHANNEL_ID, "hello")
        assert result is False

    async def test_upload_file_success(self, hass, mattermost_client, tmp_path) -> None:
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        with aioresponses() as mocked:
            mocked.post(
                f"{TEST_URL}/api/v4/files",
                status=201,
                payload={"file_infos": [{"id": "file1"}]},
            )
            mocked.post(f"{TEST_URL}/api/v4/posts", status=201, payload={"id": "p1"})
            result = await mattermost_client.upload_file(
                CHANNEL_ID, str(file_path), "hello"
            )
        assert result is True

    async def test_upload_file_upload_failure(
        self, hass, mattermost_client, tmp_path
    ) -> None:
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        with aioresponses() as mocked:
            mocked.post(f"{TEST_URL}/api/v4/files", status=500, body="error")
            result = await mattermost_client.upload_file(
                CHANNEL_ID, str(file_path), "hello"
            )
        assert result is False
