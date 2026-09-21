import os

import torch
from torch import nn


class LeafDiseaseCNN(nn.Module):
    def __init__(self, num_classes: int = 5):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            # Block 2
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            # Block 3
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 28 * 28, 256),  # assumes input 224x224
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x

def get_model(num_classes: int = 5, checkpoint_path: str | None = None):
    model = LeafDiseaseCNN(num_classes=num_classes)
    if checkpoint_path:
        if os.path.isfile(checkpoint_path):
            state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
        else:
            print(f"Warning: checkpoint not found at '{checkpoint_path}'. Using untrained model.")
    model.eval()
    return model