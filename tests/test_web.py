import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet

from bot.music import PlayerManager, Track
from bot.music.control import ControlError, MusicControl
from bot.web.configuration import WebConfig
from bot.web.server import COOKIE, APIError, WebServer
from bot.youtube.playlist import PlaylistTarget
from bot.youtube.search import PlayTarget


class WebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = WebConfig(
            public_url="http://localhost",
            client_id="123",
            client_secret="test-secret",
            encryption_key=Fernet.generate_key().decode(),
            database=Path(self.tmp.name) / "web.sqlite3",
            secure_cookie=False,
        )
        self.permissions = SimpleNamespace(
            view_channel=True,
            connect=True,
            speak=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
        )
        self.channel = SimpleNamespace(
            id=10, name="VC", permissions_for=lambda m: self.permissions
        )
        self.member = SimpleNamespace(
            id=1,
            display_name="Member",
            voice=SimpleNamespace(channel=self.channel),
            guild_permissions=SimpleNamespace(manage_guild=False),
        )
        self.voice = SimpleNamespace(
            channel=self.channel,
            is_connected=lambda: True,
            is_paused=lambda: False,
            is_playing=lambda: True,
            pause=Mock(),
        )
        self.guild = SimpleNamespace(
            id=100,
            name="One",
            voice_client=self.voice,
            me=Mock(),
            text_channels=[],
            get_member=lambda uid: self.member,
            fetch_member=AsyncMock(return_value=self.member),
        )
        self.other = SimpleNamespace(**{**vars(self.guild), "id": 200, "name": "Two"})
        self.not_member = discord.NotFound(
            SimpleNamespace(status=404, reason="Not Found"),
            {"message": "Unknown Member", "code": 10007},
        )
        self.other.fetch_member = AsyncMock(side_effect=self.not_member)
        self.bot = Mock(
            guilds=[self.guild, self.other],
            is_ready=Mock(return_value=True),
            is_closed=Mock(return_value=False),
            get_guild=Mock(
                side_effect=lambda gid: {100: self.guild, 200: self.other}.get(gid)
            ),
        )
        self.manager = PlayerManager(self.bot)
        self.control = MusicControl(self.manager)
        self.service = Mock(deliver=AsyncMock())
        self.server = WebServer(self.bot, self.control, self.service, self.config)

        async def discord_api(token, path):
            if "/200/member" in path:
                raise APIError(403, "not a member")
            if path == "/users/@me/guilds":
                return [
                    {"id": "100", "name": "One", "icon": None},
                    {"id": "300", "name": "No bot", "icon": None},
                ]
            return {"id": "1", "username": "Member"}

        self.server.discord = AsyncMock(side_effect=discord_api)
        self.client = TestClient(TestServer(self.server.app()))
        await self.client.start_server()
        self.token = self.server.store.create_session(
            {
                "user": {"id": "1", "username": "Member"},
                "access_token": "private-access",
                "refresh_token": "private-refresh",
                "token_expires": time.time() + 3600,
            },
            3600,
        )
        self.client.session.cookie_jar.update_cookies({COOKIE: self.token})
        self.csrf = self.server.store.session(self.token)[0]["csrf"]

    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()

    def headers(self, **extra):
        return {
            "Origin": "http://localhost",
            "X-CSRF-Token": self.csrf,
            "X-Request-ID": "test-request-123",
            **extra,
        }

    async def test_unauthenticated_api_and_csrf_are_rejected(self):
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={"action": "pause"},
            headers=self.headers(Origin="https://evil.example"),
        )
        self.assertEqual(response.status, 403)
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={"action": "pause"},
            headers=self.headers(**{"X-CSRF-Token": "bad"}),
        )
        self.assertEqual(response.status, 403)
        self.client.session.cookie_jar.clear()
        self.assertEqual((await self.client.get("/api/guilds/100/state")).status, 401)

    async def test_guild_list_is_intersection(self):
        response = await self.client.get("/api/guilds")
        self.assertEqual([g["id"] for g in (await response.json())["guilds"]], ["100"])

    async def test_cross_guild_state_and_actions_are_forbidden(self):
        self.manager.get(200)._current = Track(
            "https://youtube.com/watch?v=12345678901", "secret", "Other"
        )
        for method, path in (
            ("get", "state"),
            ("post", "actions"),
            ("get", "jobs/anything"),
        ):
            response = await getattr(self.client, method)(
                f"/api/guilds/200/{path}",
                headers=self.headers(),
                **({"json": {"action": "pause"}} if method == "post" else {}),
            )
            self.assertEqual(response.status, 403)
            self.assertNotIn("secret", await response.text())

    async def test_revoked_membership_blocks_write_despite_read_cache(self):
        self.assertEqual((await self.client.get("/api/guilds/100/state")).status, 200)
        self.guild.fetch_member.side_effect = self.not_member
        response = await self.client.post(
            "/api/guilds/100/actions", json={"action": "pause"}, headers=self.headers()
        )
        self.assertEqual(response.status, 403)

    async def test_different_vc_rejected_for_both_entrypoints(self):
        self.member.voice.channel = SimpleNamespace(id=20)
        with self.assertRaises(ControlError):
            await self.control.apply(self.guild, self.member, "pause")
        response = await self.client.post(
            "/api/guilds/100/actions", json={"action": "pause"}, headers=self.headers()
        )
        self.assertEqual(response.status, 400)

    async def test_periodic_state_does_not_call_oauth_member_endpoint(self):
        self.server.discord.side_effect = APIError(503, "OAuth rate limited")
        for _ in range(10):
            response = await self.client.get("/api/guilds/100/state")
            self.assertEqual(response.status, 200)
        self.server.discord.assert_not_awaited()
        self.guild.fetch_member.assert_awaited_once()
        response = await self.client.post(
            "/api/guilds/100/actions", json={"action": "pause"}, headers=self.headers()
        )
        self.assertEqual(response.status, 202)
        await asyncio.gather(*list(self.server.tasks))
        self.assertGreater(self.guild.fetch_member.await_count, 1)
        self.assertTrue(all(j["status"] == "done" for j in self.server.jobs.values()))

    async def test_guild_list_is_cached_between_page_reloads(self):
        for _ in range(3):
            self.assertEqual((await self.client.get("/api/guilds")).status, 200)
        self.server.discord.assert_awaited_once()

    async def test_private_vc_does_not_leak_queue(self):
        self.permissions.view_channel = False
        self.manager.get(100)._current = Track(
            "https://youtube.com/watch?v=12345678901", "private", "A"
        )
        response = await self.client.get("/api/guilds/100/state")
        self.assertEqual(response.status, 403)
        self.assertNotIn("private", await response.text())

    async def test_duplicate_operation_runs_once(self):
        self.control.apply = AsyncMock(return_value=True)
        first = await self.client.post(
            "/api/guilds/100/actions", json={"action": "pause"}, headers=self.headers()
        )
        second = await self.client.post(
            "/api/guilds/100/actions", json={"action": "pause"}, headers=self.headers()
        )
        self.assertEqual(first.status, 202)
        self.assertEqual((await first.json())["id"], (await second.json())["id"])
        self.control.apply.assert_awaited_once()

    async def test_setting_requires_manage_guild_and_channel_from_same_guild(self):
        response = await self.client.put(
            "/api/guilds/100/settings",
            json={"channel_id": "999"},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 403)
        self.member.guild_permissions.manage_guild = True
        response = await self.client.put(
            "/api/guilds/100/settings",
            json={"channel_id": "999"},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 400)

    async def test_logout_invalidates_session(self):
        self.assertEqual(
            (await self.client.post("/auth/logout", headers=self.headers())).status, 200
        )
        self.assertIsNone(self.server.store.session(self.token))
        self.assertEqual((await self.client.get("/api/me")).status, 401)

    async def test_tokens_not_returned_or_stored_in_plaintext(self):
        response = await self.client.get("/api/me")
        self.assertNotIn("private-", await response.text())
        blob = self.server.store.db.execute("SELECT id,data FROM sessions").fetchone()
        self.assertNotEqual(blob["id"], self.token)
        self.assertNotIn(b"private-access", blob["data"])

    async def test_oauth_state_requires_cookie_and_is_single_use(self):
        state = self.server.store.new_state()
        response = await self.client.get(
            "/auth/callback?state=" + state, allow_redirects=False
        )
        self.assertEqual(response.status, 400)
        self.client.session.cookie_jar.update_cookies({"music_oauth_state": state})
        response = await self.client.get(
            "/auth/callback?state=" + state + "&error=access_denied",
            allow_redirects=False,
        )
        self.assertEqual(response.status, 302)
        response = await self.client.get(
            "/auth/callback?state=" + state, allow_redirects=False
        )
        self.assertEqual(response.status, 400)

    async def test_concurrent_refresh_uses_one_refresh_token_exchange(self):
        data, expires = self.server.store.session(self.token)
        data["token_expires"] = 0
        self.server.store.save_session(self.token, data, expires)
        self.server.token = AsyncMock(
            return_value={
                "access_token": "new",
                "refresh_token": "rotated",
                "expires_in": 3600,
            }
        )
        responses = await asyncio.gather(
            *[self.client.get("/api/me") for _ in range(3)]
        )
        self.assertTrue(all(r.status == 200 for r in responses))
        self.server.token.assert_awaited_once()

    async def test_web_download_rejects_external_hosts(self):
        for url in (
            "https://youtube.com.evil.example/watch?v=abc",
            "http://127.0.0.1/watch",
            "https://www.youtube.com@127.0.0.1/watch",
        ):
            with self.subTest(url=url), self.assertRaises(APIError):
                self.server.validate_download(url, "480p")

    async def test_playlist_preview_requires_confirmation_and_imports_selected_count(
        self,
    ):
        target = PlaylistTarget(
            "https://www.youtube.com/playlist?list=PL123",
            "My playlist",
            [
                PlayTarget(f"https://www.youtube.com/watch?v={i:011d}", str(i))
                for i in range(50)
            ],
            truncated=True,
        )
        self.server.resolve = AsyncMock(return_value=target)
        self.server.notification_channel = Mock(return_value=SimpleNamespace(id=10))
        self.control.enqueue_many = AsyncMock(return_value=["queued"])
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={"action": "playlist_preview", "query": target.url},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 202)
        await asyncio.gather(*list(self.server.tasks))
        self.control.enqueue_many.assert_not_awaited()
        state = await (await self.client.get("/api/guilds/100/state")).json()
        preview = state["jobs"][0]["preview"]
        self.assertEqual(preview["maximum"], 50)
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={
                "action": "play",
                "query": target.url,
                "preview_id": preview["id"],
                "count": 3,
            },
            headers=self.headers(**{"X-Request-ID": "confirm-playlist-123"}),
        )
        self.assertEqual(response.status, 202)
        await asyncio.gather(*list(self.server.tasks))
        self.assertEqual(
            [t.title for t in self.control.enqueue_many.await_args.args[2]],
            ["0", "1", "2"],
        )
        self.assertNotIn(preview["id"], self.server.previews)

    async def test_playlist_without_preview_or_invalid_count_is_rejected(self):
        self.server.notification_channel = Mock(return_value=SimpleNamespace(id=10))
        url = "https://www.youtube.com/playlist?list=PL123"
        target = PlaylistTarget(url, "List", [PlayTarget("x", "x") for _ in range(50)])
        self.server.previews["preview"] = {
            "owner": "1",
            "guild": "100",
            "target": target,
            "expires": time.monotonic() + 300,
        }
        for preview_id, count in (
            ("missing", 1),
            ("preview", 0),
            ("preview", 51),
            ("preview", True),
            ("preview", "5"),
        ):
            response = await self.client.post(
                "/api/guilds/100/actions",
                json={
                    "action": "play",
                    "query": url,
                    "preview_id": preview_id,
                    "count": count,
                },
                headers=self.headers(),
            )
            self.assertEqual(response.status, 400)
        for owner, guild in (("2", 100), ("1", 200)):
            with self.assertRaises(APIError):
                self.server.preview("preview", owner, guild)
        self.server.previews["preview"]["expires"] = 0
        with self.assertRaises(APIError):
            self.server.preview("preview", "1", 100)

    async def test_queue_batch_is_rejected_without_partial_insertion(self):
        self.control.max_queue = 1
        player = self.manager.get(100)
        player.enqueue = AsyncMock()
        with self.assertRaises(ControlError):
            await self.control.enqueue_many(
                self.guild, self.member, [Track("a", "a", "a"), Track("b", "b", "b")]
            )
        player.enqueue.assert_not_awaited()

    async def test_volume_validation_and_queue_limit(self):
        for value in (0, 101, True, "50"):
            with self.assertRaises(ControlError):
                await self.control.apply(self.guild, self.member, "volume", value=value)
        self.control.max_queue = 0
        with self.assertRaises(ControlError):
            await self.control.enqueue(self.guild, self.member, Track("x", "x", "x"))


if __name__ == "__main__":
    unittest.main()
