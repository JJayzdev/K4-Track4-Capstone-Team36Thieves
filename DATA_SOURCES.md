# Video inputs

## Multi-room additions (2026-10-16)

Eight Le2i/IMVIA public mirror clips are declared in `data/hospital_manifest.json`;
download with `scripts/download_room_samples.py`. Source: [Kaggle mirror by tuyenldvn](https://www.kaggle.com/datasets/tuyenldvn/falldataset-imvia).
The mirror metadata says license Unknown; original rights could not be verified.
Do not redistribute these video assets as licensed project content. Original AVIs
and normalized H.264 copies remain ignored local inputs. Original FPS is checked
and preserved; metadata, source names, content hashes and annotations are recorded.

R01–R04 are development: coffee room, home, office, lecture room. R05–R08 are
evaluation, selected before threshold tuning; R05/R06 falls and R07/R08 normal
according to provided annotation files (1-based onset/end frames; 0/0 normal).
R03/R04 lack matching annotations in the mirror and remain explicitly unknown;
they are excluded from labeled accuracy calculations. No clip label creates an alert.

These rooms are public surrogate backgrounds, **not hospital footage**. A hospital
ward with bed, rehabilitation area, corridor, occlusion and everyday negatives still
need separate locally authorized validation; see HOSPITAL_TEST_MATRIX.md. URFD D02
provides a public bedroom background in the replay dashboard.

Default room allocation is R01/R04/R03/URFD-D02. R01 was used to tune global lowering
thresholds from 25%/25% to 15% rapid and 20% low; its detection is development evidence.
The frozen configuration hash is 826164d73aebb6c20989886b4d6d073db52217d9ff642e0136dea06341c22cca.
Evaluation failures are retained and reported, not used to force per-clip outcomes.

The subsequent room-03 calibration-boundary fix uses hospital_calibration_v3.json
(SHA-256 f4b37cc179683dd08d525b2788f71cfe75df7537d169a04498a46853628a88da).
It allows a bounded 1000 ms calibration grace inside the initial 3 seconds; source
videos, labels and frame timestamps are unchanged. R03's fall was observed by the
user, while its original annotation remains unknown in the downloaded manifest.

## Local pose models

Official Google MediaPipe Pose Landmarker float16/v1 downloads:
[Lite](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task),
[Full](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task),
[Heavy](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task).
`scripts/download_model.py --variant full` downloads the active model. No training.
Active Full SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.

## URFD provenance

Source: [UR Fall Detection Dataset](https://fenix.ur.edu.pl/~mkepski/ds/uf.html),
University of Rzeszow, Bogdan Kwolek and Michal Kepski.

Citation: Kwolek, B. and Kepski, M. (2014), *Human fall detection on embedded
platform using depth maps and wireless accelerometer*, Computer Methods and
Programs in Biomedicine 117(3), 489–501.

Dataset license: CC BY-NC-SA 4.0, intended for non-commercial academic use.
Commercial use requires contacting the authors. The clips are local test inputs,
not included in the source distribution. Run `python scripts/download_samples.py`.

Fixed split chosen before inference or threshold adjustment:

| ID | Split | File | Expected |
|---|---|---|---|
| D01 | development | fall-01-cam0.mp4 | fall |
| D02 | development | adl-01-cam0.mp4 | normal |
| D03 | additional development/calibration rejection | fall-04-cam0.mp4 | fall, begins seated |
| E01 | evaluation | fall-02-cam0.mp4 | fall |
| E02 | evaluation | fall-03-cam0.mp4 | fall |
| E03 | evaluation | adl-02-cam0.mp4 | normal |
| E04 | evaluation | adl-03-cam0.mp4 | normal |

These official preview MP4s combine depth (left) and RGB (right). Use
`--crop right-half`; this selects RGB without changing timing. OpenCV reports
30 FPS on all six preview files. Their original sensor timestamps are not used
by this demo, which follows PLAN.md frame-index/FPS timestamps.

No frames are repeated or prepended to create a calibration interval. A clip
without sufficient visible standing data in its first two seconds is a recorded
calibration failure. Short clips may end before the 1.2-second confirmation can
complete. Such cases remain failures, not successful detections.

The initial split had two development and four evaluation clips. D03 was added
after the first development fall lost pose on the floor. Extra candidates
fall-06/08/10 were inspected and began seated; fall-21 was only 1.83 seconds;
fall-11 timed out. They are not part of evaluation and do not add evaluation
samples. No evaluation clip was moved into development.

The occlusion input `data/occlusion_dev.mp4` is derived from development adl-01:
frames 80 through 109 are blacked out. It is a missing-data control, not an
independent sample or a new normal/fall evaluation clip.
