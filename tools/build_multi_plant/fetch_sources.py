"""Cache official public CSVs and metadata. No API key or private data is used."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "datasets/multi_plant"
# Candidate IDs from the repository's verified source inventory, not guessed URLs.
CANDIDATES = {
    "15043384": "남제주소내", "15043385": "부산복합자재창고",
    "15043386": "부산본부", "15043387": "부산수처리장",
    "15043388": "부산신항", "15043389": "부산운동장",
    "15043390": "삼척사택", "15043391": "삼척소내",
    "15043394": "신인천소내", "15043395": "신인천전망대",
    "15043396": "신인천해수구취수구", "15043397": "안동소내",
    "15043399": "영월본부", "15043400": "영월철도부지",
    "15043401": "위미2리", "15043402": "인천수산정수장",
    "15043404": "하동공설운동장", "15043405": "하동변전소",
    "15043406": "하동보건소", "15043407": "하동본부",
    "15043408": "하동정수장", "15043411": "행원소수력",
    "15095374": "무릉리", "15095380": "부산역선상주차장",
    "15095404": "용수리", "15096126": "송당리",
    "15096129": "신인천1_2단계주차장", "15096131": "신인천북측부지",
    "15096132": "신인천주차장", "15096134": "이천D백사면B",
    "15096136": "화촌주민참여형", "15109994": "감우리",
    "15109998": "신풍리", "15109999": "이천시백사면A",
    "15124860": "세화리", "15124861": "신인천본관주차장",
    "15140067": "와산리", "15140095": "익산다송리",
    "15156688": "부산철도2호기",
}
REFERENCE = {"15030079": "태양광발전기사양", "15147894": "발전소위치"}


def fetch(item, refresh=False):
    sid, name = item
    raw = OUT / "raw" / f"{sid}.csv"
    meta = OUT / "raw" / f"{sid}.json"
    if raw.exists() and meta.exists() and not refresh:
        result = json.loads(meta.read_text(encoding="utf-8"))
        if hashlib.sha256(raw.read_bytes()).hexdigest() != result["sha256"]:
            raise ValueError(f"Cached source hash mismatch: {sid}")
        if "usage_label" in result:
            return sid, result
        with urllib.request.urlopen(result["landing_url"], timeout=35) as response:
            html = response.read().decode("utf-8")
        result["usage_label"] = "이용허락범위 제한 없음" if "이용허락범위 제한 없음" in html else "포털 상세 조건 확인 필요"
        meta.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return sid, result
    url = f"https://www.data.go.kr/data/{sid}/fileData.do"
    with urllib.request.urlopen(url, timeout=35) as response:
        html = response.read().decode("utf-8")
    blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    schema = next(json.loads(b) for b in blocks if '"distribution"' in b)
    target = schema["distribution"][0]["contentUrl"]
    with urllib.request.urlopen(target, timeout=60) as response:
        body = response.read()
    if body.lstrip().lower().startswith((b"<!doctype", b"<html")):
        raise ValueError("Download returned HTML instead of CSV")
    result = {
        "source_id": sid, "name": name, "landing_url": url,
        "download_url": target, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
        "usage_label": "이용허락범위 제한 없음" if "이용허락범위 제한 없음" in html else "포털 상세 조건 확인 필요",
        "metadata": {k: schema.get(k) for k in ("name", "description", "dateModified", "license", "temporalCoverage", "spatialCoverage")},
    }
    raw.write_bytes(body)
    meta.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sid, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, item, args.refresh): item for item in (CANDIDATES | REFERENCE).items()}
        for future in as_completed(futures):
            sid, name = futures[future]
            try:
                _, results[sid] = future.result()
                print(f"OK {sid} {results[sid]['bytes']} bytes", flush=True)
            except Exception as exc:
                results[sid] = {"source_id": sid, "name": name, "error": str(exc)}
                print(f"FAILED {sid}: {exc}", flush=True)
    (OUT / "sources.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {sum('error' not in v for v in results.values())}/{len(results)} sources")


if __name__ == "__main__":
    main()
