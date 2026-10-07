Hadong offline model comparison

Purpose
Compare the teaching LSTM, XGBoost, Prophet and validation-weighted ensembles.
This experiment does not modify, upload to, or start the serving application.
The separately added multi_plant data is intentionally outside this first run.

Run from project/ (Python 3.11):
  .venv/Scripts/python -X utf8 -B ../tools/model_benchmark/benchmark.py --stage all
  .venv/Scripts/python -X utf8 -B ../tools/model_benchmark/check_causality.py
  .venv/Scripts/python -X utf8 -B ../tools/model_benchmark/audit_results.py

Use --out docs/proposal/evidence/<new-run-name> for a new run. The default output
belongs to the original 2026-10-07 experiment; reusing it replaces its artifacts.
Each stage can be recovered with --stage prepare|xgb|prophet|lstm|select|
final_xgb|final_prophet|final_lstm|report. Always freeze select before final_*.
Do not change candidates or weights based on the test results.

Reproduction dependencies are listed in requirements.txt. The executed environment
is recorded in evidence/model_benchmark_20261007/environment.json. On this Windows
host, project/.venv inherits preinstalled packages (--system-site-packages), with
Prophet installed locally into that venv; project/requirements.txt is unchanged.

Data and method
- Source: datasets/hadong_upload_forecast_jma.csv, 1337 contiguous daily rows.
- 20 input days -> next day's total generation; 1317 supervised samples.
- Train: 2022-07-22..2024-08-31 (772 targets).
- Validation: 2024-09-01..2025-02-27 (180 targets).
- Test: 2025-02-28..2026-02-27 (365 targets, covers all seasons).
- Volume[d] is the forecast for d+1. No target-day observed weather is used.
- Rolling one-day predictions use actual generation up to T-1. This is not an
  open-loop forecast of an entire year made at the test start.
- Select settings/epochs/ensemble weights on validation. Refit each selected
  model on train+validation before predicting the untouched test block.
- Min-max scaling is fitted only on information before the respective cutoff.
- LSTM architecture is imported from project/serving_app/lstm_model.py unchanged.
  Three seeds, 3 learning rates, full 120 epochs retaining validation-best weights;
  final epochs = median validation-best epoch across seeds; shuffle=False.
  Report each seed and the three-seed prediction average. No best-seed selection.
- XGBoost: all 20x2 raw inputs, recent statistics, forecast efficiency and calendar.
- Prophet: yearly seasonality and forecast irradiance, with/without lagged
  generation/efficiency regressors selected on validation. No weekly/holiday effect.
- Calendar dates are known beforehand. Feature engineering differs by model, so
  this compares practical model systems, not isolated network architectures.
- Ensemble weights use a coarse nonnegative grid summing to 1. A constrained
  variant keeps >=50% weight on LSTM to show a teaching-model-centered option.
- All forecasts are floored at zero; no abnormal days are removed from scoring.

Artifacts
protocol.json is written before training; frozen_selection.json before final test.
Search results, histories, per-day predictions, monthly metrics, seed scores,
14-day paired block-bootstrap intervals and input hashes support inspection.
report.txt and test_rmse.png summarize actual execution, not prior research values.
Model files in models/ and execution *.log files are ignored by the local .gitignore.
No server, MLflow registry or existing proposal policy is changed.

Troubleshooting observed during this run
1. TensorFlow: ImportError, DLL initialization failed (_pywrap_tensorflow_internal).
   Cause isolation: this host imports TensorFlow successfully before NumPy, with
   TF_ENABLE_ONEDNN_OPTS=0. No CPU-instruction or driver diagnosis was established.
   Fix: initialize TensorFlow first in separate LSTM worker processes and set that
   environment variable. Subsequent training verifies the workaround.
2. Prophet absent; pip network access failed inside the sandbox (WinError 10013).
   Fix: install Prophet in project/.venv with approved network access. Existing
   global packages and application requirements are not replaced.
3. An initial validation-only pilot used patience=15. Some LSTM seeds stopped
   before the network learned the radiation response (best epoch 2-3). Before
   any final-test evaluation, the protocol was amended to complete 120 epochs
   for all candidates and keep validation-best weights. Pilot artifacts and
   protocol_amendment.json preserve that choice; no test-based tuning occurred.

Limitations
One plant and one temporal split; not proof of generalization to new plants.
Historical forecast publication time remains an assumption from the source docs.
Research already examined this dataset; it is not a freshly collected blind sample.
Prior 264-day numbers use a different split/preprocessing and are not comparable.
Daily totals do not measure hourly market settlement compliance.
This validates offline prediction, not serving latency or AIOps retraining behavior.
