"""Camera-local person IDs, independent motion histories, and disappearance alerts.

Association uses global assignment of predicted position, overlap and clothing color.
This is short-term tracking, not biometric re-identification across cameras.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from .config import SAMPLE_FPS, SEQUENCE_LENGTH
from .detector import FallDetector
from .pose import features


@dataclass
class TrackingSettings:
    missing_seconds: float = 8.0
    minimum_seen: float = 1.0
    exit_margin: float = .08
    exit_zones: list = field(default_factory=list)


@dataclass
class Person:
    id: int
    box: np.ndarray
    points: np.ndarray
    appearance: np.ndarray
    first_seen: float
    last_seen: float
    detector: FallDetector
    hits: int = 1
    observed_seconds: float = 0
    interior: bool = False
    at_exit: bool = False
    missing_alerted: bool = False
    score: float = 0
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    vectors: deque = field(default_factory=lambda: deque(maxlen=64))


def center(box):
    return (box[:2] + box[2:]) / 2


def overlap(a, b):
    intersection = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
    union = np.maximum(0, a[2:] - a[:2]).prod() + np.maximum(0, b[2:] - b[:2]).prod() - intersection
    return float(intersection / max(union, 1e-8))


class PeopleMonitor:
    def __init__(self, classifier, settings=None):
        self.classifier = classifier
        self.settings = settings or TrackingSettings()
        self.reset()

    def reset(self):
        self.people = {}
        self.next_id = 1
        self.timestamp = None

    def near_exit(self, box, velocity):
        c = center(box)
        m = self.settings.exit_margin
        if np.any(c < m) or np.any(c > 1 - m):
            return True
        # A body touching the image border only counts when moving outwards.
        if ((box[0] < .02 and velocity[0] < -.03) or (box[2] > .98 and velocity[0] > .03)
                or (box[1] < .02 and velocity[1] < -.03) or (box[3] > .98 and velocity[1] > .03)):
            return True
        # Marked doors also work when an exit is in the middle of the image.
        feet = np.array([c[0], box[3]])
        return any(x1 <= feet[0] <= x2 and y1 <= feet[1] <= y2
                   for x1, y1, x2, y2 in self.settings.exit_zones)

    @staticmethod
    def cost(person, detection, timestamp):
        gap = timestamp - person.last_seen
        predicted = person.box.copy()
        shift = person.velocity * min(gap, .8)
        predicted[:2] += shift
        predicted[2:] += shift
        size = max(float(np.linalg.norm(person.box[2:] - person.box[:2])), .12)
        distance = float(np.linalg.norm(center(predicted) - center(detection['box'])) / size)
        iou = overlap(predicted, detection['box'])
        appearance = detection.get('appearance', np.zeros(24))
        color_distance = (float(np.abs(person.appearance - appearance).sum()) / 6
                          if person.appearance.any() and appearance.any() else 0)
        if distance > (1.2 if gap < 1 else 1.7) or (gap > 1 and color_distance > .65):
            return 1000.0
        return .5 * (1 - iou) + .35 * min(distance, 2) + .5 * color_distance

    def update(self, timestamp, detections, aspect=4 / 3):
        timestamp = float(timestamp)
        if self.timestamp is not None and timestamp <= self.timestamp:
            return []
        self.timestamp = timestamp
        # An ID that was seen leaving is not reused for a later entrant.
        retention = max(30, self.settings.missing_seconds + 5)
        self.people = {key: p for key, p in self.people.items()
                       if timestamp - p.last_seen <= (.8 if p.at_exit else retention if self.confirmed(p) else 1)}
        existing = list(self.people.values())
        matches = {}
        if existing and detections:
            costs = np.array([[self.cost(p, d, timestamp) for d in detections] for p in existing])
            rows, columns = linear_sum_assignment(costs)
            matches = {int(col): existing[int(row)] for row, col in zip(rows, columns) if costs[row, col] < 1.05}
        visible = []
        for index, detection in enumerate(detections):
            box = np.asarray(detection['box'], dtype=np.float32)
            points = np.asarray(detection['points'], dtype=np.float32)
            appearance = np.asarray(detection.get('appearance', np.zeros(24)), dtype=np.float32)
            person = matches.get(index)
            if person is None:
                person = Person(self.next_id, box.copy(), points, appearance, timestamp, timestamp,
                                FallDetector(self.classifier.threshold))
                self.people[person.id] = person
                self.next_id += 1
            else:
                gap = timestamp - person.last_seen
                velocity = (center(box) - center(person.box)) / max(gap, .01)
                person.velocity = .5 * person.velocity + .5 * velocity
                # Unobserved time cannot establish that a new track is real.
                if np.count_nonzero(points[:, 2] >= .25) >= 4:
                    person.observed_seconds += min(gap, .2) if gap <= .5 else 0
                if gap > .35:
                    person.vectors.clear()
                person.box, person.points = box.copy(), points
                person.appearance = .8 * person.appearance + .2 * appearance
                person.last_seen = timestamp
                person.hits += 1
            person.at_exit = self.near_exit(box, person.velocity)
            person.interior |= not person.at_exit
            person.missing_alerted = False
            person.vectors.append((timestamp, features(points, box, aspect)))
            visible.append(person)

        alerts = []
        if visible:
            # Resample each person's own history at the 10 Hz used during training.
            sequences = []
            target = timestamp - np.arange(SEQUENCE_LENGTH - 1, -1, -1) / SAMPLE_FPS
            for person in visible:
                times, vectors = zip(*person.vectors)
                vectors = np.asarray(vectors)
                sequences.append(np.stack([np.interp(target, times, vectors[:, i])
                                           for i in range(vectors.shape[1])], axis=1))
            scores = self.classifier.predict_windows(np.asarray(sequences, dtype=np.float32))
            for person, score in zip(visible, scores):
                person.score = float(score)
                if person.detector.update(timestamp, person.score, person.points, person.box, aspect):
                    alerts.append({'kind': 'fall', 'track_id': person.id,
                                   'last_seen': timestamp, 'last_box': person.box.tolist()})

        for person in self.people.values():
            missing = timestamp - person.last_seen
            if (missing >= self.settings.missing_seconds and self.confirmed(person) and person.interior
                    and not person.at_exit and not person.missing_alerted and not person.detector.latched):
                person.missing_alerted = True
                alerts.append({'kind': 'occlusion', 'track_id': person.id,
                               'last_seen': person.last_seen, 'missing_seconds': round(missing, 2),
                               'last_box': person.box.tolist()})
        return alerts

    def confirmed(self, person):
        return person.hits >= 3 and person.observed_seconds + 1e-6 >= self.settings.minimum_seen

    def snapshot(self):
        result = []
        for person in self.people.values():
            missing = max(0, (self.timestamp or 0) - person.last_seen)
            if missing > .3 and (person.at_exit or not self.confirmed(person)):
                continue
            result.append({'track_id': person.id, 'box': person.box.round(5).tolist(),
                           'points': person.points.round(5).tolist(), 'score': round(person.score, 4),
                           'visible': missing < 1e-6, 'missing_seconds': round(missing, 1),
                           'confirmed': self.confirmed(person),
                           'observed_seconds': round(person.observed_seconds, 2),
                           'state': 'occluded' if person.missing_alerted else 'missing' if missing > 0
                           else person.detector.state})
        return result
