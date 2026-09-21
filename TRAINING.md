Training instructions

Prepare dataset structure:

- dataset_root/
  - train/
    - Healthy/
    - Early\ Blight/
    - Late\ Blight/
    - Leaf\ Spot/
    - Bacterial\ Wilt/
  - val/  (optional, same subfolders as train)

Run training (example):

```bash
python -m backend.train --data path/to/dataset_root --epochs 10 --batch 32 --lr 1e-3
```

This will save the best model to `models/leaf_disease_cnn.pth`.

Notes:
- The script uses `backend.get_model` architecture and trains the classifier end-to-end.
- If you don't have a `val/` folder, the script will split 10% from `train/` for validation.
- For faster training use a GPU and increase `--batch` as appropriate.
