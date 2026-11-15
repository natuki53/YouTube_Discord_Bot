import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet

from bot.music import PlayerManager, Track
from bot.music.control import ControlError, MusicControl
from bot.web.configuration import WebConfig
from bot.web.server import COOKIE, APIError, WebServer
from bot.youtube.playlist import PlaylistTarget
from bot.youtube.recommendations import RadioTrack, RecommendationError
from bot.youtube.search import PlayTarget, SearchError, SearchResult


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

    async def test_search_browses_before_joining_voice_and_caches_without_enqueuing(
        self,
    ):
        self.member.voice = None
        track = SearchResult("12345678901", "Chosen song", "Artist", 245)
        self.control.enqueue = AsyncMock()
        with patch(
            "bot.web.server.search_workers.run", new=AsyncMock(return_value=[track])
        ) as lookup:
            for query in (" song ", "song"):
                response = await self.client.post(
                    "/api/guilds/100/search",
                    json={"query": query},
                    headers=self.headers(),
                )
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                data = await response.json()
                self.assertEqual(data["query"], "song")
                self.assertEqual(
                    data["results"],
                    [
                        {
                            "video_id": track.video_id,
                            "url": track.url,
                            "title": track.title,
                            "channel": "Artist",
                            "duration": 245,
                        }
                    ],
                )
            lookup.assert_awaited_once()
        self.control.enqueue.assert_not_awaited()
        self.assertEqual(self.server.jobs, {})
        self.assertIsNone(self.manager.get_existing(100))

    async def test_search_requires_login_csrf_membership_and_valid_query_even_on_cache_hit(
        self,
    ):
        self.server.search_cache["song"] = (time.monotonic() + 60, [])
        with patch("bot.web.server.search_workers.run", new=AsyncMock()) as lookup:
            for query in (None, "", " ", "x" * 501, [], 123):
                response = await self.client.post(
                    "/api/guilds/100/search",
                    json={"query": query},
                    headers=self.headers(),
                )
                self.assertEqual(response.status, 400)
            for headers in (
                self.headers(Origin="https://evil.example"),
                self.headers(**{"X-CSRF-Token": "wrong"}),
            ):
                response = await self.client.post(
                    "/api/guilds/100/search", json={"query": "song"}, headers=headers
                )
                self.assertEqual(response.status, 403)
            response = await self.client.post(
                "/api/guilds/200/search", json={"query": "song"}, headers=self.headers()
            )
            self.assertEqual(response.status, 403)
            self.guild.fetch_member.side_effect = self.not_member
            response = await self.client.post(
                "/api/guilds/100/search", json={"query": "song"}, headers=self.headers()
            )
            self.assertEqual(response.status, 403)
            self.client.session.cookie_jar.clear()
            response = await self.client.post(
                "/api/guilds/100/search", json={"query": "song"}, headers=self.headers()
            )
            self.assertEqual(response.status, 401)
            lookup.assert_not_awaited()

    async def test_search_rechecks_membership_after_lookup_and_does_not_cache_failed_authorization(
        self,
    ):
        async def revoke(*args):
            self.guild.fetch_member.side_effect = self.not_member
            return [SearchResult("12345678901", "song", None, None)]

        with patch(
            "bot.web.server.search_workers.run", new=AsyncMock(side_effect=revoke)
        ):
            response = await self.client.post(
                "/api/guilds/100/search", json={"query": "song"}, headers=self.headers()
            )
        self.assertEqual(response.status, 403)
        self.assertNotIn("song", self.server.search_cache)

    async def test_search_distinguishes_empty_results_upstream_failure_and_limits(self):
        with patch(
            "bot.web.server.search_workers.run", new=AsyncMock(return_value=[])
        ) as lookup:
            response = await self.client.post(
                "/api/guilds/100/search",
                json={"query": "absent"},
                headers=self.headers(),
            )
            self.assertEqual(
                (response.status, (await response.json())["results"]), (200, [])
            )
            lookup.side_effect = SearchError("YouTube検索に失敗しました。")
            response = await self.client.post(
                "/api/guilds/100/search",
                json={"query": "failed"},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 502)
            self.assertNotIn("failed", self.server.search_cache)
        self.server.search_users.add("1")
        response = await self.client.post(
            "/api/guilds/100/search", json={"query": "busy"}, headers=self.headers()
        )
        self.assertEqual(response.status, 429)
        self.server.search_users.clear()
        self.server.searches = {object() for _ in range(4)}
        response = await self.client.post(
            "/api/guilds/100/search",
            json={"query": "global busy"},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 429)
        self.server.searches.clear()
        for _ in range(6):
            response = await self.client.post(
                "/api/guilds/100/search",
                json={"query": "absent"},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 200)
        response = await self.client.post(
            "/api/guilds/100/search", json={"query": "absent"}, headers=self.headers()
        )
        self.assertEqual(response.status, 429)

    async def test_timed_out_search_remains_counted_until_worker_finishes(self):
        release = asyncio.Event()
        started = asyncio.Event()

        async def slow(*args):
            started.set()
            await release.wait()
            return []

        async def time_out(awaitable, *, timeout):
            await started.wait()
            awaitable.cancel()  # Cancel the shield, not the worker.
            raise TimeoutError

        with (
            patch("bot.web.server.search_workers.run", new=AsyncMock(side_effect=slow)),
            patch("bot.web.server.asyncio.wait_for", side_effect=time_out),
        ):
            response = await self.client.post(
                "/api/guilds/100/search", json={"query": "slow"}, headers=self.headers()
            )
            self.assertEqual(response.status, 504)
            self.assertEqual(len(self.server.searches), 1)
            self.assertIn("1", self.server.search_users)
            response = await self.client.post(
                "/api/guilds/100/search",
                json={"query": "again"},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 429)
            pending = list(self.server.searches)
            release.set()
            await asyncio.gather(*pending)
        self.assertEqual(self.server.searches, set())
        self.assertEqual(self.server.search_users, set())

    async def test_search_cache_expires_and_is_bounded(self):
        self.server.search_cache = {
            f"song-{i}": (time.monotonic() + 60, []) for i in range(100)
        }
        with patch(
            "bot.web.server.search_workers.run", new=AsyncMock(return_value=[])
        ) as lookup:
            response = await self.client.post(
                "/api/guilds/100/search",
                json={"query": "new song"},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 200)
            self.assertEqual(len(self.server.search_cache), 100)
            self.server.search_cache["new song"] = (0, [])
            await self.client.post(
                "/api/guilds/100/search",
                json={"query": "new song"},
                headers=self.headers(),
            )
            self.assertEqual(lookup.await_count, 2)

    async def test_selected_video_uses_existing_enqueue_permissions_and_rechecks_voice(
        self,
    ):
        selected_url = "https://www.youtube.com/watch?v=23456789012"
        self.server.resolve = AsyncMock(
            return_value=PlayTarget(selected_url, "Chosen song")
        )
        self.server.notification_channel = Mock(return_value=SimpleNamespace(id=10))
        self.control.enqueue = AsyncMock(return_value="queued")
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={"action": "play", "query": selected_url},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 202)
        await asyncio.gather(*list(self.server.tasks))
        self.server.resolve.assert_awaited_once_with(selected_url)
        self.assertEqual(self.control.enqueue.await_args.args[2].url, selected_url)
        self.member.voice = None
        response = await self.client.post(
            "/api/guilds/100/actions",
            json={"action": "play", "query": selected_url},
            headers=self.headers(**{"X-Request-ID": "after-leaving-voice"}),
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(self.control.enqueue.await_count, 1)

    async def test_recommendations_can_be_browsed_with_autoplay_off_and_without_voice(self):
        player = self.manager.get(100)
        seed = player._current = Track("https://youtu.be/seed0000001", "Seed", "Member")
        player.get_autoplay_candidates = AsyncMock(return_value=[RadioTrack("next0000001", "Next")])
        self.member.voice = None
        self.control.enqueue = AsyncMock()
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        body = await response.json()
        self.assertEqual(body["track_id"], seed.queue_id)
        self.assertEqual(
            body["results"][0]["url"], "https://www.youtube.com/watch?v=next0000001"
        )
        self.control.enqueue.assert_not_awaited()
        self.assertFalse(player.is_autoplay_enabled())

    async def test_recommendations_check_csrf_membership_and_current_track(self):
        player = self.manager.get(100)
        seed = player._current = Track("https://youtu.be/seed0000001", "Seed", "Member")
        player.get_autoplay_candidates = AsyncMock(return_value=[])
        for track_id in (None, 123, "bad", "old-track-123"):
            response = await self.client.post(
                "/api/guilds/100/recommendations",
                json={"track_id": track_id},
                headers=self.headers(),
            )
            self.assertEqual(
                response.status, 409 if track_id == "old-track-123" else 400
            )
        for headers in (
            self.headers(Origin="https://evil.example"),
            self.headers(**{"X-CSRF-Token": "bad"}),
        ):
            response = await self.client.post(
                "/api/guilds/100/recommendations",
                json={"track_id": seed.queue_id},
                headers=headers,
            )
            self.assertEqual(response.status, 403)
        response = await self.client.post(
            "/api/guilds/200/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 403)
        self.permissions.view_channel = False
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 403)
        self.client.session.cookie_jar.clear()
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 401)
        player.get_autoplay_candidates.assert_not_awaited()

    async def test_recommendations_reject_membership_or_track_changes_during_lookup(
        self,
    ):
        player = self.manager.get(100)
        seed = Track("https://youtu.be/seed0000001", "Seed", "Member")
        for revoke in (False, True):
            player._current = seed

            async def change(track, *, revoke=revoke):
                if revoke:
                    self.guild.fetch_member.side_effect = self.not_member
                else:
                    player._current = Track(
                        "https://youtu.be/other000001", "Other", "Member"
                    )
                return [RadioTrack("next0000001", "stale")]

            player.get_autoplay_candidates = AsyncMock(side_effect=change)
            response = await self.client.post(
                "/api/guilds/100/recommendations",
                json={"track_id": seed.queue_id},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 403 if revoke else 409)
            self.assertNotIn("stale", await response.text())

    async def test_same_track_recommendation_requests_share_work_and_can_retry_failure(
        self,
    ):
        player = self.manager.get(100)
        seed = player._current = Track("https://youtu.be/seed0000001", "Seed", "Member")
        started, release = asyncio.Event(), asyncio.Event()

        async def slow(track):
            started.set()
            await release.wait()
            return []

        player.get_autoplay_candidates = AsyncMock(side_effect=slow)
        requests = [
            asyncio.create_task(
                self.client.post(
                    "/api/guilds/100/recommendations",
                    json={"track_id": seed.queue_id},
                    headers=self.headers(),
                )
            )
            for _ in range(2)
        ]
        await started.wait()
        await asyncio.sleep(0.01)
        release.set()
        responses = await asyncio.gather(*requests)
        self.assertEqual([response.status for response in responses], [200, 200])
        player.get_autoplay_candidates.assert_awaited_once()
        player.get_autoplay_candidates.side_effect = RecommendationError("offline")
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 502)
        player.get_autoplay_candidates.side_effect = None
        player.get_autoplay_candidates.return_value = []
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.server.recommendation_lookups, {})

    async def test_recommendations_share_lookup_capacity_and_rate_limit(self):
        player = self.manager.get(100)
        seed = player._current = Track("https://youtu.be/seed0000001", "Seed", "Member")
        player.get_autoplay_candidates = AsyncMock(return_value=[])
        self.server.searches = {object() for _ in range(4)}
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 429)
        self.server.searches.clear()
        player.get_autoplay_candidates.assert_not_awaited()
        for _ in range(19):
            response = await self.client.post(
                "/api/guilds/100/recommendations",
                json={"track_id": seed.queue_id},
                headers=self.headers(),
            )
            self.assertEqual(response.status, 200)
        response = await self.client.post(
            "/api/guilds/100/recommendations",
            json={"track_id": seed.queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 429)

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

    async def test_requester_avatars_use_cache_without_per_track_member_fetches(self):
        avatar = "https://cdn.discordapp.com/avatars/1/avatar.webp?size=64"
        self.member.display_avatar = Mock()
        self.member.display_avatar.with_size.return_value.url = avatar
        player = self.manager.get(100)
        player._current = Track("url", "current", "Member", requester_id=1)
        for i in range(50):
            player._queue.enqueue(Track(str(i), str(i), "Member", requester_id=1))
        response = await self.client.get("/api/guilds/100/state")
        data = await response.json()
        self.assertEqual(data["current"]["requester_avatar"], avatar)
        self.assertTrue(all(t["requester_avatar"] == avatar for t in data["queue"]))
        self.guild.fetch_member.assert_awaited_once()  # Only the signed-in member.
        self.guild.get_member = lambda uid: None
        player._current.requester_avatar = avatar
        response = await self.client.get("/api/guilds/100/state")
        self.assertEqual((await response.json())["current"]["requester_avatar"], avatar)

    async def test_bootstrap_returns_authorized_initial_state_in_one_response(self):
        response = await self.client.get("/api/bootstrap?guild_id=100")
        self.assertEqual(response.status, 200)
        data = await response.json()
        self.assertEqual(data["user"]["id"], "1")
        self.assertEqual(data["csrf"], self.csrf)
        self.assertEqual(data["guild_id"], "100")
        self.assertEqual(data["state"]["guild"]["id"], "100")
        self.assertNotIn("private-access", str(data))
        response = await self.client.get("/api/bootstrap?guild_id=200")
        self.assertEqual((await response.json())["guild_id"], "100")

    async def test_bootstrap_does_not_expose_private_voice_queue(self):
        self.permissions.view_channel = False
        self.manager.get(100)._current = Track("private", "secret title", "private")
        response = await self.client.get("/api/bootstrap")
        data = await response.json()
        self.assertEqual(response.status, 200)
        self.assertIsNone(data["state"])
        self.assertNotIn("secret title", str(data))

    async def test_cache_is_enabled_only_for_public_static_assets(self):
        root = Path(self.tmp.name) / "static"
        (root / "assets").mkdir(parents=True)
        (root / "index.html").write_text("<html>test</html>")
        (root / "assets/app-abcdef12.js").write_text("console.log('test')")
        object.__setattr__(self.config, "static_dir", root)
        response = await self.client.get("/assets/app-abcdef12.js")
        self.assertEqual(
            response.headers["Cache-Control"], "public, max-age=31536000, immutable"
        )
        response = await self.client.get("/")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        response = await self.client.get("/api/bootstrap")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("app;dur=", response.headers["Server-Timing"])

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
        self.assertEqual(response.status, 200)
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
        self.assertEqual(first.status, 200)
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

    async def test_volume_applies_synchronously_even_with_pending_request(self):
        self.server.jobs["pending"] = {
            "status": "running",
            "owner": "1",
            "guild": "100",
        }
        response = await self.client.put(
            "/api/guilds/100/volume", json={"volume": 72}, headers=self.headers()
        )
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["volume"], 72)
        self.assertEqual(self.manager.get(100).get_volume_percent(), 72)
        for value in (True, "50", 0, 101):
            response = await self.client.put(
                "/api/guilds/100/volume", json={"volume": value}, headers=self.headers()
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

    async def test_nightcore_revalidates_csrf_voice_and_membership_without_restarting_audio(self):
        self.voice.stop, self.voice.play = Mock(), Mock()
        with patch("bot.music.guild_player.nightcore_available", return_value=True):
            response = await self.client.put("/api/guilds/100/nightcore", json={"enabled": True}, headers=self.headers())
            self.assertEqual(response.status, 200)
            self.assertTrue((await response.json())["nightcore"]["enabled"])
            for value in (1, None, "true"):
                response = await self.client.put("/api/guilds/100/nightcore", json={"enabled": value}, headers=self.headers())
                self.assertEqual(response.status, 400)
            response = await self.client.put("/api/guilds/100/nightcore", json={"enabled": False}, headers=self.headers(**{"X-CSRF-Token": "wrong"}))
            self.assertEqual(response.status, 403)
            self.member.voice = None
            response = await self.client.put("/api/guilds/100/nightcore", json={"enabled": False}, headers=self.headers())
            self.assertEqual(response.status, 400)
            self.guild.fetch_member.side_effect = self.not_member
            response = await self.client.put("/api/guilds/100/nightcore", json={"enabled": False}, headers=self.headers())
            self.assertEqual(response.status, 403)
        self.voice.stop.assert_not_called()
        self.voice.play.assert_not_called()

    async def test_live_spatial_updates_bound_member_fetches_and_recheck_voice_and_session(self):
        payload = {"enabled": False, "x": 1, "y": 1.5, "z": 0}
        self.voice.stop = Mock()
        for _ in range(12):
            response = await self.client.put(
                "/api/guilds/100/spatial", json=payload, headers=self.headers()
            )
            self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["spatial"]["x"], 1)
        self.guild.fetch_member.assert_awaited_once()
        self.voice.stop.assert_not_called()
        self.member.voice = None
        response = await self.client.put(
            "/api/guilds/100/spatial", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 400)
        self.client.session.cookie_jar.clear()
        response = await self.client.put(
            "/api/guilds/100/spatial", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 401)

    async def test_spatial_rechecks_membership_after_two_seconds_and_rejects_csrf(self):
        payload = {"enabled": False, "x": 0, "y": 1.5, "z": 0}
        response = await self.client.put(
            "/api/guilds/100/spatial", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 200)
        for key, (_, guild, member) in self.server.spatial_permissions.items():
            self.server.spatial_permissions[key] = (0, guild, member)
        self.guild.fetch_member.side_effect = self.not_member
        response = await self.client.put(
            "/api/guilds/100/spatial", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 403)
        self.assertEqual(self.guild.fetch_member.await_count, 2)
        response = await self.client.put(
            "/api/guilds/100/spatial", json=payload,
            headers=self.headers(**{"X-CSRF-Token": "bad"})
        )
        self.assertEqual(response.status, 403)

    async def test_seek_endpoint_checks_track_position_same_voice_and_csrf(self):
        player = self.manager.get(100)
        track = Track("https://youtube.com/watch?v=12345678901", "song", "Member")
        player._current = track
        player._duration = 120
        self.voice.stop = Mock()
        payload = {"track_id": track.queue_id, "position": 45}
        response = await self.client.put(
            "/api/guilds/100/seek", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["progress"]["position"], 45)
        response = await self.client.put(
            "/api/guilds/100/seek",
            json={**payload, "track_id": "old-track"},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 400)
        response = await self.client.put(
            "/api/guilds/100/seek",
            json={**payload, "position": 121},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 400)
        response = await self.client.put(
            "/api/guilds/100/seek",
            json=payload,
            headers=self.headers(**{"X-CSRF-Token": "bad"}),
        )
        self.assertEqual(response.status, 403)
        self.member.voice = None
        response = await self.client.put(
            "/api/guilds/100/seek", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 400)

    async def test_queue_api_serializes_ids_thumbnails_and_removes_only_requested_entry(
        self,
    ):
        player = self.manager.get(100)
        tracks = [
            Track("https://youtube.com/watch?v=12345678901", "same", "Member")
            for _ in range(2)
        ]
        for track in tracks:
            player._queue.enqueue(track)
        response = await self.client.get("/api/guilds/100/state")
        queue = (await response.json())["queue"]
        self.assertEqual(queue[0]["video_id"], "12345678901")
        self.assertNotEqual(queue[0]["id"], queue[1]["id"])
        response = await self.client.put(
            "/api/guilds/100/queue",
            json={"action": "queue_remove", "id": tracks[1].queue_id},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            [t["id"] for t in (await response.json())["queue"]], [tracks[0].queue_id]
        )

    async def test_queue_edit_validates_permissions_csrf_and_stale_ids(self):
        player = self.manager.get(100)
        first, second = Track("1", "1", "Member"), Track("2", "2", "Member")
        player._queue.enqueue(first)
        player._queue.enqueue(second)
        payload = {
            "action": "queue_move",
            "id": second.queue_id,
            "before_id": first.queue_id,
        }
        response = await self.client.put(
            "/api/guilds/100/queue", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(player._queue.peek_all(), [second, first])
        response = await self.client.put(
            "/api/guilds/100/queue",
            json={**payload, "before_id": "missing"},
            headers=self.headers(),
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(player._queue.peek_all(), [second, first])
        response = await self.client.put(
            "/api/guilds/100/queue",
            json=payload,
            headers=self.headers(**{"X-CSRF-Token": "bad"}),
        )
        self.assertEqual(response.status, 403)
        self.member.voice = None
        response = await self.client.put(
            "/api/guilds/100/queue", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 400)
        response = await self.client.put(
            "/api/guilds/200/queue", json=payload, headers=self.headers()
        )
        self.assertEqual(response.status, 403)


if __name__ == "__main__":
    unittest.main()
