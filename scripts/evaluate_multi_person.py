"""Diagnostic only: two URFD views composited side-by-side, not real crowd data."""
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from vinfall.config import DATA, ROOT
from vinfall.model import TemporalClassifier
from vinfall.pose import PoseExtractor, rgb_frame
from vinfall.tracking import PeopleMonitor


def read(capture, timestamp):
    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp*1000)
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError(f'Cannot decode frame at {timestamp}')
    return rgb_frame(frame)


def main():
    extractor, classifier = PoseExtractor(), TemporalClassifier()
    falling = cv2.VideoCapture(str(DATA / 'fall-01-cam0.mp4'))
    normal = cv2.VideoCapture(str(DATA / 'adl-01-cam0.mp4'))
    try:
        standing = read(normal, 1)
        first = read(falling, .5)
        report = {'limits': 'Synthetic composite of two separate URFD recordings, using real YOLO and LSTM. '
                  'The disappearance is simulated by replacing the left view with a flat background. '
                  'This is an integration diagnostic, not an evaluation of real crowds, identity crossings or real occluded falls.',
                  'scenarios': []}
        for scenario, count in [('one_falls_other_stands', 50), ('one_disappears_other_stays', 115)]:
            monitor = PeopleMonitor(classifier)
            observations, counts = [], []
            for i in range(count):
                timestamp = i / 10
                left = read(falling, timestamp) if scenario == 'one_falls_other_stands' else first
                if scenario == 'one_disappears_other_stays' and timestamp >= 2:
                    left = np.full_like(first, 100)
                frame = np.concatenate([left, standing], axis=1)
                detections = extractor.infer([frame])[0]
                alerts = monitor.update(timestamp, detections, frame.shape[1]/frame.shape[0])
                observations.extend({**alert, 'time': timestamp} for alert in alerts)
                counts.append(len(detections))
            record = {'name': scenario, 'max_people_detected': max(counts),
                      'two_person_frames': sum(n >= 2 for n in counts), 'total_frames': len(counts),
                      'tracks_created': monitor.next_id-1, 'observations': observations}
            report['scenarios'].append(record)
            print(json.dumps(record), flush=True)
        target = ROOT / 'docs' / 'multi_person_diagnostic.json'
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    finally:
        falling.release()
        normal.release()


if __name__ == '__main__':
    main()
