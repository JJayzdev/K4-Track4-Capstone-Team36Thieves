# VinFall implementation contract

## Web and multi-room replay (current)

`run_web.py` launches Streamlit `app.py` on 127.0.0.1:8501 only. Upload analysis calls
`analysis.analyze_video` with a fresh PoseSession, FeatureExtractor and FallDetector.
Each run has its own UUID directory. `AnalysisResult` returns raw video, CSV, JSONL
trace, summary, frame/FPS counts, coverage, warnings and actual events. `media.py`
encodes H.264/yuv420p/faststart without dropping frames; input preview is encoded too.

`scripts/prepare_dashboard.py` independently analyzes each declared source, then
atomically publishes `runs/dashboard/current.json`. Room metadata and dataset labels
never enter the detector. `dashboard.py` embeds local result videos and trace state
transitions in a single iframe. Videos play concurrently; requestVideoFrameCallback
uses presented mediaTime to show state and release actual detector events. Fallback
timeupdate is coarser on older browsers. Room+event ID deduplicates alerts across loops.
Replay clears UI latches; stored analysis/CSV stay immutable. These are recorded
replays after batch processing, not live camera inference or a monitoring service.

`Observation` now additionally includes optional `angle_3d_deg` after `reason`.
`PoseLandmarks` is a list-compatible set of image landmarks with optional world
landmarks. Pixel geometry remains the source for 2D angle and normalized lowering;
world torso tilt is optional through `Config.use_world_tilt`. Missing/invalid world
geometry falls back to image geometry. Config and model hashes accompany every
prepared dashboard and web result. The active web profile is hospital_calibration_v3.json.
Calibration may finalize from 2000 ms when sufficient standing samples exist. Its
explicit 1000 ms grace permits collecting missing samples until 3000 ms; it closes
permanently if insufficient at that deadline. Zero grace preserves older profiles.

## Local webcam (user-requested scope extension)

`webcam_ui.py` adds a third Streamlit mode. Root owns the shared contracts,
app integration and UI; Worker A owns only `realtime.py`; Worker B owns only
`tests/test_realtime.py`. Both workers were requested GPT-6 Luna. No new package
is required. Camera capture uses the machine running the localhost server.

`CapturedFrame(sequence, timestamp_ms, captured_at, frame)` carries the latest
camera frame. `timestamp_ms` is elapsed monotonic capture time from the first
successful read, independent of inference speed and camera FPS metadata.
Recorded-video time remains frame-index/FPS. Observation and Detection retain
their existing interface; only the source of their elapsed timestamp differs.

`CameraSource` drains OpenCV capture on its own thread and keeps one latest
packet. `RealtimeSession` initializes the local pose model before opening the
camera, then owns fresh feature/detector state and a UUID CSV for that session.
The UI waits five seconds after model initialization before capture, giving time
to stand in view. Every start/reset recreates all state; no camera image/video is
saved. A process-wide lock prevents concurrent VinFall camera sessions. Cleanup
releases capture, logger, pose and the lock; terminal errors remain retryable.

`RealtimeSnapshot` atomically returns the latest annotated frame, detection,
events, processing metrics and CSV path. Streamlit refreshes a fragment every
0.2 seconds. Displayed frame and state come from the same processed packet.
Actual detector transitions append one event/CSV row; UI toasts deduplicate
event IDs. Stop or leaving webcam mode requests cleanup. The session releases
the device after 20 seconds without UI heartbeat, including startup lease
expiry before the camera is opened. Browser preview cadence is separate from
inference FPS. Physical-camera fall accuracy has not been accepted.

The earlier CLI contract and ownership history follow.

`main.py` is the checkout entry point; `python -m vinfall` uses the same
`src/vinfall/main.py` orchestrator. The CLI supports recorded video; webcam is
available in the web app.

| Owner | Files | Responsibility |
|---|---|---|
| Root | main.py, main module, contracts.py, config.py, configs, scripts, README, integration tests/report | interface, configuration, integration, acceptance |
| Worker A, requested GPT-6 Luna | video.py, pose.py, features.py, test_video.py, test_features.py | file input, model session, geometry/calibration |
| Worker B, requested GPT-6 Luna | detector.py, event_log.py, test_detector.py, test_event_log.py | temporal state machine, event CSV |

These boundaries were assigned after environment/model/input inspection and
creation of the shared contracts. Two workers were used concurrently. Worker
models were explicitly selected through the agent tool. This chat does not expose
an independent runtime field for verifying the root model's exact variant.

`Observation` is immutable:

```python
Observation(timestamp_ms: float, landmarks_valid: bool, calibrated: bool = False,
            angle_deg: Optional[float] = None, drop_ratio: Optional[float] = None,
            reason: str = "")
```

`Detection` is immutable:

```python
Detection(timestamp_ms: float, state: str, observation: Observation,
          event_id: Optional[int] = None, new_alert: bool = False, reason: str = "")
```

`timestamp_ms` is `frame_index * 1000 / FPS`, starting at frame zero. Geometry
and detector timestamps never come from wall time. MediaPipe requires integer
timestamps; the wrapper rounds down and ensures strict monotonicity in its model
session. Detection retains the original floating-point video time.

`VideoSource.read()` returns `(ok, BGR_frame, timestamp_ms)`. FPS must be finite
and positive or supplied explicitly. `PoseSession.process()` returns one list of
MediaPipe landmarks or `None`. `FeatureExtractor.update()` returns an Observation.
`FallDetector.update()` returns a Detection. `EventLogger.write()` consumes it.

Geometry converts normalized image coordinates to pixels before angles. Shoulder
and hip midpoints define the torso. Median torso center Y and nose-to-foot height
from standing samples in the first 2000 ms define the reference. Calibration
requires visible full-body landmarks, near-extended knees and a near-vertical
torso; it rejects initially seated/lying people. Knee threshold 145 degrees is a
standing-calibration geometry guard, not a validated clinical rule. At least 15
standing samples are required. No later automatic recalibration takes place.

The temporal detector requires rapid lowering and tilt evidence within the same
one-second window, then confirms a sustained low tilted pose. A recovered pose
cancels a candidate and clears stale evidence. Missing observations interrupt
evidence pairing, pause confirmation, and clear a candidate after a gap over
500 ms. An emitted ALERT remains latched until replay. Logger emits one CSV row
only when `new_alert` is true and deduplicates event IDs within that session.

Pause stops reading frames and updating all pipeline components. Replay closes
and recreates the model, detector and feature extractor, rewinds video, resets
frame index and writes a separate `.replayN.csv` log. EOF retains the last frame
in GUI mode. Headless mode exits at EOF. `finally` closes all acquired resources.

Run summaries include model SHA-256, package versions, configuration, frame
counts, state transitions and alert video times. JSONL traces support exact
baseline/pause/replay comparison. Evaluation records config/manifest hashes.
