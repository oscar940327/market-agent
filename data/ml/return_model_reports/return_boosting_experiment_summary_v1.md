# Return Boosting Experiment Summary

- Experiment version: `return_boosting_experiment_v1`
- Usage: comparison only. This does not replace the active return model.
- Available models: lightgbm, xgboost

## forward_return_5d
### xgboost
- Test MAE: 0.0374
- Test RMSE: 0.0559
- Test directional accuracy: 0.5264

### lightgbm
- Test MAE: 0.0378
- Test RMSE: 0.0565
- Test directional accuracy: 0.5238
- Test interval coverage: 0.4459

## forward_return_10d
### xgboost
- Test MAE: 0.0543
- Test RMSE: 0.0804
- Test directional accuracy: 0.5407

### lightgbm
- Test MAE: 0.0547
- Test RMSE: 0.0808
- Test directional accuracy: 0.5317
- Test interval coverage: 0.4388

## forward_return_20d
### xgboost
- Test MAE: 0.0792
- Test RMSE: 0.1180
- Test directional accuracy: 0.5443

### lightgbm
- Test MAE: 0.0795
- Test RMSE: 0.1183
- Test directional accuracy: 0.5458
- Test interval coverage: 0.4435

## max_drop_20d
### xgboost
- Test MAE: 0.0443
- Test RMSE: 0.0613
- Test directional accuracy: n/a

### lightgbm
- Test MAE: 0.0443
- Test RMSE: 0.0616
- Test directional accuracy: n/a
- Test interval coverage: 0.4675

These experiment results are not trading advice.
