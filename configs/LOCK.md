# Configuration freeze

Frozen before evaluation inference on 2026-10-16, Asia/Bangkok.
`locked.json` keeps the initial PLAN.md thresholds unchanged. Development
fall-01 reached SUSPECTED but lost pose before confirmation; adl-01 had no alert.
No threshold adjustment can compensate for missing visual evidence without
changing the intended behavior. The extra development fall-04 began seated and
correctly failed standing calibration. Inspected candidates fall-06/08/10 began
seated; fall-21 was shorter than the calibration interval; fall-11 timed out.
These inspected candidates are not evaluation samples.

The `low_pose_drop_ratio` threshold is explicitly 0.25 of median standing height.
`visibility_min=0.5`, tilt >=60 degrees, rapid drop >=0.25 within 700 ms,
evidence coincidence <=1000 ms, low tilted confirmation >=1200 ms, missing gap
>500 ms cancels pending confirmation. Missing time never counts as confirmation.

See evaluation provenance JSON for the exact SHA-256 of this configuration.
Any change after this freeze requires a new evaluation run and report.
