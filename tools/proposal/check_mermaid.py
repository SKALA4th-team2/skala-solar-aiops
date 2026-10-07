"""기획서의 Mermaid 그림이 문법에 맞고 실제로 그려지는지 헤드리스 Chrome 에서 확인한다.

문서의 ```mermaid 블록을 뽑아, Mermaid 라이브러리(CDN 에서 받는다)로 하나씩 해석하고 그려 본다.
해석에 실패한 블록은 오류 문장을 그대로 적는다. 그린 결과를 눈으로 볼 수 있게 PNG 로도 저장할 수 있다.

GitHub 가 쓰는 Mermaid 의 판과 다를 수 있다. 여기서 통과해도 GitHub 화면에서 한 번 더 본다.

필요한 것: Chrome, websockets 패키지, 인터넷 연결.

실행 (저장소 루트에서):
    python tools/proposal/check_mermaid.py [--png-dir <그림을 저장할 폴더>]
결과: docs/proposal/evidence/mermaid_check.txt. 실패한 블록이 있으면 종료 코드 1
"""
import argparse
import asyncio
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "proposal" / "evidence"
DOCS = sorted((ROOT / "docs" / "proposal").glob("*.md")) + sorted((ROOT / "docs" / "decisions").glob("*.md"))

p = argparse.ArgumentParser()
p.add_argument("--png-dir", type=Path)
p.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
p.add_argument("--port", type=int, default=9334)
p.add_argument("--mermaid", default="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")
a = p.parse_args()

blocks = []
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    for m in re.finditer(r"^```mermaid\n(.*?)^```", text, flags=re.S | re.M):
        line = text[: m.start()].count("\n") + 1
        blocks.append({"doc": str(doc.relative_to(ROOT)), "line": line, "code": m.group(1)})
if not blocks:
    raise SystemExit("Mermaid 블록이 없다")

HTML = """<!doctype html><meta charset="utf-8">
<style>body{margin:16px;font-family:sans-serif;background:#fff} .d{margin:0 0 24px 0;padding:8px;width:1500px}</style>
<div id="out"></div>
<script type="application/json" id="blocks">__BLOCKS__</script>
<script type="module">
  window.__results = []; window.__done = false; window.__fatal = null;
  try {
    const mermaid = (await import("__MERMAID__")).default;
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
    window.__version = "__MERMAID__".replace(/^.*npm\//, "").replace(/\/dist.*$/, "");
    const blocks = JSON.parse(document.getElementById("blocks").textContent);
    for (let i = 0; i < blocks.length; i++) {
      const r = { i, ok: false, type: "", error: "" };
      try {
        const parsed = await mermaid.parse(blocks[i].code);
        r.type = (parsed && parsed.diagramType) || "";
        const { svg } = await mermaid.render("m" + i, blocks[i].code);
        const div = document.createElement("div"); div.className = "d"; div.id = "d" + i; div.innerHTML = svg;
        document.getElementById("out").appendChild(div); document.getElementById("out").appendChild(document.createElement("br"));
        r.ok = true;
      } catch (e) { r.error = String(e && e.message ? e.message : e); }
      window.__results.push(r);
    }
  } catch (e) { window.__fatal = String(e); }
  window.__done = true;
</script>
"""


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="check_mermaid_"))
    page_file = tmp / "page.html"
    page_file.write_text(HTML.replace("__BLOCKS__", json.dumps(blocks, ensure_ascii=False).replace("</", "<\\/")).replace("__MERMAID__", a.mermaid),
                         encoding="utf-8")
    chrome = subprocess.Popen(
        [a.chrome, "--headless=new", f"--remote-debugging-port={a.port}", f"--user-data-dir={tmp / 'profile'}", "--window-size=1400,1000",
         "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--allow-file-access-from-files", "about:blank"],
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
            n = 0

            async def send(method, **params):
                nonlocal n
                n += 1
                mid = n
                await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        return msg.get("result", {})

            async def js(expr):
                r = await send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
                return r.get("result", {}).get("value")

            await send("Page.enable")
            await send("Runtime.enable")
            await send("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1.5, mobile=False)
            await send("Page.navigate", url=page_file.as_uri())
            for _ in range(240):
                await asyncio.sleep(0.25)
                if await js("window.__done === true"):
                    break
            fatal = await js("window.__fatal")
            if fatal:
                raise SystemExit(f"Mermaid 를 불러오지 못했다: {fatal}")
            results = json.loads(await js("JSON.stringify(window.__results)"))
            version = await js("window.__version")
            if a.png_dir:
                a.png_dir.mkdir(parents=True, exist_ok=True)
                for r in results:
                    if not r["ok"]:
                        continue
                    box = json.loads(await js(f"JSON.stringify(document.querySelector('#d{r['i']} svg').getBoundingClientRect())"))
                    clip = {"x": box["x"] + await js("window.scrollX"), "y": box["y"] + await js("window.scrollY"),
                            "width": box["width"], "height": box["height"], "scale": 1}
                    shot = await send("Page.captureScreenshot", format="png", captureBeyondViewport=True, clip=clip)
                    b = blocks[r["i"]]
                    name = f"{Path(b['doc']).stem}_L{b['line']}.png"
                    (a.png_dir / name).write_bytes(base64.b64decode(shot["data"]))
            return results, version
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        shutil.rmtree(tmp, ignore_errors=True)


results, version = asyncio.run(main())
bad = [r for r in results if not r["ok"]]
out = [f"Mermaid {version} 로 해석하고 그렸다. 블록 {len(results)}개 가운데 실패 {len(bad)}개"]
for r in results:
    b = blocks[r["i"]]
    out.append(f"  {'통과' if r['ok'] else '실패'}  {b['doc']}:{b['line']}  {r['type']}" + ("" if r["ok"] else f"\n        {r['error'][:400]}"))
(EVIDENCE / "mermaid_check.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
sys.exit(1 if bad else 0)
