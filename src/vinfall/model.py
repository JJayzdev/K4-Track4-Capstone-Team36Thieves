"""Small temporal classifier, trained by scripts/train_model.py, never random at runtime."""
import numpy as np
import torch
from torch import nn

from .config import MODELS, SEQUENCE_LENGTH
from .pose import FEATURE_SIZE


class FallLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(FEATURE_SIZE, 48, batch_first=True)
        self.head = nn.Sequential(nn.Linear(48, 24), nn.ReLU(), nn.Linear(24, 1))

    def forward(self, x):
        output, _ = self.lstm(x)
        return self.head(output[:, -1]).squeeze(-1)


def windows(vectors):
    padded = np.pad(vectors, ((SEQUENCE_LENGTH - 1, 0), (0, 0)), mode="edge")
    return np.stack([padded[i:i + SEQUENCE_LENGTH] for i in range(len(vectors))]).astype(np.float32)


class TemporalClassifier:
    def __init__(self):
        path = MODELS / "fall_lstm.pt"
        if not path.exists():
            raise FileNotFoundError("Missing trained LSTM. Run: python scripts/train_model.py")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        self.model = FallLSTM()
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()
        self.threshold = float(checkpoint["threshold"])

    def predict(self, vectors):
        return self.predict_windows(windows(vectors))

    def predict_windows(self, sequences):
        batches = torch.from_numpy(np.asarray(sequences, dtype=np.float32))
        with torch.inference_mode():
            return torch.cat([self.model(chunk).sigmoid() for chunk in batches.split(128)]).numpy()
