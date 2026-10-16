"""Realtime session lifecycle tests use injected sources, never a physical camera."""
import csv
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from vinfall.config import Config
from vinfall.contracts import Observation
from vinfall.live_contracts import CapturedFrame
from vinfall.realtime import RealtimeSession


class FakeSource:
    def __init__(self, camera_index, max_width, clock, packets, error="", repeat_first=0):
        self.camera_index = camera_index
        self.max_width = max_width
        self.clock = clock
        self.packets = list(packets)
        self.error = error
        self.repeat_first = repeat_first
        self._stop = threading.Event()
        self.started = False
        self.stopped = False
        self.calls = 0
        self._index = 0
        self._repeated_first = False

    def start(self):
        self.started = True

    def read_latest(self, after_sequence, timeout=.2):
        if self._stop.is_set():
            return None
        if self._index < len(self.packets):
            if self._index == 1 and self.repeat_first and not self._repeated_first:
                self._repeated_first = True
                self.calls += 1
                return self.packets[0]
            packet = self.packets[self._index]
            self._index += 1
            self.calls += 1
            return packet
        self._stop.wait(min(timeout, .01))
        return None

    def request_stop(self):
        self._stop.set()

    def stop(self, timeout=2):
        self._stop.set()
        self.stopped = True
        return True


class FakePose:
    def __init__(self, *args):
        self.timestamps = []
        self.closed = False

    def process(self, frame, timestamp_ms):
        self.timestamps.append(timestamp_ms)
        return object()

    def draw(self, frame, landmarks):
        return frame

    def close(self):
        self.closed = True


class ScriptedFeatures:
    observations = {}

    def __init__(self, config):
        pass

    def update(self, landmarks, width, height, timestamp_ms):
        return self.observations[timestamp_ms]


def packet(sequence, timestamp_ms, captured_at):
    return CapturedFrame(sequence, timestamp_ms, captured_at,
                         np.zeros((48, 64, 3), dtype=np.uint8))


def make_session(directory, packets, *, source_error="", repeat_first=0,
                 pose_factory=None, idle_timeout_s=5, start_delay_s=0):
    created = {}

    def source_factory(camera_index, max_width, clock):
        source = FakeSource(camera_index, max_width, clock, packets,
                            error=source_error, repeat_first=repeat_first)
        created["source"] = source
        return source

    def create_pose(model_path, config):
        pose = (pose_factory or FakePose)(model_path, config)
        created["pose"] = pose
        return pose

    session = RealtimeSession(
        "injected-model.task", Config(), directory,
        source_factory=source_factory,
        pose_factory=create_pose,
        idle_timeout_s=idle_timeout_s,
        start_delay_s=start_delay_s,
    )
    return session, created


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        threading.Event().wait(.005)
    return predicate()


class RealtimeSessionTests(unittest.TestCase):
    def test_capture_timestamps_are_used_once_and_fps_comes_from_elapsed_time(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = time.monotonic()
            packets = [packet(0, 0, origin), packet(1, 80, origin + .08),
                       packet(2, 250, origin + .25)]
            session, refs = make_session(directory, packets, repeat_first=1)
            pose = None
            try:
                self.assertTrue(session.start())
                self.assertTrue(wait_until(lambda: session.snapshot().frame_count == 3))
                pose = session._pose
                snapshot = session.snapshot()
                self.assertEqual(snapshot.detection.timestamp_ms, 250)
                self.assertEqual(snapshot.elapsed_ms, 250)
                self.assertEqual(snapshot.frame_count, 3)
                self.assertEqual(pose.timestamps, [0, 80, 250])
                self.assertGreater(snapshot.elapsed_ms, 0)
                self.assertAlmostEqual(snapshot.fps,
                                       (snapshot.frame_count - 1) /
                                       (snapshot.elapsed_ms / 1000))
                self.assertTrue(refs["source"].started)
            finally:
                session.stop()
            self.assertTrue(refs["source"].stopped)
            self.assertTrue(pose.closed)

    def test_real_detector_pauses_confirmation_during_missing_frames_and_logs_one_event(self):
        with tempfile.TemporaryDirectory() as directory:
            # Candidate starts at 100 ms and accrues 500 ms of confirmation.
            # Two missing frames pause time. The alert therefore occurs at 1600 ms.
            times = list(range(0, 1700, 100))
            packets = [packet(i, ts, time.monotonic() + i * .001)
                       for i, ts in enumerate(times)]
            observations = {0: Observation(0, True, True, 10, 0)}
            for ts in times[1:]:
                if ts in (700, 800):
                    observations[ts] = Observation(ts, False, True, None, None)
                else:
                    observations[ts] = Observation(ts, True, True, 70, .30)
            ScriptedFeatures.observations = observations
            session, _ = make_session(directory, packets)
            try:
                with patch("vinfall.features.FeatureExtractor", ScriptedFeatures):
                    self.assertTrue(session.start())
                    self.assertTrue(wait_until(lambda: session.snapshot().frame_count == len(packets)))
                    snapshot = session.snapshot()
                self.assertEqual(len(snapshot.events), 1)
                self.assertEqual(snapshot.events[0]["video_timestamp_ms"], 1600)
                with snapshot.csv_path.open(newline="", encoding="utf-8") as file:
                    rows = list(csv.DictReader(file))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["video_timestamp_ms"], "1600")
            finally:
                session.stop()

    def test_new_session_does_not_reuse_previous_alert_state(self):
        with tempfile.TemporaryDirectory() as directory:
            def run(observations, name):
                times = sorted(observations)
                packets = [packet(i, ts, time.monotonic() + i * .001)
                           for i, ts in enumerate(times)]
                ScriptedFeatures.observations = observations
                session, _ = make_session(Path(directory) / name, packets)
                try:
                    with patch("vinfall.features.FeatureExtractor", ScriptedFeatures):
                        self.assertTrue(session.start())
                        self.assertTrue(wait_until(
                            lambda: session.snapshot().frame_count == len(packets)))
                        return session.snapshot()
                finally:
                    session.stop()

            fall_samples = {0: Observation(0, True, True, 10, 0)}
            fall_samples.update({ts: Observation(ts, True, True, 70, .30)
                                 for ts in range(100, 1401, 100)})
            alert_session = run(fall_samples, "alert")
            self.assertEqual(len(alert_session.events), 1)

            normal_samples = {
                0: Observation(0, True, True, 10, 0),
                100: Observation(100, True, True, 15, .02),
            }
            fresh_session = run(normal_samples, "normal")
            self.assertEqual(fresh_session.events, ())

    def test_source_read_failure_sets_error_and_releases_pose_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            packets = [packet(0, 0, time.monotonic())]
            session, refs = make_session(directory, packets,
                                         source_error="injected camera read failure")
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: session.status == "ERROR"
                                       and refs.get("pose") is not None
                                       and refs["pose"].closed
                                       and refs.get("source") is not None
                                       and refs["source"].stopped))
            pose = refs["pose"]
            self.assertIn("injected camera read failure", session.snapshot().error)
            self.assertTrue(refs["source"].stopped)
            self.assertTrue(pose.closed)

    def test_failed_model_initialization_does_not_open_camera_and_releases_session_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            opened = []

            def failed_pose(*args):
                raise RuntimeError("injected model initialization failure")

            session, _ = make_session(directory, [], pose_factory=failed_pose)
            session._source_factory = lambda *args: opened.append(True)
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: session.status == "ERROR"))
            self.assertIn("injected model initialization failure", session.snapshot().error)
            self.assertEqual(opened, [])
            self.assertTrue(session.stop(timeout=1))
            self.assertEqual(session.status, "ERROR")
            self.assertTrue(session.stop(timeout=1))
            self.assertEqual(session.status, "ERROR")

            # A new session can acquire the global camera/model lease after failure.
            fresh, _ = make_session(directory, [])
            self.assertTrue(fresh.start())
            self.assertTrue(fresh.stop())

    def test_stop_unblocks_reader_and_closes_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            session, refs = make_session(directory, [])
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: "source" in refs and refs["source"].started))
            pose = refs["pose"]
            self.assertTrue(session.stop(timeout=1))
            self.assertEqual(session.status, "STOPPED")
            self.assertTrue(refs["source"].stopped)
            self.assertTrue(pose.closed)

    def test_idle_lease_expires_and_releases_source_and_pose_without_snapshot_touches(self):
        with tempfile.TemporaryDirectory() as directory:
            session, refs = make_session(
                directory, [packet(0, 0, time.monotonic())], idle_timeout_s=.05)
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: session.status == "STOPPED"
                                       and refs.get("source") is not None
                                       and refs["source"].stopped
                                       and refs.get("pose") is not None
                                       and refs["pose"].closed, timeout=2))
            self.assertEqual(session.status, "STOPPED")

    def test_stop_during_start_delay_cancels_before_camera_is_opened(self):
        with tempfile.TemporaryDirectory() as directory:
            opened = []

            def source_factory(*args):
                opened.append(True)
                raise AssertionError("camera factory must not run during cancelled startup")

            refs = {}

            def pose_factory(model_path, config):
                pose = FakePose(model_path, config)
                refs["pose"] = pose
                return pose

            session = RealtimeSession(
                "injected-model.task", Config(), directory,
                source_factory=source_factory, pose_factory=pose_factory,
                start_delay_s=2.0,
            )
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: "pose" in refs))
            self.assertTrue(session.stop(timeout=1))
            self.assertEqual(session.status, "STOPPED")
            self.assertTrue(refs["pose"].closed)
            self.assertEqual(opened, [])

    def test_idle_lease_expiring_during_slow_model_init_never_opens_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            opened = []
            refs = {}

            def slow_pose_factory(model_path, config):
                threading.Event().wait(.08)
                pose = FakePose(model_path, config)
                refs["pose"] = pose
                return pose

            def source_factory(*args):
                opened.append(True)
                raise AssertionError("expired idle lease must not open camera")

            session = RealtimeSession(
                "injected-model.task", Config(), directory,
                source_factory=source_factory,
                pose_factory=slow_pose_factory,
                idle_timeout_s=.03,
            )
            self.assertTrue(session.start())
            self.assertTrue(wait_until(lambda: session.status == "STOPPED"
                                       and refs.get("pose") is not None
                                       and refs["pose"].closed, timeout=2))
            self.assertEqual(opened, [])

    def test_second_live_session_reports_busy_then_new_session_can_start(self):
        with tempfile.TemporaryDirectory() as directory:
            first, first_refs = make_session(directory, [])
            self.assertTrue(first.start())
            self.assertTrue(wait_until(lambda: "source" in first_refs
                                       and first_refs["source"].started))

            busy, _ = make_session(directory, [])
            self.assertFalse(busy.start())
            self.assertEqual(busy.status, "ERROR")
            self.assertTrue(busy.snapshot().error)
            self.assertTrue(busy.stop(timeout=1))
            self.assertEqual(busy.status, "ERROR")
            self.assertTrue(busy.stop(timeout=1))
            self.assertEqual(busy.status, "ERROR")

            self.assertTrue(first.stop(timeout=1))
            self.assertEqual(first.status, "STOPPED")
            retry, _ = make_session(directory, [])
            self.assertTrue(retry.start())
            self.assertTrue(retry.stop(timeout=1))


if __name__ == "__main__":
    unittest.main()
