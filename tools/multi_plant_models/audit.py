"""Independent standard-library audit of splits, metrics, artifacts and registry coverage."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KINDS = ["LSTM", "XGBoost", "Prophet", "Ensemble", "LSTM_Main_Ensemble"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8",newline="") as fp:
        return list(csv.DictReader(fp))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a,b):
    assert math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-3),(a,b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default="docs/proposal/evidence/multi_plant_models_20261007")
    ap.add_argument("--require-registry",action="store_true")
    ap.add_argument("--completed-only",action="store_true",help="Audit completed plants during training; write *_partial outputs")
    args = ap.parse_args()
    out = ROOT/args.out
    screening = read(out/"screening.json")
    if args.completed_only:
        if args.require_registry:
            raise ValueError("Final registry coverage requires the complete batch")
        screening["admitted"] = [p for p in screening["admitted"] if (out/"plants"/p["plant_id"]/"result.json").exists()]
    suffix = "_partial" if args.completed_only else ""
    summary, checks = [], []
    for rel,expected in read(out/"training_code_hashes.json").items():
        assert digest(out/"source_snapshot"/rel)==expected, f"Run source snapshot changed: {rel}"
        if args.completed_only:
            assert digest(ROOT/rel)==expected, f"Training code changed during execution: {rel}"
    if not args.completed_only:
        assert read(out/"training_code_integrity_at_completion.json")["passed"]
    for plant in screening["admitted"]:
        pid = plant["plant_id"]
        dest = out/"plants"/pid
        result = read(dest/"result.json")
        meta = read(dest/"models/metadata.json")
        frozen = read(dest/"frozen_selection.json")
        source = ROOT/meta["source"]
        assert digest(source)==meta["source_sha256"]==plant["selected_upload"]["sha256"]
        raw = rows(source)[-1480:]
        assert len(raw)==plant["retained_rows"]
        dates = [date.fromisoformat(r["Date"]) for r in raw]
        assert all(b-a==timedelta(days=1) for a,b in zip(dates,dates[1:]))
        manifest = rows(dest/"split_manifest.csv")
        assert [r["date"][:10] for r in manifest]==[str(d) for d in dates[20:]]
        counts = Counter(r["split"] for r in manifest)
        assert counts["test"]==365 and counts["validation"]==180 and counts["train"]>=550
        assert [r["split"] for r in manifest]==["train"]*counts["train"]+["validation"]*180+["test"]*365
        lastfit = len(raw)-366
        assert meta["trained_through"]==raw[lastfit]["Date"]==meta["scaler"]["last_generation_date"]
        assert meta["scaler"]["last_weather_row"]==raw[lastfit-1]["Date"]
        for j,(col,end) in enumerate([("Close",lastfit+1),("Volume",lastfit)]):
            values = [float(r[col]) for r in raw[:end]]
            close(meta["scaler"]["min"][j],min(values))
            close(meta["scaler"]["range"][j],max(values)-min(values))
        assert datetime.fromisoformat(frozen["frozen_utc"]) < datetime.fromisoformat(meta["created_utc"])
        assert frozen["selected_by_validation"]==min(frozen["validation_metrics"], key=lambda k:frozen["validation_metrics"][k]["rmse_kwh"])
        for phase,start,end in [("validation",len(raw)-545,len(raw)-365),("test",len(raw)-365,len(raw))]:
            predictions = rows(dest/f"{phase}_predictions.csv")
            assert [r["date"][:10] for r in predictions]==[r["Date"] for r in raw[start:end]]
            actual = [float(r["actual_kwh"]) for r in predictions]
            for a,r in zip(actual,raw[start:end]):
                close(a,float(r["Close"]))
            for name in result[f"{phase}_metrics"]:
                predicted = [float(r[name]) for r in predictions]
                assert all(math.isfinite(v) and v>=0 for v in predicted)
                errors = [p-a for p,a in zip(predicted,actual)]
                stats = {"rmse_kwh":math.sqrt(sum(e*e for e in errors)/len(errors)),
                         "mae_kwh":sum(abs(e) for e in errors)/len(errors),
                         "wape_pct":100*sum(abs(e) for e in errors)/sum(actual)}
                for metric,value in stats.items():
                    close(value,result[f"{phase}_metrics"][name][metric])
            for offset,r in enumerate(predictions,start):
                close(float(r["Persistence"]),float(raw[offset-1]["Close"]))
                close(float(r["Mean7"]),sum(float(v["Close"]) for v in raw[offset-7:offset])/7)
                close(float(r["Seasonal7"]),float(raw[offset-7]["Close"]))
                for name,weights in frozen["ensemble_weights"].items():
                    close(sum(weights),1)
                    assert min(weights)>=0
                    if name=="LSTM_Main_Ensemble":
                        assert weights[0]>=.5
                    close(float(r[name]),sum(float(r[k])*v for k,v in zip(KINDS[:3],weights)))
        for file,expected in result["artifact_hashes"].items():
            assert digest(dest/"models"/file)==expected
        assert read(dest/"reload_check.json")["passed"]
        baselines = ["Persistence","Mean7","Seasonal7"]
        baseline = min(baselines,key=lambda k:result["validation_metrics"][k]["rmse_kwh"])
        baseline_rmse = result["test_metrics"][baseline]["rmse_kwh"]
        for kind,metrics in result["test_metrics"].items():
            summary.append({"plant_id":pid,"name":plant["name"],"unit":plant["unit"],"model":kind,
                "selected_by_validation":kind==result["selected_by_validation"],**metrics,
                "validation_rmse_kwh":result["validation_metrics"][kind]["rmse_kwh"],
                "baseline_selected_on_validation":baseline,"baseline_test_rmse_kwh":baseline_rmse,
                "rmse_improvement_vs_baseline_pct":100*(baseline_rmse-metrics["rmse_kwh"])/baseline_rmse})
        checks.append({"plant_id":pid,"passed":True})
    registry_count = 0
    if args.require_registry:
        registry = read(out/"registry_index.json")
        assert registry["production_promoted"] is False
        registered = registry["models"]
        pairs = {(r["plant_id"],r["kind"]) for r in registered}
        assert pairs=={(p["plant_id"],k) for p in screening["admitted"] for k in KINDS}
        assert len(registered)==len(pairs)
        assert all(r["reload_passed"] and r["alias"]=="candidate" for r in registered)
        assert all(any(dep.startswith("scikit-learn==") for dep in r["pip_requirements"]) for r in registered)
        for row in registered:
            assert row["metadata_sha256"]==digest(out/"plants"/row["plant_id"]/"models/metadata.json")
        registry_count = len(registered)
    with (out/f"all_metrics{suffix}.csv").open("w",encoding="utf-8-sig",newline="") as fp:
        writer = csv.DictWriter(fp,fieldnames=list(summary[0]))
        writer.writeheader();writer.writerows(summary)
    selected = [r for r in summary if r["selected_by_validation"]]
    lstms = [r for r in summary if r["model"]=="LSTM"]
    wins = Counter(r["model"] for r in selected)
    output = {"passed":True,"plants_checked":len(checks),"registry_models_checked":registry_count,
              "checks":checks,"selected_model_counts":dict(wins),
              "lstm_beats_validation_selected_baseline_on_test":sum(r["rmse_improvement_vs_baseline_pct"]>0 for r in lstms),
              "selected_beats_validation_selected_baseline_on_test":sum(r["rmse_improvement_vs_baseline_pct"]>0 for r in selected)}
    (out/f"independent_audit{suffix}.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    lines = ["발전소별 모델 학습·저장 결과", "",
             f"검증 완료: {len(checks)}개 호기 / 제외: {len(screening['excluded'])}개 호기 (추가 원본 3건은 상류 단계에서 제외)",
             "호기 수는 독립 사업장 수와 다릅니다.",
             "입력: 20일 발전량 + ASOS 전날 관측 일사량. 대상일 T에는 T-2 일사량까지 사용.",
             "추가 자료는 예보 입력이 아니므로 기존 하동 예보 기반 점수와 직접 비교하지 않습니다.",
             "시험: 각 개소 마지막 365일, 이전 180일 검증. LSTM 고정 시드42, 최대120 epoch에서 검증 최적 epoch 선택.",
             "LSTM 모델 구조는 수업 코드와 동일. 이번 다개소 비교는 시드 변동성까지 평가한 결과가 아닙니다.",
             "검증 선택 분포: "+str(dict(wins)),
             f"LSTM이 검증에서 선택한 단순 기준모델보다 시험 RMSE가 낮은 호기: {output['lstm_beats_validation_selected_baseline_on_test']}/{len(checks)}",
             f"MLflow 등록 및 재로딩 확인: {registry_count}개 후보 버전 (Production 승격 없음)","",
             "발전소 / 호기 | 검증에서 선택한 모델 | 시험 RMSE(kWh) | LSTM RMSE(kWh)"]
    for s in selected:
        lstm = next(r for r in lstms if r["plant_id"]==s["plant_id"])
        lines.append(f"{s['name']} / {s['unit']} ({s['plant_id']}) | {s['model']} | {s['rmse_kwh']:.2f} | {lstm['rmse_kwh']:.2f}")
    lines += ["", "저장 위치: plants/<plant_id>/models/", "lstm.keras, xgboost.ubj, prophet.json, scaler.json, metadata.json",
              "metadata.json에 두 앙상블의 비중·학습 기간·입력 정의·검증/시험 점수 포함.",
              "MLflow 모델별 URI/버전/실험 ID: registry_index.json. 로컬 DB와 아티팩트: mlflow/.",
              "저장 모델은 시험 이전까지 학습한 평가 후보이며 최신 전체 자료로 재학습한 운영 모델이 아닙니다.",
              "모든 시험 날짜에서 파일 재로딩 예측 재현 확인. MLflow URI 재로딩은 개소·모델별 3일 확인.",
              "FastAPI 다개소 라우팅, 고장 감지, 자동 재학습/교체는 이번 작업 범위에서 실행하지 않았습니다.",
              "모델 저장과 버전 관리가 준비됐으며 AIOps 전체 동작이 완료됐다는 뜻은 아닙니다.","", "제외 호기 및 사유:"]
    lines += [f"{p['name']} ({p['plant_id']}): {p['reason']}" for p in screening["excluded"]]
    if args.completed_only:
        lines.insert(0,"진행 중: 완료된 일부 호기만 검사한 중간 결과입니다.")
    (out/f"report{suffix}.txt").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(output,ensure_ascii=False))


if __name__=="__main__":
    main()
