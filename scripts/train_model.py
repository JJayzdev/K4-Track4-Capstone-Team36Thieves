"""Train a small LSTM using official posture labels, keeping both views of a sequence in one split."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
import torch
from torch import nn

from vinfall.config import DATA, DEMO_SEQUENCES, MODELS, SEQUENCE_LENGTH
from vinfall.model import FallLSTM, windows
from vinfall.pose import PoseExtractor

VALIDATION_FALLS = {"fall-04", "fall-12", "fall-19", "fall-27", "fall-30"}
TEST_ADLS = {f"adl-{i:02d}" for i in (1, 9, 17, 25, 33)}
VALIDATION_ADLS = {f"adl-{i:02d}" for i in (5, 13, 21, 29, 37)}


def split_for(sequence):
    if sequence in set(DEMO_SEQUENCES) | TEST_ADLS:
        return "test"
    if sequence in VALIDATION_FALLS | VALIDATION_ADLS:
        return "validation"
    return "train"


def metrics(actual, scores, threshold):
    predicted = scores >= threshold
    actual = actual.astype(bool)
    tp = int((predicted & actual).sum())
    fp = int((predicted & ~actual).sum())
    fn = int((~predicted & actual).sum())
    tn = int((~predicted & ~actual).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / max(precision + recall, 1e-9),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=65)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(42)
    random.seed(42)
    np.random.seed(42)
    labels = {}
    for name in ("urfall-cam0-falls.csv", "urfall-cam0-adls.csv"):
        with (DATA / name).open() as handle:
            for row in csv.reader(handle):
                labels.setdefault(row[0], {})[int(row[1])] = int(row[2])
    groups = {name: [] for name in ("train", "validation", "test")}
    members = {name: [] for name in groups}
    extractor = PoseExtractor()
    for video in sorted(DATA.glob("*.mp4")):
        sequence = video.stem.rsplit("-cam", 1)[0]
        if sequence not in labels:
            continue
        data = extractor.extract(video)
        frame_labels = labels[sequence]
        frame_numbers = np.array(sorted(frame_labels))
        # The paired preview MP4s share a 30 Hz timeline. Labels are 1-based.
        targets, usable = [], []
        for i, timestamp in enumerate(data["times"]):
            frame = int(round(timestamp * 30)) + 1
            nearest = int(frame_numbers[np.argmin(abs(frame_numbers - frame))])
            label = frame_labels[nearest]
            targets.append(float(label == 1))
            # Exclude transitional / unannotated frames and unobservable poses.
            usable.append(label != 0 and abs(nearest - frame) <= 3 and (data["points"][i, :, 2] >= .25).sum() >= 8)
        keep = np.array(usable)
        group = split_for(sequence)
        groups[group].append((windows(data["features"])[keep], np.array(targets, np.float32)[keep]))
        members[group].append(video.name)
    tensors = {}
    for group, entries in groups.items():
        if not entries:
            raise SystemExit(f"Empty {group} split. Download the full dataset first.")
        tensors[group] = (torch.from_numpy(np.concatenate([x for x, _ in entries])),
                          torch.from_numpy(np.concatenate([y for _, y in entries])))
    x, y = tensors["train"]
    model = FallLSTM()
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.001)
    criterion = nn.BCEWithLogitsLoss(pos_weight=(len(y) - y.sum()) / y.sum().clamp(min=1))
    best_loss, best_state = float("inf"), None
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(x))
        for indices in order.split(128):
            optimizer.zero_grad()
            loss = criterion(model(x[indices]), y[indices])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            vx, vy = tensors["validation"]
            validation_loss = float(criterion(model(vx), vy))
        if validation_loss < best_loss:
            best_loss, best_state = validation_loss, copy.deepcopy(model.state_dict())
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(f"Epoch {epoch + 1}/{args.epochs}: validation loss {validation_loss:.4f}", flush=True)
    model.load_state_dict(best_state)
    model.eval()
    with torch.inference_mode():
        val_scores = model(tensors["validation"][0]).sigmoid().numpy()
        val_y = tensors["validation"][1].numpy()
        threshold = max(np.arange(.35, .91, .025), key=lambda t: metrics(val_y, val_scores, t)["f1"])
        test_scores = model(tensors["test"][0]).sigmoid().numpy()
    report = {"model": "YOLOv8n Pose + LSTM(57,48)", "seed": 42, "sequence_length": SEQUENCE_LENGTH,
              "sample_fps": 10, "threshold": float(threshold), "validation_loss": best_loss,
              "splits": members, "samples": {key: len(value[1]) for key, value in tensors.items()},
              "validation": metrics(val_y, val_scores, threshold),
              "test": metrics(tensors["test"][1].numpy(), test_scores, threshold),
              "limits": "Window-level posture classification on staged URFD clips. Both views of a clip stay in the same split. Splits are by sequence, NOT by participant; no claim of generalization to unseen elderly patients. Camera 1 uses the synchronized camera 0 posture annotation. Event-level alert accuracy must be assessed separately."}
    MODELS.mkdir(exist_ok=True)
    torch.save({"state_dict": best_state, "threshold": float(threshold)}, MODELS / "fall_lstm.pt")
    (MODELS / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"samples": report["samples"], "threshold": float(threshold), "test": report["test"]}), flush=True)


if __name__ == "__main__":
    main()
