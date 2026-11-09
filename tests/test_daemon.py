import unittest

from gamedoro.config import Settings
from gamedoro.cycle import Cycle, Phase
from gamedoro.daemon import FAST_INTERVAL, OVERLAY_MARGIN, Daemon
from gamedoro.sway import GameView


class FakeOverlay:
    def __init__(self):
        self.available = True
        self.shown = []  # `until` of every show() call
        self.areas = []  # `areas` of every show() call
        self.hidden = 0
        self.enter_pressed = False

    def show(self, until, areas=None):
        self.shown.append(until)
        self.areas.append(areas)

    def hide(self):
        self.hidden += 1

    def confirmed(self):
        pressed, self.enter_pressed = self.enter_pressed, False
        return pressed


class Harness:
    def __init__(self, play=10, block=5, overlay=None, locate=None, bonus=0.0):
        self.pids = {"1": [100, 101]}
        self.frozen, self.thawed, self.notes = [], [], []
        self.daemon = Daemon(
            Cycle(play, block),
            find=lambda: self.pids,
            freeze=lambda p: self.frozen.append(set(p)),
            thaw=lambda p: self.thawed.append(set(p)),
            notify=lambda title, body="": self.notes.append(title),
            overlay=overlay,
            clock=lambda: 1000.0,
            locate=locate,
            launch_bonus_seconds=bonus,
        )


class DaemonTest(unittest.TestCase):
    def test_freezes_when_play_time_runs_out(self):
        h = Harness(play=4)
        h.daemon.step(2)
        self.assertEqual(h.frozen, [])
        h.daemon.step(2)
        self.assertEqual(h.frozen, [{100, 101}])
        self.assertIn("Time's up!", h.notes)

    def test_catches_game_launched_during_block(self):
        h = Harness(play=1, block=5)
        h.daemon.step(1)
        h.pids = {"1": [100, 101], "2": [200]}
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100, 101, 200})

    def test_thaws_everything_when_block_ends(self):
        h = Harness(play=1, block=2)
        h.daemon.step(1)
        h.pids = {}  # game frozen, then user quit it
        h.daemon.step(2)
        self.assertEqual(h.thawed, [{100, 101}])
        self.assertIn("Block over", h.notes)

    def test_release_is_idempotent(self):
        h = Harness(play=1)
        h.daemon.step(1)
        h.daemon.release()
        h.daemon.release()
        self.assertEqual(h.thawed, [{100, 101}, set()])

    def test_warns_once_before_blocking(self):
        h = Harness(play=70)
        for _ in range(2):
            h.daemon.step(5)  # 60s left: warn
        self.assertEqual(h.notes, ["1 minute of play left"])
        h.daemon.step(5)
        self.assertEqual(h.notes, ["1 minute of play left"])  # only once


class OverlayTest(unittest.TestCase):
    def blocked(self, block=5):
        o = FakeOverlay()
        h = Harness(play=1, block=block, overlay=o)
        h.daemon.step(1)  # play time over -> BLOCKED
        return h, o

    def test_overlay_counts_down_to_the_end_of_the_block(self):
        h, o = self.blocked(block=5)
        self.assertEqual(o.shown, [1000.0 + 5 + OVERLAY_MARGIN])

    def test_game_stays_frozen_until_enter_is_pressed(self):
        h, o = self.blocked(block=2)
        h.daemon.step(2)  # block over -> READY
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        self.assertEqual(h.thawed, [])
        self.assertIn("Block over", h.notes)
        for _ in range(3):
            h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        self.assertEqual(h.thawed, [])

        o.enter_pressed = True
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)
        self.assertEqual(h.thawed, [{100, 101}])
        self.assertGreaterEqual(o.hidden, 1)
        self.assertEqual(h.notes.count("Block over"), 2)  # prompt, then resumed

    def test_enter_during_the_countdown_is_discarded(self):
        h, o = self.blocked(block=3)
        o.enter_pressed = True
        h.daemon.step(1)  # still BLOCKED
        h.daemon.step(2)  # -> READY
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)  # old Enter didn't count

    def test_quitting_the_game_mid_block_hides_the_overlay(self):
        h, o = self.blocked()
        h.pids = {}
        h.daemon.step(1)
        self.assertEqual(o.hidden, 1)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)  # timer still runs

    def test_ready_with_no_game_resumes_without_asking(self):
        h, o = self.blocked(block=2)
        h.pids = {}
        h.daemon.step(2)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_unusable_overlay_falls_back_to_auto_resume(self):
        h, o = self.blocked(block=2)
        o.available = False
        h.daemon.step(2)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)
        self.assertEqual(h.thawed, [{100, 101}])

    def test_overlay_dying_in_ready_falls_back_to_auto_resume(self):
        h, o = self.blocked(block=2)
        h.daemon.step(2)
        o.available = False  # e.g. the terminal failed to launch
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_tells_the_user_once_when_the_overlay_is_unavailable(self):
        h, o = self.blocked()
        o.available = False
        h.daemon.step(1)
        h.daemon.step(1)
        self.assertEqual(h.notes.count("Overlay unavailable"), 1)

    def blocked_with_screens(self, screens):
        o = FakeOverlay()
        h = Harness(play=1, block=5, overlay=o,
                    locate=lambda pids, app_ids: None if h.screens is None
                    else GameView(h.screens, set(pids)))
        h.screens = screens
        h.daemon.step(1)
        return h, o

    def test_overlay_covers_the_screen_showing_the_game(self):
        h, o = self.blocked_with_screens({(0, 0, 1920, 1080)})
        self.assertEqual(o.areas, [{(0, 0, 1920, 1080)}])

    def test_overlay_goes_away_when_you_leave_the_game_workspace(self):
        h, o = self.blocked_with_screens({(0, 0, 1920, 1080)})
        h.screens = set()
        h.daemon.step(1)
        self.assertEqual(o.hidden, 1)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)  # still frozen
        self.assertEqual(h.frozen[-1], {100, 101})

    def test_overlay_returns_when_you_come_back(self):
        h, o = self.blocked_with_screens(set())
        self.assertEqual(o.shown, [])
        h.screens = {(0, 0, 1920, 1080)}
        h.daemon.step(1)
        self.assertEqual(len(o.shown), 1)

    def test_unknown_location_covers_every_screen(self):
        h, o = self.blocked_with_screens(None)
        self.assertEqual(o.areas, [None])

    def test_enter_prompt_waits_while_you_are_elsewhere(self):
        h, o = self.blocked_with_screens({(0, 0, 1920, 1080)})
        h.daemon.step(5)  # block over -> READY
        h.screens = set()
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        self.assertEqual(h.thawed, [])  # still frozen until you confirm

    def test_polls_faster_while_blocked_with_an_overlay(self):
        h, o = self.blocked()
        self.assertEqual(h.daemon.interval(), FAST_INTERVAL)
        self.assertEqual(Harness().daemon.interval(), 1.0)

    def test_release_hides_the_overlay(self):
        h, o = self.blocked()
        h.daemon.release()
        self.assertEqual(o.hidden, 1)


class LaunchBonusTest(unittest.TestCase):
    def test_launching_a_game_adds_the_bonus(self):
        h = Harness(play=100, bonus=30)
        h.pids = {}
        h.daemon.step(1)  # no game yet
        h.pids = {"1": [100]}
        h.daemon.step(1)  # launch: +30, then 1s of play drains
        self.assertEqual(h.daemon.cycle.remaining, 100 + 30 - 1)

    def test_a_game_already_running_at_startup_is_not_a_launch(self):
        h = Harness(play=100, bonus=30)
        h.daemon.step(1)  # the very first look already sees a game
        self.assertEqual(h.daemon.cycle.remaining, 99)

    def test_staying_in_the_game_gives_no_more_bonus(self):
        h = Harness(play=100, bonus=30)
        h.pids = {}
        h.daemon.step(1)
        h.pids = {"1": [100]}
        for _ in range(3):
            h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.remaining, 130 - 3)

    def test_every_new_launch_tops_up_but_never_beyond_the_cap(self):
        h = Harness(play=100, bonus=30)
        for launch in range(3):
            h.pids = {}
            h.daemon.step(1)
            h.pids = {"1": [100]}
            h.daemon.step(1)
            self.assertLessEqual(h.daemon.cycle.remaining, 130)
        self.assertGreater(h.daemon.cycle.remaining, 100)  # topped up again

    def test_no_bonus_for_a_game_launched_during_a_block(self):
        h = Harness(play=1, block=60, bonus=30)
        h.daemon.step(1)  # BLOCKED
        h.pids = {}
        h.daemon.step(1)
        h.pids = {"2": [200]}
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)
        self.assertEqual(h.daemon.cycle.remaining, 58)  # block time, untouched

    def test_zero_bonus_changes_nothing(self):
        h = Harness(play=100, bonus=0)
        h.pids = {}
        h.daemon.step(1)
        h.pids = {"1": [100]}
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.remaining, 99)


class SurgicalFreezeTest(unittest.TestCase):
    """Freeze only the process owning the game window, not the whole tree."""

    def make(self, view):
        h = Harness(play=1, block=300, locate=lambda pids, app_ids: h.view)
        h.pids = {"12210": [100, 101, 102]}  # 100 = game, others = helpers
        h.view = view
        return h

    def test_freezes_only_the_window_owner(self):
        h = self.make(GameView({(0, 0, 1920, 1080)}, {100}))
        h.daemon.step(1)  # -> BLOCKED
        h.daemon.step(1)
        self.assertTrue(h.frozen)
        for frozen in h.frozen:
            self.assertEqual(frozen, {100})  # helpers never touched

    def test_only_what_was_frozen_is_thawed(self):
        h = self.make(GameView({(0, 0, 1920, 1080)}, {100}))
        h.daemon.step(1)
        h.daemon.release()
        self.assertEqual(h.thawed, [{100}])

    def test_freezes_everything_when_sway_cannot_be_asked(self):
        h = self.make(None)
        h.daemon.step(1)
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100, 101, 102})

    def test_still_freezes_when_the_game_is_on_another_workspace(self):
        h = self.make(GameView(set(), {100}))  # not on screen, but window known
        h.daemon.step(1)
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100})

    def test_waits_for_the_window_before_freezing_anything(self):
        h = self.make(GameView(set(), set()))  # game running, no window yet
        h.daemon.step(1)
        h.daemon.step(5)
        self.assertEqual(h.frozen[-1], set())

    def test_gives_up_waiting_and_freezes_the_whole_tree(self):
        h = self.make(GameView(set(), set()))
        h.daemon.step(1)
        for _ in range(4):  # 20s > WINDOW_GRACE
            h.daemon.step(5)
        self.assertEqual(h.frozen[-1], {100, 101, 102})

    def test_helpers_are_released_once_the_window_appears(self):
        h = self.make(GameView(set(), set()))
        h.daemon.step(1)
        for _ in range(4):
            h.daemon.step(5)  # fell back to the whole tree
        h.view = GameView({(0, 0, 1920, 1080)}, {100})
        h.daemon.step(1)
        self.assertEqual(h.thawed[-1], {101, 102})  # only the helpers
        self.assertEqual(h.frozen[-1], {100})

    def test_a_late_window_resets_the_wait(self):
        h = self.make(GameView(set(), set()))
        h.daemon.step(1)
        h.daemon.step(10)
        h.view = GameView(set(), {100})
        h.daemon.step(1)
        h.view = GameView(set(), set())
        h.daemon.step(10)  # a fresh 10s, not 21s
        self.assertEqual(h.frozen[-1], set())


class FakeWatcher:
    def __init__(self):
        self.pending = (None, None)

    def poll(self):
        result, self.pending = self.pending, (None, None)
        return result


class ReloadTest(unittest.TestCase):
    def make(self):
        h = Harness(play=600, block=300)
        h.daemon._watcher = FakeWatcher()
        return h

    def test_launch_bonus_changes_apply_immediately(self):
        h = self.make()
        h.daemon._watcher.pending = (Settings(launch_bonus=3), None)
        h.daemon.reload_config()
        self.assertEqual(h.daemon.launch_bonus_seconds, 180)

    def test_new_lengths_apply_to_the_next_cycle_only(self):
        h = self.make()
        h.daemon.step(5)
        h.daemon._watcher.pending = (Settings(play=20, block=3), None)
        h.daemon.reload_config()
        self.assertEqual(h.daemon.cycle.play_seconds, 1200)
        self.assertEqual(h.daemon.cycle.block_seconds, 180)
        self.assertEqual(h.daemon.cycle.remaining, 595)  # running budget untouched
        self.assertIn("gamedoro: settings reloaded", h.notes)

    def test_a_block_in_progress_cannot_be_shortened(self):
        h = Harness(play=1, block=300)
        h.daemon._watcher = FakeWatcher()
        h.daemon.step(1)  # BLOCKED, 300s
        h.daemon._watcher.pending = (Settings(play=1, block=0.1), None)
        h.daemon.reload_config()
        self.assertEqual(h.daemon.cycle.remaining, 300)
        h.daemon.step(5)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)

    def test_bad_config_keeps_old_settings_and_tells_you(self):
        h = self.make()
        h.daemon._watcher.pending = (None, "config.toml: play must be a number")
        h.daemon.reload_config()
        self.assertEqual(h.daemon.cycle.play_seconds, 600)
        self.assertIn("gamedoro: bad config", h.notes)

    def test_no_change_is_silent(self):
        h = self.make()
        h.daemon.reload_config()
        self.assertEqual(h.notes, [])

    def test_works_without_a_watcher(self):
        Harness().daemon.reload_config()


if __name__ == "__main__":
    unittest.main()
