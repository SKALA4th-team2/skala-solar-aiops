"""컨테이너에 1초 간격으로 예측을 보내 성공률과 응답 시간을 잰다. 짧은 구간의 값이고 한 달 단위의 가용성이 아니다."""
import json, sys, time, urllib.request, urllib.error
BASE, N, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read(); return r.status, time.time() - t, raw
    except urllib.error.HTTPError as e: return e.code, time.time() - t, b""
    except Exception: return 0, time.time() - t, b""
code, _, raw = call("/ui/sample?plant_id=hadong-sewage"); body = json.loads(raw)["prediction"]
started = time.strftime("%Y-%m-%dT%H:%M:%S+09:00"); t0 = time.time(); lat = []; ok = 0; health_ok = 0; health_n = 0; fails = []
for i in range(N):
    tick = t0 + i
    code, dt, raw = call("/predict", body)
    good = code == 200 and len(json.loads(raw).get("predictions", [])) == 24 if code == 200 else False
    ok += good; lat.append(dt)
    if not good: fails.append(dict(i=i, code=code))
    if i % 10 == 0:
        c, _, r = call("/health"); health_n += 1; health_ok += (c == 200 and json.loads(r).get("worker_alive") is True)
    time.sleep(max(0, tick + 1 - time.time()))
lat_sorted = sorted(lat)
res = dict(started_at=started, target=BASE, interval_seconds=1, requests=N, succeeded=ok, success_rate_percent=round(100 * ok / N, 3), failures=fails[:20],
           duration_seconds=round(time.time() - t0, 1), latency_seconds=dict(median=round(lat_sorted[N // 2], 4), p95=round(lat_sorted[int(N * .95) - 1], 4), max=round(lat_sorted[-1], 4)),
           health_checks=health_n, health_ok_with_worker_alive=health_ok,
           scope="single container on one Mac, one client, 1 request per second; not a monthly availability measurement")
open(OUT, "w").write(json.dumps(res, ensure_ascii=False, indent=2) + "\n"); print(json.dumps(res, ensure_ascii=False))
