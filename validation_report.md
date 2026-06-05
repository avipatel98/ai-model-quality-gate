# Validation Report

## Dataset

- Source file: `data/dataset.csv`
- Total labelled rows: 202
- Labels: `High`, `Medium`, `Low`
- Class balance: High 67, Medium 67, Low 68

## Model Validation

The model was trained using an 80/20 stratified train/test split with `random_state=42`.
The held-out test set contained 41 tasks.

| Metric | Result |
|---|---:|
| Accuracy | 0.8780 |
| Macro F1 | 0.8787 |
| Weighted F1 | 0.8800 |
| Macro precision | 0.8929 |
| Macro recall | 0.8791 |

The quality gate passed because the macro F1 score is above the configured threshold of 0.82.

## Confusion Matrix Insight

The confusion matrix is saved at `src/model/confusion_matrix.png`. The model separates the extremes well: no `High` tasks were predicted as `Low`, and no `Low` tasks were predicted as `High`. Most confusion happens between neighbouring priority levels, especially softer `High` tasks being classified as `Medium` and some exploratory `Medium` tasks being classified as `Low`.
