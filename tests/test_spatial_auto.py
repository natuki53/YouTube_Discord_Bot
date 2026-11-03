import asyncio
import math
import threading
import unittest
from unittest.mock import Mock, patch

from bot.music.guild_player import GuildPlayer
from bot.music.player_manager import PlayerManager
from bot.music.spatial import SpatialPosition, automatic_position, prepare_target


class SpatialTrajectoryTests(unittest.TestCase):
    def test_orbit_starts_at_current_position_and_reaches_all_directions(self):
        origin = SpatialPosition(True)
        self.assertEqual(automatic_position(origin, 0).x, origin.x)
        self.assertEqual(automatic_position(origin, 0).y, origin.y)
        self.assertAlmostEqual(automatic_position(origin, 5).x, 1.5)
        self.assertAlmostEqual(automatic_position(origin, 10).y, -1.5)
        self.assertAlmostEqual(automatic_position(origin, 15).x, -1.5)
        self.assertAlmostEqual(automatic_position(origin, 20).y, 1.5)
        self.assertGreater(automatic_position(origin, 10).z, 0.3)

    def test_initial_transition_and_bounds_remain_safe(self):
        origin = SpatialPosition(True, 4, -4, 2)
        near = automatic_position(origin, 0.001)
        self.assertLess(
            math.dist((origin.x, origin.y, origin.z), (near.x, near.y, near.z)), 0.001
        )
        for i in range(401):
            point = automatic_position(origin, i / 10)
            self.assertLessEqual(abs(point.x), 4)
            self.assertLessEqual(abs(point.y), 4)
            self.assertLessEqual(abs(point.z), 2)

    def test_auto_validation_and_disabled_normalization(self):
        body = {"enabled": True, "x": 0, "y": 1.5, "z": 0, "auto": True}
        self.assertTrue(SpatialPosition.parse(body).auto)
        self.assertFalse(SpatialPosition.parse({**body, "enabled": False}).auto)
        with self.assertRaises(ValueError):
            SpatialPosition.parse({**body, "auto": "true"})


class SpatialAutoRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_motion_continues_without_client_and_manual_edit_stops_it(
        self,
    ):
        player = GuildPlayer(1, Mock())
        player._spatial_source = Mock()
        try:
            await player.set_spatial(
                {"enabled": True, "x": 0, "y": 1.5, "z": 0, "auto": True}
            )
            task = player._spatial_auto_task
            await asyncio.sleep(0.17)
            self.assertGreater(player.get_spatial()["x"], 0)
            self.assertGreater(player.get_spatial()["motion"]["elapsed"], 0.1)
            await player.set_spatial(
                {"enabled": True, "x": -2, "y": 1, "z": 0, "auto": False}
            )
            await asyncio.sleep(0.13)
            self.assertEqual(player.get_spatial()["x"], -2)
            self.assertFalse(player.get_spatial()["auto"])
            self.assertIsNone(player.get_spatial()["motion"])
            self.assertTrue(task.done())
            self.assertEqual(player._spatial_source.target.position.x, -2)
        finally:
            player.cancel_spatial_auto()

    async def test_late_worker_result_cannot_overwrite_manual_position(self):
        player = GuildPlayer(1, Mock())
        started, release = threading.Event(), threading.Event()
        calls = 0

        def delayed(position):
            nonlocal calls
            calls += 1
            if calls == 2:
                started.set()
                release.wait(2)
            return prepare_target(position)

        try:
            with patch("bot.music.guild_player.prepare_target", side_effect=delayed):
                await player.set_spatial(
                    {"enabled": True, "x": 0, "y": 1.5, "z": 0, "auto": True}
                )
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                await player.set_spatial({"enabled": True, "x": 2, "y": 0, "z": 0})
                release.set()
                await asyncio.sleep(0.1)
                self.assertEqual(player.get_spatial()["x"], 2)
                self.assertFalse(player.get_spatial()["auto"])
        finally:
            release.set()
            player.cancel_spatial_auto()

    async def test_removing_player_cancels_automatic_movement(self):
        manager = PlayerManager(Mock())
        player = manager.get(1)
        await player.set_spatial(
            {"enabled": True, "x": 0, "y": 1.5, "z": 0, "auto": True}
        )
        task = player._spatial_auto_task
        manager.remove(1)
        await asyncio.sleep(0.01)
        self.assertTrue(task.done())
        self.assertIsNone(manager.get_existing(1))
