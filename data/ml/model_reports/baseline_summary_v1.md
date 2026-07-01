# Baseline Model Summary

- Model version: `baseline_v1`
- Targets: `up_5d`, `up_10d`, `up_20d`, `large_drop_20d`
- Split: time-based train / validation / test from dataset.

## up_5d
- rule_based: validation accuracy 0.507, test accuracy 0.497, test ROC AUC n/a
- logistic_regression: validation accuracy 0.488, test accuracy 0.506, test ROC AUC 0.524
- random_forest: validation accuracy 0.501, test accuracy 0.498, test ROC AUC 0.520

## up_10d
- rule_based: validation accuracy 0.500, test accuracy 0.500, test ROC AUC n/a
- logistic_regression: validation accuracy 0.482, test accuracy 0.493, test ROC AUC 0.520
- random_forest: validation accuracy 0.494, test accuracy 0.500, test ROC AUC 0.521

## up_20d
- rule_based: validation accuracy 0.486, test accuracy 0.509, test ROC AUC n/a
- logistic_regression: validation accuracy 0.484, test accuracy 0.495, test ROC AUC 0.528
- random_forest: validation accuracy 0.499, test accuracy 0.488, test ROC AUC 0.521

## large_drop_20d
- rule_based: validation accuracy 0.475, test accuracy 0.448, test ROC AUC n/a
- logistic_regression: validation accuracy 0.600, test accuracy 0.558, test ROC AUC 0.617
- random_forest: validation accuracy 0.591, test accuracy 0.531, test ROC AUC 0.641

This baseline report is for model evaluation only and is not investment advice.
