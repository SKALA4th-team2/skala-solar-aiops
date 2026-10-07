"""모델, 스케일러, 피처의 뜻이 서로 짝이 맞는지 확인한다.

지금의 서빙 코드는 MLflow 의 Production 모델과 serving_app/models/scaler.pkl 을 따로 불러 한 상자에 담는다
(project/serving_app/model_loader.py 의 _load_from_mlflow). 둘이 같은 발전소, 같은 자료로 만든 것인지 확인하는 곳이 없다.
발전소가 여럿이 되면 A 의 모델에 B 의 스케일러가 붙어도 오류 없이 값만 틀어진다.

제안하는 짝 확인: 학습할 때 "모델 묶음 기록(manifest)"을 함께 남기고, 불러올 때 다음을 견준다.
    - plant_id 가 요청한 발전소와 같은가
    - 스케일러 파일의 해시가 기록과 같은가
    - 피처의 뜻(순서, 단위, 창 길이)이 서빙 코드가 기대하는 것과 같은가

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    # 학습 뒤에 기록을 만든다
    python tools/multi_plant/bundle_check.py write --plant-id hadong-sewage --model-name solar-daily-hadong-sewage --model-version 1 \
        --scaler project/serving_app/models/scaler.pkl --dataset <학습에 쓴 CSV> --out <기록.json>
    # 불러오기 전에 짝을 확인한다
    python tools/multi_plant/bundle_check.py check --manifest <기록.json> --scaler <scaler.pkl> --plant-id hadong-sewage
check 는 어긋나면 종료 코드 1 이다.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

# 지금의 서빙 코드가 기대하는 입력의 뜻 (docs/decisions/0002-inputs-and-prediction-time.md)
FEATURE_SCHEMA = {
    "seq_len": C.SEQ_LEN,
    "features": [
        {"name": "generation_kwh", "unit": "kWh", "meaning": "그날의 하루 발전량", "field": "close"},
        {"name": "ghi_forecast_next_day", "unit": "MJ/m2", "meaning": "다음 날에 대한 하루 전 일사량 예보의 하루 합계", "field": "volume"},
    ],
    "target": {"name": "generation_kwh_next_day", "unit": "kWh"},
    "scaler": "min-max, 학습 구간으로 한 번 맞춘 뒤 고정",
}


def model_name_for(plant_id):
    """발전소마다 레지스트리의 모델 이름을 하나씩 둔다."""
    return f"solar-daily-{plant_id}"


def make_manifest(plant_id, model_name, model_version, scaler_path, dataset_path=None, train_end=None, run_id=None):
    manifest = {
        "schema_version": C.SCHEMA_VERSION,
        "plant_id": plant_id,
        "model": {"name": model_name, "version": str(model_version), "run_id": run_id},
        "scaler": {"file": Path(scaler_path).name, "sha256": C.sha256_file(scaler_path)},
        "feature_schema": FEATURE_SCHEMA,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    if dataset_path is not None:
        manifest["dataset"] = {"file": Path(dataset_path).name, "sha256": C.sha256_file(dataset_path), "train_end": train_end}
    return manifest


def check_bundle(manifest, scaler_path, plant_id, feature_schema=FEATURE_SCHEMA, model_name=None, model_version=None):
    # Runtime manifest v1 stores the same identity and paired hash with immutable version directories.
    if 'contract' in manifest:
        manifest={
            'plant_id':manifest.get('plant_id'),
            'scaler':{'sha256':manifest.get('hashes',{}).get('scaler.pkl')},
            'feature_schema':FEATURE_SCHEMA if manifest.get('contract')=='solar_next_day_jma_msm_day1_v1' else {},
            'model':{'name':manifest.get('model_name'),'version':manifest.get('version')},
        }
    issues = []
    if manifest.get("plant_id") != plant_id:
        issues.append(C.issue("error", "BUNDLE-PLANT", "manifest", f"기록의 발전소는 '{manifest.get('plant_id')}' 인데 요청은 '{plant_id}' 다"))
    actual = C.sha256_file(scaler_path)
    if manifest.get("scaler", {}).get("sha256") != actual:
        issues.append(C.issue("error", "BUNDLE-SCALER", scaler_path, "스케일러 파일이 이 모델을 학습할 때의 것과 다르다(해시 불일치)"))
    if manifest.get("feature_schema") != feature_schema:
        issues.append(C.issue("error", "BUNDLE-FEATURES", "manifest", "피처의 뜻이 서빙 코드가 기대하는 것과 다르다"))
    model = manifest.get("model", {})
    if model_name is not None and model.get("name") != model_name:
        issues.append(C.issue("error", "BUNDLE-MODEL-NAME", "manifest", f"기록의 모델은 '{model.get('name')}' 인데 불러온 것은 '{model_name}' 이다"))
    if model_version is not None and str(model.get("version")) != str(model_version):
        issues.append(C.issue("error", "BUNDLE-MODEL-VERSION", "manifest", f"기록의 버전은 '{model.get('version')}' 인데 불러온 것은 '{model_version}' 이다"))
    return issues


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    w = sub.add_parser("write")
    w.add_argument("--plant-id", required=True)
    w.add_argument("--model-name")
    w.add_argument("--model-version", required=True)
    w.add_argument("--scaler", type=Path, required=True)
    w.add_argument("--dataset", type=Path)
    w.add_argument("--train-end")
    w.add_argument("--run-id")
    w.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("check")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--scaler", type=Path, required=True)
    c.add_argument("--plant-id", required=True)
    c.add_argument("--model-name")
    c.add_argument("--model-version")
    a = p.parse_args()

    if a.command == "write":
        manifest = make_manifest(a.plant_id, a.model_name or model_name_for(a.plant_id), a.model_version, a.scaler, a.dataset, a.train_end, a.run_id)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"모델 묶음 기록을 썼다: {a.out}")
        return
    issues = check_bundle(json.loads(a.manifest.read_text(encoding="utf-8")), a.scaler, a.plant_id, model_name=a.model_name, model_version=a.model_version)
    for i in issues:
        print(f"[오류] {i['code']}  {i['where']}  {i['message']}")
    print("짝이 맞다" if not issues else f"어긋난 곳 {len(issues)}건")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
