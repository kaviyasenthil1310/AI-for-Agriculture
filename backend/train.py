import argparse
import time
from pathlib import Path

import torch
import torchvision.transforms as T
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from backend.model import get_model
from backend.labels import CLASS_NAMES


def train_one_epoch(model, dataloader, criterion, optimizer, device):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0
    for x, y in dataloader:
        x = x.to(device)
        y = y.to(device)
        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * x.size(0)
        preds = logits.argmax(dim=1)
        correct += (preds == y).sum().item()
        total += x.size(0)

    return running_loss / total, correct / total


def evaluate(model, dataloader, criterion, device):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0
    with torch.inference_mode():
        for x, y in dataloader:
            x = x.to(device)
            y = y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            running_loss += loss.item() * x.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == y).sum().item()
            total += x.size(0)

    return running_loss / total, correct / total


def build_dataloaders(data_dir, img_size, batch_size, num_workers=4):
    train_dir = Path(data_dir) / "train"
    val_dir = Path(data_dir) / "val"
    if not train_dir.exists():
        raise SystemExit(f"Train directory not found: {train_dir}")

    train_tf = T.Compose([
        T.RandomResizedCrop(img_size),
        T.RandomHorizontalFlip(),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    val_tf = T.Compose([
        T.Resize((img_size, img_size)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    train_ds = ImageFolder(train_dir, transform=train_tf)
    if train_ds.classes != CLASS_NAMES:
        raise ValueError(
            f"Dataset classes must be {CLASS_NAMES} in ImageFolder order; found {train_ds.classes}"
        )
    if val_dir.exists():
        val_ds = ImageFolder(val_dir, transform=val_tf)
        if val_ds.classes != CLASS_NAMES:
            raise ValueError(
                f"Validation classes must be {CLASS_NAMES} in ImageFolder order; found {val_ds.classes}"
            )
    else:
        # simple split from train if no val folder
        n = len(train_ds)
        val_n = max(1, int(0.1 * n))
        train_n = n - val_n
        train_ds, val_ds = torch.utils.data.random_split(train_ds, [train_n, val_n])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    return train_loader, val_loader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to dataset root (train/ and optional val/ subfolders)")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--img_size", type=int, default=224)
    parser.add_argument("--save", default="models/leaf_disease_cnn.pth")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device:", device)

    train_loader, val_loader = build_dataloaders(args.data, args.img_size, args.batch, args.workers)

    # number of classes inferred from train loader dataset
    if hasattr(train_loader.dataset, 'dataset'):
        # when random_split returns Subset wrapper
        num_classes = len(train_loader.dataset.dataset.classes)
    else:
        num_classes = len(train_loader.dataset.classes)

    model = get_model(num_classes=num_classes, checkpoint_path=None)
    model.to(device)

    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_acc = 0.0
    save_path = Path(args.save)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        dt = time.time() - t0
        print(f"Epoch {epoch}/{args.epochs}  train_loss={train_loss:.4f} train_acc={train_acc:.4f}  val_loss={val_loss:.4f} val_acc={val_acc:.4f}  time={dt:.1f}s")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), str(save_path))
            print(f"Saved best model ({best_acc:.4f}) to {save_path}")


if __name__ == "__main__":
    main()
