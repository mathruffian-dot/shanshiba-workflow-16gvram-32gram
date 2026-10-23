"""Seedance 2.5（Kie.ai）分鏡送件：吃 h3_shot.py 同一份分鏡 spec（官方六段格式 JSON），轉成 Seedance 提示詞送 Kie，做好就下載。
2026-10-23 建立（原頻道規定）：**有台詞的鏡一定要給角色參考音；角色真的沒有參考音，才讓 2.5 自己生聲音。**

模式（自動判斷，不用自己選）：
  有台詞＋spec 有 audio.voice_ref（或 audio.fixed）→ 參考模式：首幀當參考圖 1、角色參考音當參考音 1（只學音色、不念參考音的字）。
      Kie 的參考模式不能和首幀模式混用 → 首幀不再釘成第 0 格，提示詞另外要求「照參考圖的構圖開場」。
      原頻道實測（2026-10-23）：構圖與臉幾乎就是首幀；聲音仍由 2.5 重念，但音色被拉向參考音（像參考音 0.63，不給只有約 0.31）。
  有台詞但沒有參考音 → 擋下來報錯。只有 spec 寫 "self_voice": true（＝這個角色沒有參考音）才改成首幀模式、聲音由 2.5 自己生。
  沒有台詞 → 首幀模式（first_frame_url，構圖釘在首幀；不用參考音）。
規格：720p；秒數取整數且 ≥ 4；直式 spec（size 寬<高）參考模式用 9:16、橫式用 16:9，首幀模式用 adaptive。
費用：720p 約 63 點／秒（200 點 ≈ 1 美元）；submit 前先查 Kie 點數，不夠就不送。金鑰：環境變數 KIE_API_KEY（或 KIE_KEY_FILE＝金鑰文字檔路徑）。

用法：
  python sd25_shot.py check  <spec.json ...>                 # 列出每鏡模式、秒數與總點數，不送件
  python sd25_shot.py submit <spec.json ...> --out <資料夾>   # 送件（已送過的鏡跳過），紀錄寫 <資料夾>/tasks.json
  python sd25_shot.py poll   --out <資料夾>                   # 每 20 秒查一次，做好下載成 <資料夾>/<鏡>.mp4
  python sd25_shot.py show   <spec.json>                      # 印出這鏡實際送出的提示詞
  鏡名＝spec 檔所在資料夾名（spec.json）或檔名（S04.json）。"""
import json
import math
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KEY = os.environ.get("KIE_API_KEY") or (Path(os.environ["KIE_KEY_FILE"]).read_text(encoding="utf-8").strip()
                                         if os.environ.get("KIE_KEY_FILE") else "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"   # Kie 會擋沒有瀏覽器 UA 的請求
H = {"Authorization": f"Bearer {KEY}", "User-Agent": UA}


def upload(p):
    """上傳到 Kie 的暫存空間（約 24 小時後刪），回傳下載網址。"""
    if not KEY:
        raise SystemExit("sd25_shot: 先設環境變數 KIE_API_KEY（或 KIE_KEY_FILE＝金鑰文字檔路徑）")
    with open(p, "rb") as f:
        r = requests.post("https://kieai.redpandaai.co/api/file-stream-upload", headers=H,
                          files={"file": (Path(p).name, f)}, data={"uploadPath": "sd25-shot", "fileName": Path(p).name},
                          timeout=120)
    j = r.json()
    if not j.get("success", j.get("code") == 200):
        raise RuntimeError(f"upload {p}: {j}")
    return j["data"]["downloadUrl"]

MODEL = "bytedance/seedance-2-5"
RATE = 63
SHE = ("girl", "woman", "she ", "her ", "mother", "female")


def pronoun(sub):
    return "She" if any(w in (sub.get("desc", "") + " " + sub.get("voice", "")).lower() for w in SHE) else "He"


def name_of(p):
    p = Path(p)
    return p.parent.name if p.name == "spec.json" else p.stem


def lines(s):
    return [d for sh in s.get("shots", []) for d in sh.get("dialogue", [])]


def ref_audio(s):
    a = s.get("audio") or {}
    for k in ("voice_ref", "fixed"):
        if isinstance(a.get(k), dict) and a[k].get("file"):
            return Path(a[k]["file"])
    return None


def mode(s):
    if not lines(s):
        return "first_frame"
    if ref_audio(s):
        return "reference"
    if s.get("self_voice"):
        return "first_frame_selfvoice"
    return "BLOCKED"


def to_prompt(s, md):
    subs = {x["key"]: x for x in s.get("subjects", [])}
    p = []
    if md == "reference":
        spk = subs.get((s.get("audio", {}).get("voice_ref") or {}).get("subject")) or (subs.get(lines(s)[0]["subject"]) if lines(s) else {})
        who = (spk.get("desc", "the speaker").split(",")[0]) if spk else "the speaker"
        p.append("Image 1 is the exact opening frame: start the video from this exact framing, with the same people, the same "
                 f"room and the same lighting. Audio 1 is ONLY a voice-timbre reference for {who}: speak with exactly this voice "
                 "(same timbre, pitch range and Taiwanese accent), but never say any of the words heard in Audio 1; say only the "
                 "line written below.")
    p += [s["style"][0].upper() + s["style"][1:] + ".", "Setting: " + s["setting"] + "."]
    for x in s.get("subjects", []):
        p.append(f"{x['desc'][0].upper() + x['desc'][1:]}.")
    for sh in s.get("shots", []):
        p += [sh.get("action", ""), sh.get("camera", "")]
        for d in sh.get("dialogue", []):
            v = subs.get(d["subject"], {})
            p.append(f"{pronoun(v)} says, in Mandarin with a Taiwanese accent, in {v.get('voice', 'a natural voice')}: 「{d['line']}」 "
                     f"{d.get('after', '')}")
    p += s.get("constraints", [])
    p.append("Sound: " + s.get("soundscape", "") + " No music.")
    return " ".join(x.strip() for x in p if x and x.strip())


def seconds(s):
    return max(4, math.ceil(float(s["duration"])))


def credit():
    return requests.get("https://api.kie.ai/api/v1/chat/credit", headers=H, timeout=60).json().get("data")


def up(path, tag):
    """Kie 上傳會把非 ASCII 檔名去掉、同名可能互蓋 → 複製成 <tag><副檔名> 再傳。"""
    tmp = Path(tempfile.mkdtemp()) / f"{tag}{Path(path).suffix}"
    shutil.copy2(path, tmp)
    return upload(tmp)


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def check(specs):
    total, bad = 0, []
    for p in specs:
        s = load(p); md = mode(s); sec = seconds(s); total += sec if md != "BLOCKED" else 0
        print(f"{name_of(p):8s} {md:22s} {sec} 秒" + (f"  參考音 {ref_audio(s).name}" if md == "reference" else ""))
        if md == "BLOCKED":
            bad.append(name_of(p))
    print(f"合計 {total} 秒 ≈ {total * RATE} 點")
    if bad:
        print(f"⚠ 有台詞但沒有角色參考音：{bad} → spec 加 audio.voice_ref；角色真的沒有參考音才加 \"self_voice\": true")
    return total, bad


def submit(specs, out):
    out.mkdir(parents=True, exist_ok=True)
    tf = out / "tasks.json"
    tasks = json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else {}
    todo = [p for p in specs if not (tasks.get(name_of(p), {}).get("taskId") and tasks[name_of(p)].get("state") != "fail")]
    total, bad = check(todo)
    if bad:
        raise SystemExit("有台詞的鏡沒有角色參考音，不送件（規則見本檔開頭）。")
    c = credit()
    if c is None or c < total * RATE:
        raise SystemExit(f"Kie 剩 {c} 點，這次需要約 {total * RATE} 點 → 先儲值")
    tasks.setdefault("_credit_before", c)
    for p in todo:
        s = load(p); sid = name_of(p); md = mode(s)
        inp = {"prompt": to_prompt(s, md), "resolution": "720p", "duration": seconds(s), "generate_audio": True}
        if md == "reference":
            w, h = s.get("size", [768, 1344])
            inp.update(aspect_ratio="9:16" if w < h else "16:9", reference_image_urls=[up(s["first_frame"], f"{sid}_first")],
                       reference_audio_urls=[up(ref_audio(s), f"{sid}_voice")])
        else:
            inp.update(aspect_ratio="adaptive", first_frame_url=up(s["first_frame"], f"{sid}_first"))
        r = requests.post("https://api.kie.ai/api/v1/jobs/createTask", headers=H, json={"model": MODEL, "input": inp}, timeout=60).json()
        ok = r.get("code") == 200
        print(sid, md, "送出" if ok else f"失敗 {r}", flush=True)
        tasks[sid] = ({"taskId": r["data"]["taskId"], "mode": md, "input": inp, "submitted": time.time()} if ok
                      else {"mode": md, "input": inp, "state": "fail", "failMsg": r})
        tf.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")


def poll(out):
    tf = out / "tasks.json"
    tasks = json.loads(tf.read_text(encoding="utf-8"))
    pending = {k for k, v in tasks.items() if not k.startswith("_") and v.get("taskId") and v.get("state") not in ("success", "fail")}
    while pending:
        for sid in sorted(pending):
            d = requests.get("https://api.kie.ai/api/v1/jobs/recordInfo", headers=H, params={"taskId": tasks[sid]["taskId"]},
                             timeout=60).json().get("data") or {}
            st = d.get("state")
            if st in ("success", "fail"):
                tasks[sid].update(state=st, costTime=d.get("costTime"), credits=d.get("creditsConsumed"), failMsg=d.get("failMsg"))
                if st == "success":
                    url = json.loads(d["resultJson"])["resultUrls"][0]
                    (out / f"{sid}.mp4").write_bytes(urllib.request.urlopen(
                        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300).read())
                    tasks[sid]["file"] = f"{sid}.mp4"
                print(sid, st, d.get("costTime"), d.get("creditsConsumed"), d.get("failMsg") or "", flush=True)
                pending.discard(sid)
        if not pending:
            tasks["_credit_after"] = credit()
        tf.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
        if pending:
            time.sleep(20)
    ok = [k for k, v in tasks.items() if not k.startswith("_") and v.get("state") == "success"]
    print(f"完成 {len(ok)} 鏡；點數 {tasks.get('_credit_before')} → {tasks.get('_credit_after')}", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0]
    out = Path(a[a.index("--out") + 1]) if "--out" in a else None
    specs = [x for x in a[1:] if x.endswith(".json") and (out is None or x != str(out))]
    if cmd == "check":
        check(specs)
    elif cmd == "submit":
        submit(specs, out)
    elif cmd == "poll":
        poll(out)
    elif cmd == "show":
        s = load(specs[0]); print(f"[{mode(s)}]", to_prompt(s, mode(s)))
