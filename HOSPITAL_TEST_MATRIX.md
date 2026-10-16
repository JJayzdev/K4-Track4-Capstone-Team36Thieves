# Hospital-like logic and video test matrix

This matrix separates detector logic checks from evidence on recorded video.
The logic checks below use hand-authored observations; they establish behavior
for those sequences only. There is currently **no hospital video evidence**
and no claim of hospital readiness or clinical performance.

## Synthetic logic checks

Run with `PYTHONPATH=src .venv-demo/Scripts/python.exe -m unittest discover -s tests -p "test_hospital_logic.py"`
from PowerShell (set `$env:PYTHONPATH="src"` first).

| Case | Input sequence | Expected result | Evidence type |
|---|---|---|---|
| H01 | Fast sit/crouch height change with upright torso | Remains `NORMAL`; no alert | Synthetic observation test |
| H02 | Person starts lying down; standing calibration never succeeds | Remains `CALIBRATING`; no alert | Synthetic observation test |
| H03 | Fall candidate accumulates some confirmation, then bed-area occlusion lasts beyond the missing-data reset interval | Occlusion is `NO_DATA`; resumed lying pose does not alert from stale evidence | Synthetic observation test |
| H04 | Slow lie/down sequence | No rapid-drop alert | Existing generic detector test (`test_slow_lying_does_not_create_rapid_drop_evidence`); synthetic only |
| H05 | Same observations in separate analyses, followed by a normal/no-person analysis | Repeated event times match; next analysis has no stale alert | Existing web-logic test; synthetic only |

These are focused logic controls, not estimates of false-alarm or missed-fall
rates. Room tags such as `ward_bed`, `clinic_rehab`, and `corridor` belong in
recording metadata and analysis reports. They must not select or alter detector
thresholds.

## Recorded-video evidence plan

| Environment | Positive and negative scenarios to record | Status |
|---|---|---|
| Ward / bed area | Controlled fall near bed; sit/stand transfers; lying down and getting up; bed or furniture occlusion | No hospital recordings yet |
| Clinic / rehabilitation | Controlled fall during supervised walking or transfer; walking, bending, reaching, and supported exercises | No clinic recordings yet |
| Corridor | Controlled fall during walking; ordinary walking, turning, pausing, and bending | No corridor recordings yet |

For each usable recording, capture about 3 seconds of visible standing at the
start for calibration, with the full body and floor in view when safe. Record
occlusion and out-of-frame cases as separate labeled conditions. Falls should
be staged by a consenting, able-bodied actor under appropriate supervision on
mats or another safe surface; do not ask actual patients to fall or record
patients for this demonstration.

Split development and evaluation by **actor and camera/recording session** so
the same person, viewpoint, or continuous recording cannot leak across splits.
Choose any thresholds using development recordings only, then freeze them
before evaluation. Report false alarms per hour and missed falls for each room
type, plus event timing and excluded/unusable clips. Also show the overall
counts and denominators; do not pool away a poor per-room result.

Until those recordings are collected and evaluated, label all hospital-like
results as synthetic logic checks or non-hospital dataset results, as
applicable. Synthetic cases do not count as recorded-video samples.
