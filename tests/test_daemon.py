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
    def __init__(self, play=10, block=5, overlay=None, locate=None, bonus=0.0,
                 pulse_every=0.0, pulse_for=0.0, pause_key="", pause_wait=0.0,
                 press_ok=True, freeze_games=True):
        self.pids = {"1": [100, 101]}
        self.frozen, self.thawed, self.notes = [], [], []
        self.events = []  # ordered ("freeze"|"thaw"|"sleep", detail)
        self.logs = []
        self.daemon = Daemon(
            Cycle(play, block),
            find=lambda: self.pids,
            freeze=lambda p: (self.frozen.append(set(p)), self.events.append(("freeze", set(p)))),
            thaw=lambda p: (self.thawed.append(set(p)), self.events.append(("thaw", set(p)))),
            notify=lambda title, body="": self.notes.append(title),
            overlay=overlay,
            clock=lambda: 1000.0,
            locate=locate,
            launch_bonus_seconds=bonus,
            pulse_every=pulse_every,
            pulse_for=pulse_for,
            sleep=lambda secs: self.events.append(("sleep", secs)),
            pause_key=pause_key,
            pause_wait=pause_wait,
            press=lambda key: (self.events.append(("press", key)), press_ok)[1],
            log=self.logs.append,
            freeze_games=freeze_games,
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


class PulseTest(unittest.TestCase):
    def blocked(self, **kw):
        h = Harness(play=1, block=600, **kw)
        h.daemon.step(1)  # -> BLOCKED, game frozen
        h.events.clear()
        return h

    def test_thaws_briefly_then_refreezes_every_interval(self):
        h = self.blocked(pulse_every=30, pulse_for=1)
        for _ in range(5):
            h.daemon.step(5)  # 25s: nothing yet
        self.assertNotIn("sleep", [e[0] for e in h.events])
        h.events.clear()
        h.daemon.step(5)  # 30s: pulse
        pulse = [e for e in h.events if e[0] in ("thaw", "sleep")]
        self.assertEqual(pulse, [("thaw", {100, 101}), ("sleep", 1)])
        kinds = [e[0] for e in h.events]
        self.assertLess(kinds.index("sleep"), len(kinds) - 1)
        self.assertEqual(h.events[-1][0], "freeze")  # always ends frozen
        self.assertEqual(h.events[-1][1], {100, 101})

    def test_pulses_repeat(self):
        h = self.blocked(pulse_every=10, pulse_for=0.5)
        for _ in range(6):
            h.daemon.step(5)  # 30s
        self.assertEqual([e for e in h.events if e[0] == "sleep"], [("sleep", 0.5)] * 3)

    def test_zero_interval_never_pulses(self):
        h = self.blocked(pulse_every=0, pulse_for=1)
        for _ in range(20):
            h.daemon.step(5)
        self.assertNotIn("sleep", [e[0] for e in h.events])

    def test_no_pulses_while_playing(self):
        h = Harness(play=1000, pulse_every=5, pulse_for=1)
        for _ in range(10):
            h.daemon.step(5)
        self.assertEqual(h.events, [])

    def test_pulses_while_waiting_for_enter_too(self):
        o = FakeOverlay()
        h = Harness(play=1, block=2, overlay=o, pulse_every=10, pulse_for=1)
        h.daemon.step(1)
        h.daemon.step(2)  # READY: waiting for Enter
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        h.events.clear()
        for _ in range(3):
            h.daemon.step(5)  # 15s at the prompt
        self.assertIn(("sleep", 1), h.events)
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)  # still waiting

    def test_the_timer_restarts_for_each_block(self):
        h = Harness(play=1, block=600, pulse_every=30, pulse_for=1)
        h.daemon.step(1)
        h.daemon.step(20)  # 20s into the first block
        h.daemon.release()  # block ended / shutdown
        h.daemon.cycle.phase = Phase.BLOCKED
        h.events.clear()
        h.daemon.step(20)  # 20s into a fresh block: not 40s
        self.assertNotIn("sleep", [e[0] for e in h.events])

    def test_nothing_to_pulse_when_nothing_is_frozen(self):
        h = Harness(play=1, block=600, pulse_every=5, pulse_for=1,
                    locate=lambda pids, app_ids: GameView(set(), set()))  # no window yet
        h.daemon.step(1)
        h.events.clear()
        h.daemon.step(6)
        self.assertNotIn("sleep", [e[0] for e in h.events])

    def test_a_reload_changes_the_pulse(self):
        h = self.blocked(pulse_every=30, pulse_for=1)
        h.daemon._watcher = FakeWatcher()
        h.daemon._watcher.pending = (Settings(pulse_every_seconds=0), None)
        h.daemon.reload_config()
        self.assertEqual(h.daemon.pulse_every, 0)


class PauseKeyTest(unittest.TestCase):
    def harness(self, focused=True, view=True, **kw):
        loc = (lambda pids, app_ids: GameView({(0, 0, 1920, 1080)}, set(pids), focused)
               ) if view else (lambda pids, app_ids: None)
        return Harness(play=1, block=600, locate=loc, pause_key="Escape",
                       pause_wait=1.5, **kw)

    def kinds(self, h):
        return [e[0] for e in h.events]

    def test_presses_the_key_then_waits_then_freezes(self):
        h = self.harness()
        h.daemon.step(1)  # play time over
        self.assertEqual(h.events[:2], [("press", "Escape"), ("sleep", 1.5)])
        self.assertLess(self.kinds(h).index("sleep"), self.kinds(h).index("freeze"))

    def test_does_not_press_when_the_game_is_not_focused(self):
        h = self.harness(focused=False)
        h.daemon.step(1)
        self.assertNotIn("press", self.kinds(h))
        self.assertIn("freeze", self.kinds(h))  # still frozen, just not paused first

    def test_does_not_press_when_sway_cannot_be_asked(self):
        h = self.harness(view=False)
        h.daemon.step(1)
        self.assertNotIn("press", self.kinds(h))

    def test_disabled_with_an_empty_key(self):
        h = Harness(play=1, block=600, pause_key="", pause_wait=1.5,
                    locate=lambda pids, app_ids: GameView(set(), set(pids), True))
        h.daemon.step(1)
        self.assertNotIn("press", self.kinds(h))

    def test_no_wait_if_the_key_could_not_be_sent(self):
        h = self.harness(press_ok=False)
        h.daemon.step(1)
        self.assertIn("press", self.kinds(h))
        self.assertNotIn("sleep", self.kinds(h))
        self.assertIn("freeze", self.kinds(h))

    def test_only_once_per_block_not_every_tick(self):
        h = self.harness()
        for _ in range(5):
            h.daemon.step(1)
        self.assertEqual(self.kinds(h).count("press"), 1)

    def test_a_game_launched_during_a_block_is_not_paused(self):
        h = self.harness()
        h.daemon.step(1)  # block starts with game 1 (paused, frozen)
        h.pids = {}
        h.daemon.step(1)  # it quits
        h.events.clear()
        h.pids = {"2": [200]}  # a different game launches mid-block
        h.daemon.step(1)
        self.assertNotIn("press", self.kinds(h))
        self.assertIn("freeze", self.kinds(h))

    def test_not_pressed_while_playing(self):
        h = Harness(play=1000, pause_key="Escape", pause_wait=1.5,
                    locate=lambda pids, app_ids: GameView(set(), set(pids), True))
        for _ in range(5):
            h.daemon.step(1)
        self.assertNotIn("press", self.kinds(h))

    def says(self, h, text):
        return any(text in line for line in h.logs)

    def test_logs_what_it_did_when_it_pressed(self):
        h = self.harness()
        h.daemon.step(1)
        self.assertTrue(self.says(h, "block started"))
        self.assertTrue(self.says(h, "pressed 'Escape'"))
        self.assertTrue(self.says(h, "1.5s"))

    def test_logs_why_it_did_not_press(self):
        h = self.harness(focused=False)
        h.daemon.step(1)
        self.assertTrue(self.says(h, "isn't focused"))
        h = self.harness(view=False)
        h.daemon.step(1)
        self.assertTrue(self.says(h, "sway can't be queried"))
        h = self.harness(press_ok=False)
        h.daemon.step(1)
        self.assertTrue(self.says(h, "couldn't send"))

    def test_pause_now_presses_without_freezing(self):
        h = self.harness()
        self.assertTrue(h.daemon.pause_now())
        self.assertIn("press", self.kinds(h))
        self.assertNotIn("freeze", self.kinds(h))
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_pause_now_with_no_game_says_so(self):
        h = self.harness()
        h.pids = {}
        self.assertFalse(h.daemon.pause_now())
        self.assertTrue(self.says(h, "no game is running"))
        self.assertNotIn("press", self.kinds(h))

    def test_a_reload_changes_the_key(self):
        h = self.harness()
        h.daemon._watcher = FakeWatcher()
        h.daemon._watcher.pending = (Settings(pause_key="p", pause_wait_seconds=3), None)
        h.daemon.reload_config()
        self.assertEqual((h.daemon.pause_key, h.daemon.pause_wait), ("p", 3))


class OverlayOnlyTest(unittest.TestCase):
    """freeze = false: a block is just the overlay; the game keeps running."""

    def make(self, **kw):
        o = FakeOverlay()
        h = Harness(play=1, block=3, overlay=o, freeze_games=False,
                    locate=lambda pids, app_ids: GameView({(0, 0, 1920, 1080)}, set(pids), True),
                    **kw)
        return h, o

    def test_nothing_is_ever_frozen_or_thawed(self):
        h, o = self.make(pulse_every=1, pulse_for=0.5)
        h.daemon.step(1)  # BLOCKED
        for _ in range(3):
            h.daemon.step(1)
        o.enter_pressed = True
        h.daemon.step(1)
        self.assertTrue(all(not f for f in h.frozen))
        self.assertTrue(all(not t for t in h.thawed))
        self.assertNotIn("sleep", [e[0] for e in h.events])  # no pulses either

    def test_the_overlay_still_runs_the_whole_block(self):
        h, o = self.make()
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)
        self.assertEqual(len(o.shown), 1)
        self.assertEqual(o.areas, [{(0, 0, 1920, 1080)}])
        h.daemon.step(3)  # countdown over -> waiting for Enter
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)  # still waits for Enter
        o.enter_pressed = True
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_the_pause_key_is_still_pressed(self):
        h, o = self.make(pause_key="Escape", pause_wait=2)
        h.daemon.step(1)
        self.assertIn(("press", "Escape"), h.events)

    def test_the_notification_does_not_claim_the_game_is_frozen(self):
        h, o = self.make()
        notes = []
        h.daemon._notify = lambda title, body="": notes.append(body)
        h.daemon.step(1)
        self.assertTrue(any("break" in b for b in notes))
        self.assertFalse(any("frozen" in b for b in notes))

    def test_the_log_says_it_is_not_freezing(self):
        h, o = self.make()
        h.daemon.step(1)
        self.assertTrue(any("not freezing" in line for line in h.logs))

    def test_turning_freeze_off_mid_block_releases_the_game(self):
        h = Harness(play=1, block=600, freeze_games=True)
        h.daemon._watcher = FakeWatcher()
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100, 101})
        h.daemon._watcher.pending = (Settings(freeze=False), None)
        h.daemon.reload_config()
        self.assertEqual(h.thawed[-1], {100, 101})
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100, 101})  # nothing new was frozen after

    def test_turning_freeze_on_still_works(self):
        h = Harness(play=1, block=600, freeze_games=False)
        h.daemon._watcher = FakeWatcher()
        h.daemon._watcher.pending = (Settings(freeze=True), None)
        h.daemon.reload_config()
        h.daemon.step(1)
        self.assertTrue(h.frozen)


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
