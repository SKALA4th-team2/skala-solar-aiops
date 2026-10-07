"""실행 중인 서버의 대시보드와 API 문서를 실제 브라우저(헤드리스 Chrome)로 열어 화면을 저장한다.

기획서 ⑥(동작 화면 스냅샷)의 캡처를 같은 순서로 다시 찍으려는 도구다. 화면을 꾸미지 않고,
사람이 누르는 버튼과 같은 함수를 브라우저 안에서 부른 뒤 보이는 그대로를 저장한다.
서버 코드는 건드리지 않는다. 업로드 장면은 실제로 파일을 올리므로 그 서버의 최신 업로드가 바뀐다.

필요한 것: Chrome, 그리고 websockets 패키지(uvicorn[standard] 가 함께 설치한다).

실행 (저장소 루트에서, 서버가 떠 있는 상태로):
    python tools/proposal/capture_screens.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/screens \
        --upload datasets/hadong_upload_forecast_jma.csv

저장하는 화면
    01_dashboard_current.png          대시보드 첫 화면
    02_swagger_docs_current.png       API 문서 첫 화면
    03_dashboard_after_upload.png     파일을 올린 뒤 (--upload 를 줬을 때만)
    04_dashboard_normal_batch.png     "정상 배치 전송"을 누른 뒤
    05_dashboard_drift_batch.png      "드리프트 배치 전송"을 누른 뒤
    06_dashboard_log_panel.png        재학습 로그의 aiops.log 를 연 뒤
    07_swagger_predict_expanded.png   API 문서에서 POST /predict 를 펼친 화면
"""
import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

p = argparse.ArgumentParser()
p.add_argument("--base", default="http://127.0.0.1:8077")
p.add_argument("--out", type=Path, required=True)
p.add_argument("--upload", type=Path, help="대시보드로 올릴 CSV. 주지 않으면 업로드 장면을 건너뛴다")
p.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
p.add_argument("--port", type=int, default=9333)
p.add_argument("--batch-wait", type=float, default=180, help="배치 전송의 응답을 기다리는 최대 시간(초). 재학습이 걸리면 오래 걸린다")
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expression, timeout=30.0):
        r = await asyncio.wait_for(
            self.send("Runtime.evaluate", expression=expression, awaitPromise=True, userGesture=True, returnByValue=True), timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(f"{expression}: {r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")

    async def open(self, url, ready="true"):
        await self.send("Page.navigate", url=url)
        for _ in range(100):
            await asyncio.sleep(0.2)
            if await self.js(f"document.readyState === 'complete' && ({ready})"):
                break
        await asyncio.sleep(0.6)

    async def shot(self, name):
        m = await self.send("Page.getLayoutMetrics")
        size = m["cssContentSize"]
        clip = {"x": 0, "y": 0, "width": max(size["width"], 1280), "height": max(size["height"], 600), "scale": 1}
        r = await self.send("Page.captureScreenshot", format="png", captureBeyondViewport=True, clip=clip)
        (a.out / name).write_bytes(base64.b64decode(r["data"]))
        print("저장:", name)


async def main():
    profile = tempfile.mkdtemp(prefix="capture_screens_")
    chrome = subprocess.Popen(
        [a.chrome, "--headless=new", f"--remote-debugging-port={a.port}", f"--user-data-dir={profile}", "--window-size=1280,900",
         "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        target = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/list", timeout=1) as r:
                    target = next(t for t in json.load(r) if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.25)
        if target is None:
            raise SystemExit("Chrome 에 연결하지 못했다")

        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            page = Page(ws)
            for domain in ("Page", "Runtime", "DOM"):
                await page.send(f"{domain}.enable")
            await page.send("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1, mobile=False)

            await page.open(a.base + "/")
            await page.shot("01_dashboard_current.png")

            await page.open(a.base + "/docs", ready="document.querySelectorAll('.opblock').length > 0")
            await page.shot("02_swagger_docs_current.png")

            await page.open(a.base + "/")
            if a.upload:
                doc = await page.send("DOM.getDocument")
                node = await page.send("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="input[type=file]")
                await page.send("DOM.setFileInputFiles", files=[str(a.upload.resolve())], nodeId=node["nodeId"])
                await page.js("uploadFile()")
                await asyncio.sleep(0.5)
                await page.shot("03_dashboard_after_upload.png")

            await page.js("sendBatch('normal')", timeout=a.batch_wait)
            await asyncio.sleep(0.5)
            await page.shot("04_dashboard_normal_batch.png")

            await page.js("sendBatch('drift')", timeout=a.batch_wait)
            await asyncio.sleep(0.5)
            await page.shot("05_dashboard_drift_batch.png")

            await page.js("loadLogFiles()")
            await page.js("openLogFile('aiops.log')")
            await asyncio.sleep(0.5)
            await page.shot("06_dashboard_log_panel.png")

            await page.open(a.base + "/docs", ready="document.querySelectorAll('.opblock').length > 0")
            await page.js("document.querySelector('.opblock-post .opblock-summary-control').click()")
            await asyncio.sleep(1.2)
            await page.shot("07_swagger_predict_expanded.png")
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
