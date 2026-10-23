"""生成前試映（二）：把讀本台詞照鏡表排成時間軸，配 16 宮格草圖做成試映影片，量出實際片長。
2026-10-23 由原頻道各片的 preview/assemble_read.py 改成通用版。讀 preview/shots.json（格式見 make_storyboard.py 開頭）：
  每鏡 lines＝[{"text": "台詞原文（念的字，不含說話者）", "caption": "字幕"}]；
  或舊做法 [{"wav": "台詞音檔（相對 shots.json）", "caption": "字幕"}]；兩者都沒有的只顯示字幕（群眾聲、音效、字卡說明）。
⭐ 2026-10-23 起預設「文字讀本」：台詞由 H3 拿角色參考音自己念，讀本不用先做 TTS。有 text 沒 wav 的句子用字數估長度：
  試映畫面停留＝字數 ÷ READ_CPS＋0.3 秒（照一般語速，給人看節奏）；
  建議 H3 鏡長 h3_sec＝max(3, 該鏡台詞字數 ÷ H3_CPS＋H3_PAD)（每秒 3 字＋2 秒：H3 有時晚 1.5–2.1 秒才開口，再留反應尾巴；
  原頻道 7 句實測全部在這個長度內念完，最緊的 13 字句算出 6.3 秒、實際念到 6.16 秒）。多出來的空白剪接時裁掉。
  字數＝中文字＋英數字，不含標點。
每鏡長度＝max(鏡表秒數 sec, 台詞總長＋前 0.25＋每句後 0.3 秒)。草圖格子用 storyboard_<k>_label.png（每 16 鏡一張，依鏡在
shots 裡的順序對應；改劇本刪鏡後要沿用舊格子，可在鏡上寫 "panel_index": 舊序號，從 0 起算）。
輸出（同資料夾）：讀本.wav（文字讀本時是靜音）、讀本_timeline.json（每鏡 dur、h3_sec）、讀本試映.mp4（720×1280）、_frames/。
用法：python tools/assemble_read.py <片資料夾>/preview/shots.json"""
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fonts import font  # noqa: E402

SR = 24000
W, H = 720, 1280
PER_SHEET = 16
READ_CPS = 4.0                  # 文字讀本：試映畫面的一般語速（字／秒）
H3_CPS, H3_PAD, H3_MIN = 3.0, 2.0, 3.0   # 建議 H3 鏡長＝字數 ÷ 3＋2 秒，最短 3 秒


def nchars(t):
    return len(re.findall(r"[一-鿿A-Za-z0-9]", t or ""))


def load(p):
    if not p.exists():
        return None
    a = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True, check=True).stdout
    return np.frombuffer(a, np.int16).astype(np.float32) / 32768


def panel(here, i, n_total):
    k, j = i // PER_SHEET + 1, i % PER_SHEET
    lab = here / f"storyboard_{k}_label.png"
    if not lab.exists():
        return None
    nrows = (min(PER_SHEET, n_total - (k - 1) * PER_SHEET) + 3) // 4
    im = Image.open(lab).convert("RGB"); w, h = im.size
    raw = here / f"storyboard_{k}.png"
    g = np.asarray(Image.open(raw if raw.exists() else lab).convert("L")) > 235    # 用白色格線切（列高不一定等分）

    def cuts(frac, n):
        runs = []
        for x in (x for x, v in enumerate(frac) if v > 0.9):
            if runs and x == runs[-1][1] + 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
        edges = [0] + [x for a, b in runs for x in (a, b + 1)] + [n]
        return [(edges[t], edges[t + 1]) for t in range(0, len(edges), 2) if edges[t + 1] - edges[t] > 20]
    rows, cols = cuts(g.mean(1), h), cuts(g.mean(0), w)
    if len(rows) != nrows or len(cols) != 4:
        rows = [(int(h * t / nrows), int(h * (t + 1) / nrows)) for t in range(nrows)]
        cols = [(int(w * t / 4), int(w * (t + 1) / 4)) for t in range(4)]
    (y0, y1), (x0, x1) = rows[j // 4], cols[j % 4]
    return im.crop((x0, y0, x1, y1))


def frame(here, idx, n_total, sid, caps, end_card):
    bg = Image.new("RGB", (W, H), (12, 12, 16)); d = ImageDraw.Draw(bg)
    pn = panel(here, idx, n_total) if sid != "END" else None
    if pn:
        r = min((W - 40) / pn.width, 980 / pn.height); pn = pn.resize((int(pn.width * r), int(pn.height * r)), Image.LANCZOS)
        bg.paste(pn, ((W - pn.width) // 2, 60))
    elif sid == "END":
        d.text((W // 2, 520), end_card or "", font=ImageFont.truetype(font("jhbd"), 50), fill=(255, 214, 120), anchor="mm")
    d.text((24, 1070), sid, font=ImageFont.truetype(font("jhbd"), 36), fill=(120, 230, 255))
    y, f = 1120, ImageFont.truetype(font("jhbd"), 28)
    for c in caps:
        while c:
            seg, c = c[:23], c[23:]
            d.text((24, y), seg, font=f, fill=(240, 240, 240)); y += 38
    return bg


def main():
    sp = Path(sys.argv[1]).resolve(); here = sp.parent
    spec = json.loads(sp.read_text(encoding="utf-8"))
    shots = list(spec["shots"])
    if spec.get("end_card"):
        shots.append({"id": "END", "sec": 2, "lines": [{"caption": f"〔片尾〕{spec['end_card']}"}]})
    n_total = len(shots)
    vid = here / "_frames"; vid.mkdir(exist_ok=True)
    audio, tl, concat, t = [], [], [], 0.0
    for i, s in enumerate(shots):
        lines = s.get("lines", [])
        has_vo = any(x.get("wav") or x.get("text") for x in lines)
        seg = [np.zeros(int(0.25 * SR), np.float32)] if has_vo else []
        caps, missing = [], []
        spoken = sum(nchars(x.get("text")) for x in lines if x.get("text"))
        for x in lines:
            caps.append(x.get("caption", ""))
            if not x.get("wav"):
                if x.get("text"):          # 文字讀本：照字數留時間（靜音）
                    seg += [np.zeros(int((nchars(x["text"]) / READ_CPS + 0.3) * SR), np.float32)]
                continue
            a = load(here / x["wav"])
            if a is None:
                missing.append(x["wav"]); a = np.zeros(int(0.22 * SR * len(x.get("caption", ""))), np.float32)
            seg += [a, np.zeros(int(0.3 * SR), np.float32)]
        seg = np.concatenate(seg) if seg else np.zeros(0, np.float32)
        dur = max(float(s.get("sec", 2)), len(seg) / SR + 0.05)
        seg = np.concatenate([seg, np.zeros(int(dur * SR) - len(seg), np.float32)])
        audio.append(seg)
        h3_sec = max(H3_MIN, float(s.get("sec", 0)), spoken / H3_CPS + H3_PAD) if spoken else float(s.get("sec", 2))
        tl.append(dict(shot=s["id"], start=round(t, 2), dur=round(dur, 2), table_sec=s.get("sec"), chars=spoken,
                       h3_sec=round(h3_sec * 2 + 0.499) / 2, missing=missing))
        fp = vid / f"{s['id']}.png"
        frame(here, s.get("panel_index", i), n_total, s["id"], caps, spec.get("end_card")).save(fp)
        concat += [f"file '{fp.as_posix()}'", f"duration {dur:.3f}"]
        t += dur
    concat.append(f"file '{(vid / (shots[-1]['id'] + '.png')).as_posix()}'")
    y = np.concatenate(audio)
    with wave.open(str(here / "讀本.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    (here / "讀本_timeline.json").write_text(json.dumps(dict(total=round(t, 2), shots=tl), ensure_ascii=False, indent=1), encoding="utf-8")
    (vid / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vid / "list.txt"), "-i", str(here / "讀本.wav"),
                    "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    str(here / "讀本試映.mp4")], check=True)
    longest = sorted(tl, key=lambda x: -x["dur"])[:3]
    print(f"總長 {t:.1f} 秒；缺音 {sum(len(x['missing']) for x in tl)} 句")
    print("最長三鏡：", [(x["shot"], x["dur"]) for x in longest])
    print("超出鏡表秒數：", [(x["shot"], x["table_sec"], x["dur"]) for x in tl if x["table_sec"] and x["dur"] > x["table_sec"] + 0.1])
    print("超過 12 秒（要拆）：", [x["shot"] for x in tl if x["dur"] > 12 or x["h3_sec"] > 12])
    print("建議 H3 鏡長（台詞字數 ÷ 3＋2 秒）：", [(x["shot"], x["h3_sec"]) for x in tl if x["chars"]])


if __name__ == "__main__":
    main()
