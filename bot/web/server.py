"""同一イベントループ上で Bot を操作する認証付き HTTP サーバー。"""

import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlencode, urlsplit

import aiohttp
import discord
from aiohttp import web

from bot.music.control import ControlError
from bot.music.models import Track, requester_avatar_url
from bot.music.spatial import SpatialPosition, SpatialTarget, spatial_state
from bot.youtube import SearchError
from bot.youtube.playlist import PlaylistTarget, playlist_id, resolve_play_request
from bot.youtube.recommendations import youtube_video_id
from bot.youtube.workers import search_workers

from .store import WebStore, digest

logger = logging.getLogger(__name__)
DISCORD_API = "https://discord.com/api/v10"
COOKIE = "music_session"
STATE_COOKIE = "music_oauth_state"
ID = re.compile(r"^[0-9]{1,22}$")
REQUEST_ID = re.compile(r"^[a-zA-Z0-9_-]{8,100}$")


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class WebServer:
    def __init__(self, bot, control, download_service, config):
        self.bot, self.control, self.download_service, self.config = (
            bot,
            control,
            download_service,
            config,
        )
        self.store = WebStore(config.database, config.encryption_key)
        self.jobs = {}
        self.previews = {}
        self.tasks = set()
        self.memberships = {}
        self.spatial_permissions = {}
        self.guild_lists = {}
        self.refresh_locks = defaultdict(asyncio.Lock)
        self.limits = {}
        self.searches = set()
        self.runner = None
        self.http = None

    def limited(self, key, maximum, seconds):
        now = time.monotonic()
        if len(self.limits) > 5000:
            self.limits = {
                k: v for k, v in self.limits.items() if v and now - v[-1] < 3600
            }
        hits = self.limits.setdefault(key, deque())
        while hits and now - hits[0] >= seconds:
            hits.popleft()
        if len(hits) >= maximum:
            raise APIError(429, "操作が続いています。少し待ってからお試しください。")
        hits.append(now)

    @web.middleware
    async def middleware(self, request, handler):
        started = time.monotonic()
        try:
            # 転送ヘッダーを認証やリダイレクト先の決定に使用しない。
            if (
                request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get("Origin") != self.config.public_url
            ):
                raise APIError(
                    403, "操作元を確認できませんでした。ページを開き直してください。"
                )
            response = await handler(request)
        except APIError as error:
            response = web.json_response({"error": error.message}, status=error.status)
        except ControlError as error:
            response = web.json_response({"error": str(error)}, status=400)
        except (TimeoutError, aiohttp.ClientError):
            response = web.json_response(
                {"error": "接続が不安定です。時間をおいてお試しください。"}, status=503
            )
        except web.HTTPException as error:
            response = error
        except Exception:
            logger.exception("Web request failed: %s %s", request.method, request.path)
            response = web.json_response(
                {"error": "処理に失敗しました。時間をおいてお試しください。"},
                status=500,
            )
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["Server-Timing"] = (
            f"app;dur={(time.monotonic() - started) * 1000:.1f}"
        )
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://i.ytimg.com https://cdn.discordapp.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    def app(self):
        app = web.Application(middlewares=[self.middleware], client_max_size=16 * 1024)
        app.add_routes(
            [
                web.get("/healthz", self.health),
                web.get("/auth/login", self.login),
                web.get("/auth/callback", self.callback),
                web.post("/auth/logout", self.logout),
                web.get("/api/me", self.me),
                web.get("/api/bootstrap", self.bootstrap),
                web.get("/api/guilds", self.guilds),
                web.get("/api/guilds/{guild_id}/state", self.state),
                web.post("/api/guilds/{guild_id}/actions", self.action),
                web.put("/api/guilds/{guild_id}/queue", self.edit_queue),
                web.put("/api/guilds/{guild_id}/settings", self.settings),
                web.put("/api/guilds/{guild_id}/volume", self.volume),
                web.put("/api/guilds/{guild_id}/seek", self.seek),
                web.put("/api/guilds/{guild_id}/spatial", self.spatial),
                web.get("/api/guilds/{guild_id}/jobs/{job_id}", self.job),
                web.get("/{path:.*}", self.static),
            ]
        )
        app.cleanup_ctx.append(self.lifecycle)
        return app

    async def lifecycle(self, app):
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as http:
            self.http = http
            activity = asyncio.create_task(self.report_activity())
            yield
            activity.cancel()
            await asyncio.gather(activity, return_exceptions=True)
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.store.close()

    async def report_activity(self):
        target = self.config.database.parent / "activity.json"
        while True:
            try:
                data = {
                    "at": time.time(),
                    "jobs": sum(j["status"] == "running" for j in self.jobs.values()),
                    "voice": sum(
                        bool(g.voice_client and g.voice_client.is_connected())
                        for g in self.bot.guilds
                    ),
                    "audio": {
                        str(guild_id): {
                            "frames": monitor.frames_read,
                            "late_reads": monitor.late_reads,
                            "max_gap_ms": round(monitor.max_gap_ms, 1),
                            "packet_clock": {
                                "packets": player._packet_pacer.packets,
                                "min_gap_ms": round(
                                    player._packet_pacer.min_gap_ms or 0, 2
                                ),
                                "max_gap_ms": round(player._packet_pacer.max_gap_ms, 2),
                                "errors": player._packet_pacer.errors,
                                "timestamp_corrections": (
                                    player._packet_pacer.timestamp_corrections
                                ),
                                "skipped_frames": player._packet_pacer.skipped_frames,
                            }
                            if player._packet_pacer
                            else None,
                        }
                        for guild_id in self.control.manager.get_all_guild_ids()
                        if (player := self.control.manager.get_existing(guild_id))
                        is not None
                        and (monitor := player._audio_monitor) is not None
                    },
                }
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(data), encoding="utf-8")
                os.chmod(temporary, 0o600)
                temporary.replace(target)
            except OSError:
                logger.exception("Could not write private activity status")
            await asyncio.sleep(2)

    async def start(self):
        self.runner = web.AppRunner(self.app(), access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.config.host, self.config.port).start()
        logger.info("Web control listening on port %s", self.config.port)

    async def close(self):
        if self.runner:
            await self.runner.cleanup()

    def cookie(self, response, name, value, seconds):
        response.set_cookie(
            name,
            value,
            max_age=seconds,
            httponly=True,
            secure=self.config.secure_cookie,
            samesite="Lax",
            path="/",
        )

    async def health(self, request):
        ready = self.bot.is_ready() and not self.bot.is_closed()
        return web.json_response({"ready": ready}, status=200 if ready else 503)

    async def login(self, request):
        self.limited(("login", request.remote), 20, 60)
        state = self.store.new_state()
        response = web.Response(
            status=302,
            headers={
                "Location": "https://discord.com/oauth2/authorize?"
                + urlencode(
                    {
                        "client_id": self.config.client_id,
                        "redirect_uri": self.config.redirect_uri,
                        "response_type": "code",
                        "scope": "identify guilds",
                        "state": state,
                    }
                )
            },
        )
        self.cookie(response, STATE_COOKIE, state, 600)
        return response

    async def token(self, data):
        async with self.http.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                **data,
            },
        ) as response:
            if response.status in (400, 401):
                raise APIError(
                    401,
                    "ログインの有効期限が切れました。Discordでログインし直してください。",
                )
            if response.status != 200:
                raise APIError(503, "Discord認証に接続できませんでした。")
            return await response.json()

    async def discord(self, token, path):
        async with self.http.get(
            DISCORD_API + path, headers={"Authorization": "Bearer " + token}
        ) as response:
            if response.status == 401:
                raise APIError(401, "Discordでログインし直してください。")
            if response.status in (403, 404):
                raise APIError(403, "このDiscordサーバーを利用する権限がありません。")
            if response.status != 200:
                raise APIError(
                    503, "Discordへの問い合わせが混み合っています。少し待ってください。"
                )
            return await response.json()

    async def callback(self, request):
        state = request.query.get("state", "")
        expected = request.cookies.get(STATE_COOKIE, "")
        if (
            not state
            or not expected
            or not hmac.compare_digest(state, expected)
            or not self.store.consume_state(state)
        ):
            raise APIError(
                400, "ログインの確認に失敗しました。最初からやり直してください。"
            )
        if request.query.get("error") or not request.query.get("code"):
            return web.Response(status=302, headers={"Location": "/?login=cancelled"})
        tokens = await self.token(
            {
                "grant_type": "authorization_code",
                "code": request.query["code"],
                "redirect_uri": self.config.redirect_uri,
            }
        )
        user = await self.discord(tokens["access_token"], "/users/@me")
        session = self.store.create_session(
            {
                "user": {
                    k: user.get(k) for k in ("id", "username", "global_name", "avatar")
                },
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_expires": time.time() + tokens["expires_in"],
            },
            self.config.session_seconds,
        )
        old = request.cookies.get(COOKIE)
        if old:
            self.store.delete_session(old)
        response = web.Response(status=302, headers={"Location": "/"})
        self.cookie(response, COOKIE, session, self.config.session_seconds)
        response.del_cookie(STATE_COOKIE, path="/")
        return response

    async def session(self, request, *, write=False):
        cookie = request.cookies.get(COOKIE, "")
        if not cookie or len(cookie) > 100:
            raise APIError(401, "Discordでログインしてください。")
        stored = self.store.session(cookie)
        if not stored:
            raise APIError(401, "Discordでログインしてください。")
        data, expires = stored
        if write and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), data["csrf"]
        ):
            raise APIError(
                403, "操作の確認に失敗しました。ページを開き直してください。"
            )
        if data["token_expires"] < time.time() + 60:
            async with self.refresh_locks[digest(cookie)]:
                stored = self.store.session(cookie)
                if not stored:
                    raise APIError(401, "Discordでログインしてください。")
                data, expires = stored
                if data["token_expires"] < time.time() + 60:
                    try:
                        tokens = await self.token(
                            {
                                "grant_type": "refresh_token",
                                "refresh_token": data["refresh_token"],
                            }
                        )
                    except APIError as error:
                        if error.status == 401:
                            self.store.delete_session(cookie)
                        raise
                    data.update(
                        access_token=tokens["access_token"],
                        refresh_token=tokens["refresh_token"],
                        token_expires=time.time() + tokens["expires_in"],
                    )
                    if self.store.session(cookie) is None:
                        raise APIError(401, "Discordでログインしてください。")
                    self.store.save_session(cookie, data, expires)
        return data

    async def logout(self, request):
        await self.session(request, write=True)
        self.store.delete_session(request.cookies[COOKIE])
        response = web.json_response({"ok": True})
        response.del_cookie(COOKIE, path="/")
        return response

    async def me(self, request):
        data = await self.session(request)
        return web.json_response({"user": data["user"], "csrf": data["csrf"]})

    async def guilds(self, request):
        data = await self.session(request)
        self.limited(("guilds", data["user"]["id"]), 10, 60)
        return web.json_response({"guilds": await self.guild_list(data)})

    async def guild_list(self, data):
        user_id = data["user"]["id"]
        cached = self.guild_lists.get(user_id)
        if cached and cached[0] > time.monotonic():
            guilds = cached[1]
        else:
            guilds = await self.discord(data["access_token"], "/users/@me/guilds")
            self.guild_lists = {
                k: v for k, v in self.guild_lists.items() if v[0] > time.monotonic()
            }
            self.guild_lists[user_id] = (time.monotonic() + 60, guilds)
        return [
            {"id": g["id"], "name": g["name"], "icon": g["icon"]}
            for g in guilds
            if self.bot.get_guild(int(g["id"]))
        ]

    async def bootstrap(self, request):
        data = await self.session(request)
        self.limited(("bootstrap", data["user"]["id"]), 10, 60)
        guilds = await self.guild_list(data)
        preferred = request.query.get("guild_id")
        selected = (
            preferred
            if any(g["id"] == preferred for g in guilds)
            else (guilds[0]["id"] if guilds else "")
        )
        state = None
        if selected:
            try:
                _, guild, member = await self.authorize_guild(data, selected)
                state = self.state_data(data, guild, member)
            except APIError as error:
                if error.status != 403:
                    raise
        return web.json_response(
            {
                "user": data["user"],
                "csrf": data["csrf"],
                "guilds": guilds,
                "guild_id": selected,
                "state": state,
            }
        )

    async def authorized(self, request, *, write=False, fresh=False):
        data = await self.session(request, write=write)
        return await self.authorize_guild(
            data, request.match_info["guild_id"], write=write, fresh=fresh
        )

    async def authorize_guild(self, data, guild_id, *, write=False, fresh=False):
        if (write or fresh) and not self.bot.is_ready():
            raise APIError(503, "Discordに再接続しています。少し待ってください。")
        if not ID.fullmatch(guild_id):
            raise APIError(404, "サーバーが見つかりません。")
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            raise APIError(403, "Botが参加しているサーバーを選んでください。")
        key = (data["user"]["id"], guild_id)
        if len(self.memberships) > 1000:
            self.memberships = {
                k: cached
                for k, cached in self.memberships.items()
                if cached[0] > time.monotonic()
            }
        cached = self.memberships.get(key)
        if write or fresh or cached is None or cached[0] < time.monotonic():
            # 所属・ロールはBotのGet Guild Memberで確認する。
            # OAuthのguilds.members.readには定期ポーリング向けの余裕がない。
            self.memberships.pop(key, None)
            try:
                member = await guild.fetch_member(int(data["user"]["id"]))
            except (discord.NotFound, discord.Forbidden):
                raise APIError(403, "このサーバーを利用する権限がありません。")
            self.memberships[key] = (time.monotonic() + 15, member)
        else:
            member = cached[1]
        voice = guild.voice_client
        if (
            voice
            and voice.is_connected()
            and not voice.channel.permissions_for(member).view_channel
        ):
            raise APIError(403, "再生中のVCを閲覧する権限がありません。")
        return data, guild, member

    def channels(self, guild, member):
        return [
            {"id": str(c.id), "name": c.name}
            for c in guild.text_channels
            if c.permissions_for(member).view_channel
            and c.permissions_for(member).send_messages
            and c.permissions_for(guild.me).view_channel
            and c.permissions_for(guild.me).send_messages
        ]

    def notification_channel(self, guild, member, *, attachment=False):
        channel_id = self.store.channel(guild.id)
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise ControlError(
                "サーバー管理者に通知先チャンネルを設定してもらってください。"
            )
        user_perms, bot_perms = (
            channel.permissions_for(member),
            channel.permissions_for(guild.me),
        )
        if (
            not user_perms.view_channel
            or not user_perms.send_messages
            or not bot_perms.view_channel
            or not bot_perms.send_messages
            or not bot_perms.embed_links
        ):
            raise ControlError("通知先チャンネルへの閲覧・送信権限を確認してください。")
        if attachment and not bot_perms.attach_files:
            raise ControlError("Botに通知先へのファイル添付権限がありません。")
        return channel

    async def state(self, request):
        data, guild, member = await self.authorized(request)
        self.limited(("state", data["user"]["id"]), 90, 60)
        return web.json_response(self.state_data(data, guild, member))

    def state_data(self, data, guild, member):
        player = self.control.manager.get_existing(guild.id)
        snap = (
            player.get_queue_snapshot()
            if player
            else {"current": None, "queue": [], "loop": False, "autoplay": False}
        )
        voice = guild.voice_client
        try:
            self.control.authorize(guild, member, starting=True)
            can_control, reason = True, ""
        except ControlError as error:
            can_control, reason = False, str(error)

        def track(t):
            return (
                {
                    "title": t.title,
                    "url": t.url,
                    "requester": t.requester,
                    "requester_avatar": (
                        requester_avatar_url(guild.get_member(t.requester_id))
                        if t.requester_id is not None
                        else None
                    ) or t.requester_avatar,
                    "id": t.queue_id,
                    "video_id": t.video_id or youtube_video_id(t.url),
                    "auto_selected": t.auto_selected,
                }
                if t
                else None
            )

        return {
            "guild": {"id": str(guild.id), "name": guild.name},
            "current": track(snap["current"]),
            "queue": [track(t) for t in snap["queue"]],
            "loop": snap["loop"],
            "autoplay": snap["autoplay"],
            "volume": player.get_volume_percent()
            if player
            else self.control.manager.default_volume,
            "voice_channel": voice.channel.name
            if voice and voice.is_connected()
            else None,
            "paused": bool(voice and voice.is_paused()),
            "playback_status": player.get_playback_status(voice) if player else "idle",
            "playback_error": player._last_error if player else None,
            "progress": player.get_progress()
            if player
            else {"position": 0, "duration": None, "seekable": False},
            "spatial": player.get_spatial()
            if player
            else spatial_state(SpatialTarget(SpatialPosition())),
            "connected": self.bot.is_ready(),
            "can_control": can_control,
            "control_reason": reason,
            "can_manage": member.guild_permissions.manage_guild,
            "notification_channel_id": self.store.channel(guild.id),
            "channels": self.channels(guild, member),
            "jobs": [
                self.public_job(j)
                for j in self.jobs.values()
                if j["owner"] == data["user"]["id"]
                and j["guild"] == str(guild.id)
                and time.time() - j["created"] < 600
            ],
        }

    async def body(self, request):
        try:
            data = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "入力形式が不正です。")
        if not isinstance(data, dict):
            raise APIError(400, "入力形式が不正です。")
        return data

    async def settings(self, request):
        _, guild, member = await self.authorized(request, write=True)
        if not member.guild_permissions.manage_guild:
            raise APIError(403, "サーバー管理権限が必要です。")
        data = await self.body(request)
        channel_id = str(data.get("channel_id", ""))
        if not ID.fullmatch(channel_id) or channel_id not in {
            c["id"] for c in self.channels(guild, member)
        }:
            raise APIError(400, "通知先チャンネルを選んでください。")
        channel = guild.get_channel(int(channel_id))
        if not channel.permissions_for(guild.me).embed_links:
            raise APIError(400, "Botに埋め込みリンクの権限が必要です。")
        self.store.set_channel(guild.id, channel_id)
        return web.json_response({"ok": True})

    async def seek(self, request):
        data, guild, member = await self.authorized(request, write=True)
        self.limited(("seek", data["user"]["id"]), 40, 60)
        body = await self.body(request)
        progress = await self.control.apply(guild, member, "seek", value=body)
        return web.json_response({"track_id": body["track_id"], "progress": progress})

    async def volume(self, request):
        data, guild, member = await self.authorized(request, write=True)
        self.limited(("volume", data["user"]["id"]), 80, 60)
        body = await self.body(request)
        value = await self.control.apply(
            guild, member, "volume", value=body.get("volume")
        )
        return web.json_response({"volume": value})

    async def spatial(self, request):
        # A short control session avoids a Discord REST call for every pointer
        # move. Cookie, CSRF and Origin are checked on every update. Membership
        # and roles are re-fetched at least every 2 s; live VC state and channel
        # permissions are checked on EVERY apply(), including mid-drag moves.
        data = await self.session(request, write=True)
        guild_id = request.match_info["guild_id"]
        key = (digest(request.cookies[COOKIE]), guild_id)
        self.limited(("spatial", data["user"]["id"]), 720, 60)
        cached = self.spatial_permissions.get(key)
        if cached is None or cached[0] <= time.monotonic():
            _, guild, member = await self.authorize_guild(data, guild_id, write=True)
            self.spatial_permissions = {
                k: v for k, v in self.spatial_permissions.items()
                if v[0] > time.monotonic()
            }
            self.spatial_permissions[key] = (time.monotonic() + 2, guild, member)
        else:
            if not self.bot.is_ready():
                raise APIError(503, "Discordに再接続しています。少し待ってください。")
            _, guild, member = cached
            if self.bot.get_guild(guild.id) is not guild:
                raise APIError(403, "このサーバーを利用する権限がありません。")
        value = await self.control.apply(
            guild, member, "spatial", value=await self.body(request)
        )
        return web.json_response({"spatial": value})

    def public_job(self, job):
        result = {k: job[k] for k in ("id", "status", "message", "action")}
        if "preview" in job:
            result["preview"] = job["preview"]
        return result

    def preview(self, preview_id, owner, guild_id):
        result = self.previews.get(preview_id) if isinstance(preview_id, str) else None
        if (
            not result
            or result["owner"] != owner
            or result["guild"] != str(guild_id)
            or result["expires"] < time.monotonic()
        ):
            raise APIError(
                400,
                "再生リストをもう一度確認してください。確認画面の有効期限は5分です。",
            )
        return result

    async def edit_queue(self, request):
        data, guild, member = await self.authorized(request, write=True)
        self.limited(("queue", data["user"]["id"]), 60, 60)
        body = await self.body(request)
        if body.get("action") not in ("queue_remove", "queue_move"):
            raise APIError(400, "キューの操作が不正です。")
        try:
            await self.control.apply(guild, member, body["action"], value=body)
        except ControlError as error:
            raise APIError(400, str(error)) from error
        return await self.state(request)

    async def action(self, request):
        data, guild, member = await self.authorized(request, write=True)
        body = await self.body(request)
        action = body.get("action")
        if not isinstance(action, str):
            raise APIError(400, "操作を選択してください。")
        if action not in {
            "play",
            "playlist_preview",
            "pause",
            "resume",
            "skip",
            "stop",
            "clear",
            "loop",
            "autoplay",
            "volume",
            "download",
            "download_mp3",
        }:
            raise APIError(400, "対応していない操作です。")
        self.limited(("action", data["user"]["id"]), 30, 60)
        self.control.authorize(
            guild,
            member,
            starting=action in ("play", "playlist_preview", "download", "download_mp3"),
        )
        request_id = request.headers.get("X-Request-ID", "")
        if not REQUEST_ID.fullmatch(request_id):
            raise APIError(400, "操作IDがありません。ページを開き直してください。")
        self.jobs = {
            k: j
            for k, j in self.jobs.items()
            if j["status"] == "running" or time.time() - j["created"] < 3600
        }
        key = (data["user"]["id"], str(guild.id), request_id)
        old = self.jobs.get(key)
        if old:
            return web.json_response(self.public_job(old), status=202)
        long_operation = action in (
            "play",
            "playlist_preview",
            "download",
            "download_mp3",
        )
        if long_operation and (
            sum(j["status"] == "running" for j in self.jobs.values()) >= 8
            or any(
                j["owner"] == data["user"]["id"] and j["status"] == "running"
                for j in self.jobs.values()
            )
        ):
            raise APIError(429, "前の操作の完了をお待ちください。")
        if action in ("play", "playlist_preview", "download", "download_mp3"):
            query = body.get("query", "")
            if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
                raise APIError(
                    400, "曲名またはYouTube URLを500文字以内で入力してください。"
                )
            if action in ("download", "download_mp3"):
                self.validate_download(query, body.get("quality", "480p"))
            elif (
                "://" in query
                or "youtube.com" in query.lower()
                or "youtu.be" in query.lower()
            ):
                candidate = query if "://" in query else "https://" + query
                self.validate_download(candidate, "480p", allow_playlist=True)
                body["query"] = candidate
            self.notification_channel(
                guild, member, attachment=action in ("download", "download_mp3")
            )
            if action == "playlist_preview" and not playlist_id(body["query"]):
                raise APIError(400, "YouTube再生リストのURLを入力してください。")
            if action == "play" and playlist_id(body["query"]):
                preview = self.preview(
                    body.get("preview_id"), data["user"]["id"], guild.id
                )
                count = body.get("count")
                if type(count) is not int or not 1 <= count <= min(
                    50, len(preview["target"].tracks)
                ):
                    raise APIError(400, "取り込む曲数を1〜50曲の範囲で選んでください。")
                if playlist_id(body["query"]) != playlist_id(preview["target"].url):
                    raise APIError(
                        400, "再生リストが変更されています。もう一度確認してください。"
                    )
        job = {
            "id": secrets.token_urlsafe(16),
            "owner": data["user"]["id"],
            "guild": str(guild.id),
            "action": action,
            "status": "running",
            "message": "処理しています…",
            "created": time.time(),
        }
        self.jobs[key] = job
        if not long_operation:
            await self.perform(request, body, job)
            return web.json_response(self.public_job(job))
        task = asyncio.create_task(self.perform(request, body, job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return web.json_response(self.public_job(job), status=202)

    def validate_download(self, query, quality, *, allow_playlist=False):
        try:
            url = urlsplit(query)
            valid = (
                url.scheme == "https"
                and url.hostname
                in {
                    "youtube.com",
                    "www.youtube.com",
                    "m.youtube.com",
                    "music.youtube.com",
                    "youtu.be",
                }
                and not url.username
                and url.port in (None, 443)
                and (
                    url.path == "/watch"
                    or (allow_playlist and url.path == "/playlist")
                    or url.path.startswith(("/shorts/", "/embed/"))
                    or url.hostname == "youtu.be"
                )
                and (allow_playlist or "list=" not in url.query)
            )
        except ValueError:
            valid = False
        if not valid:
            raise APIError(
                400, "プレイリストを含まないYouTube動画のHTTPS URLを入力してください。"
            )
        if not isinstance(quality, str) or quality not in {
            "144p",
            "240p",
            "360p",
            "480p",
            "720p",
            "1080p",
        }:
            raise APIError(400, "画質を選び直してください。")

    async def resolve(self, query):
        if len(self.searches) >= 4:
            raise ControlError("曲の検索が混み合っています。少し待ってください。")
        future = asyncio.create_task(search_workers.run(resolve_play_request, query))
        self.searches.add(future)

        def done(task):
            self.searches.discard(task)
            if not task.cancelled():
                task.exception()

        future.add_done_callback(done)
        return await asyncio.wait_for(asyncio.shield(future), timeout=45)

    async def perform(self, request, body, job):
        try:
            action = body["action"]
            if action == "playlist_preview":
                target = await self.resolve(body["query"].strip())
                if not isinstance(target, PlaylistTarget):
                    raise ControlError("再生リストを確認できませんでした。")
                data, guild, member = await self.authorized(request, fresh=True)
                self.control.authorize(guild, member, starting=True)
                self.previews = {
                    k: p
                    for k, p in self.previews.items()
                    if p["expires"] > time.monotonic() and p["owner"] != job["owner"]
                }
                token = secrets.token_urlsafe(24)
                self.previews[token] = {
                    "owner": data["user"]["id"],
                    "guild": str(guild.id),
                    "target": target,
                    "expires": time.monotonic() + 300,
                }
                player = self.control.manager.get_existing(guild.id)
                available = self.control.max_queue - (
                    len(player.get_queue_snapshot()["queue"]) if player else 0
                )
                maximum = min(50, len(target.tracks), available)
                if maximum <= 0:
                    raise ControlError(
                        "キューがいっぱいです。曲数を減らしてから追加してください。"
                    )
                job["preview"] = {
                    "id": token,
                    "query": target.url,
                    "title": target.display_title,
                    "maximum": maximum,
                    "available": len(target.tracks),
                    "skipped": target.skipped,
                    "truncated": target.truncated,
                    "tracks": [t.display_title for t in target.tracks[:3]],
                }
                message = "再生リストを確認しました。取り込む曲数を選んでください。"
            elif action == "play":
                if playlist_id(body["query"]):
                    preview = self.preview(
                        body.get("preview_id"), job["owner"], job["guild"]
                    )
                    target = preview["target"]
                else:
                    target = await self.resolve(body["query"].strip())
                # 検索中の退会・ログアウト・VC移動を再検証する。
                _, guild, member = await self.authorized(request, fresh=True)
                channel = self.notification_channel(guild, member)
                track = Track(
                    url=target.url,
                    title=target.display_title,
                    requester=member.display_name,
                    requester_id=member.id,
                    requester_avatar=requester_avatar_url(member),
                )
                if isinstance(target, PlaylistTarget):
                    self.previews.pop(body["preview_id"], None)
                    tracks = [
                        Track(
                            url=t.url,
                            title=t.display_title,
                            requester=member.display_name,
                            requester_id=member.id,
                            requester_avatar=requester_avatar_url(member),
                        )
                        for t in target.tracks[: body["count"]]
                    ]
                    await self.control.enqueue_many(
                        guild, member, tracks, channel_id=channel.id
                    )
                    message = (
                        f"「{target.display_title}」から{len(tracks)}曲を追加しました。"
                    )
                    if target.skipped:
                        message += f"取得できない{target.skipped}件をスキップしました。"
                else:
                    await self.control.enqueue(
                        guild, member, track, channel_id=channel.id
                    )
                    message = "「" + target.display_title + "」を追加しました。"
            elif action in ("download", "download_mp3"):

                async def send(response):
                    _, guild, member = await self.authorized(request, fresh=True)
                    self.control.authorize(guild, member, starting=True)
                    channel = self.notification_channel(guild, member, attachment=True)
                    if response.send_file and response.file_path:
                        if os.path.getsize(response.file_path) > guild.filesize_limit:
                            raise ControlError(
                                "このサーバーの添付サイズ上限を超えています。画質を下げてください。"
                            )
                        with discord.File(response.file_path) as file:
                            await channel.send(
                                embed=response.embed,
                                file=file,
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                    else:
                        raise ControlError(
                            response.embed.description or "ダウンロードに失敗しました。"
                        )

                await self.download_service.deliver(
                    body["query"],
                    "mp3" if action == "download_mp3" else "video",
                    body.get("quality", "480p"),
                    send,
                )
                message = "通知先チャンネルにファイルを送りました。"
            else:
                _, guild, member = await self.authorized(request, fresh=True)
                await self.control.apply(guild, member, action, value=body.get("value"))
                message = "操作を反映しました。"
            job.update(status="done", message=message)
        except (ControlError, SearchError, APIError) as error:
            job.update(
                status="error",
                message=error.message if isinstance(error, APIError) else str(error),
            )
        except TimeoutError:
            job.update(
                status="error",
                message="処理がタイムアウトしました。時間をおいてお試しください。",
            )
        except asyncio.CancelledError:
            job.update(status="error", message="再起動のため操作を中断しました。")
            raise
        except Exception:
            logger.exception("Web operation failed: %s", body.get("action"))
            job.update(
                status="error",
                message="処理に失敗しました。権限・接続状況をご確認ください。",
            )

    async def job(self, request):
        data, guild, _ = await self.authorized(request)
        for job in self.jobs.values():
            if (
                job["id"] == request.match_info["job_id"]
                and job["owner"] == data["user"]["id"]
                and job["guild"] == str(guild.id)
            ):
                return web.json_response(self.public_job(job))
        raise APIError(404, "操作が見つかりません。")

    async def static(self, request):
        relative = request.match_info["path"] or "index.html"
        root = self.config.static_dir.resolve()
        path = (root / relative).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or relative.startswith(("api/", "auth/"))
        ):
            raise web.HTTPNotFound()
        response = web.FileResponse(path)
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if relative.startswith("assets/")
            else "no-cache"
        )
        return response
