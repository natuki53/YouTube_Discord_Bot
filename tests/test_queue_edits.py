import unittest

from bot.music.models import Track
from bot.music.queue import MusicQueue


class QueueEditTests(unittest.TestCase):
    def test_duplicate_videos_are_removed_by_unique_entry_id(self):
        queue = MusicQueue()
        first = Track("same", "same", "one")
        second = Track("same", "same", "one")
        queue.enqueue(first)
        queue.enqueue(second)
        self.assertNotEqual(first.queue_id, second.queue_id)
        self.assertIs(queue.remove(second.queue_id), second)
        self.assertEqual(queue.peek_all(), [first])

    def test_stale_destination_does_not_partially_move_a_track(self):
        queue = MusicQueue()
        first, second = Track("1", "1", "one"), Track("2", "2", "one")
        queue.enqueue(first)
        queue.enqueue(second)
        with self.assertRaises(ValueError):
            queue.move(first.queue_id, "already-played")
        self.assertEqual(queue.peek_all(), [first, second])
        queue.move(second.queue_id, first.queue_id)
        self.assertEqual(queue.peek_all(), [second, first])
        queue.move(second.queue_id, None)
        self.assertEqual(queue.peek_all(), [first, second])
