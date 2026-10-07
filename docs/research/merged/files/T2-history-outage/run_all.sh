#!/bin/sh
# T2 통합 계산을 처음부터 다시 돌린다. s8(실습 LSTM 18회 학습)은 오래 걸려 따로 둔다.
cd "$(dirname "$0")"
PY=/Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
$PY s1_stoplists.py > s1_stoplists.out 2>&1
$PY s2_rules.py > s2_rules.out 2>&1
$PY s2b_rules_norm.py > s2b_rules_norm.out 2>&1
$PY s4_timeline.py > s4_timeline.out 2>&1
$PY s5_extra.py > s5_extra.out 2>&1
$PY s6_profile.py > s6_profile.out 2>&1
$PY s7_final_rule_and_list.py > s7_final_rule_and_list.out 2>&1
$PY s3_samples_lstm.py > s3_samples_lstm.out 2>&1
$PY s1b_signature.py > s1b_signature.out 2>&1
# 실습 LSTM (tensorflow 가 든 가상환경): for k in lag proxy; do for v in none stop43 stop50; do /Users/psm/workspace/skala-aiops/project/.venv/bin/python -B s8_lstm_exclusion.py $k $v 42 43 44 > lstm/${k}_${v}.log 2>&1; done; done
# $PY s8b_lstm_summary.py > s8b_lstm_summary.out 2>&1
