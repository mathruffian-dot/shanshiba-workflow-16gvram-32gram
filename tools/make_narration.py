"""口播／旁白配音（2026-10-11 作者定案：比一句一句接、固定停頓順很多）。
BreezyVoice 一次念 2–3 句（同一段內併塊）、塊與塊之間的停頓照結尾標點，不再一句一句接、固定停頓。

流程：
  1. 併塊：同一段（sec）內連續的句子併成一塊，最多 MAX_CHARS 字、句號／問號／驚嘆號滿 MAX_SENT 個就切。
  2. 生成：每塊 SEEDS 個候選，兩個程序同時跑（tools\\make_breezyvoice.cmd）。
  3. 挑選：聽寫逐字對（先把簡轉繁假錯「顯卡→顯示卡、消息→訊息、台→臺…」與英文拼法正規化，拼音聲調相同就算對）、
     長度比 ≤1.8（中間夾亂念）、標了注音的字沒被腔調比對標成走音、結尾沒被截斷；都不合格的塊列出來，用 --reroll 重抽。
  4. 切尾巴：用聽寫字級時間找最後一個字，之後還有 >0.35 秒的聲音（BreezyVoice 句尾多念的小字）就切掉。
  5. 串接：塊與塊之間停頓照結尾標點（GAP），換段 SEC_GAP；輸出 narration.wav＋timeline.json（每塊、每句的起訖秒數，給字幕與畫面用）。

輸入 lines.json：[{"id": "L01", "sec": 1, "tts": "配音輸入（可含注音標記 字[:ㄓㄥ1]）", "sub": "字幕"}, ...]（或 {"lines": [...]}）。
用法（Voice venv）：
  C:\\AI\\Voice\\venv\\Scripts\\python.exe tools\\make_narration.py lines.json out_dir --ref ref.wav --ref-text "參考音逐字稿" [--seeds 6]
  …\\make_narration.py lines.json out_dir --ref ref.wav --ref-text "..." --reroll K04,K11 [--seeds 10]   # 指定的塊重抽（舊候選保留，一起比）
  …\\make_narration.py lines.json out_dir --assemble-only                  # 只重新挑選、切尾巴、串接
參考音用你自己有權使用的聲音（10–20 秒、乾淨、平常念句子的語氣）。"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MAX_CHARS, MAX_SENT = 100, 3
GAP = {"。": 0.55, "？": 0.65, "！": 0.55, "：": 0.35, "；": 0.45, "，": 0.3}
SEC_GAP, LEAD, TAIL = 1.0, 0.6, 1.2
CO = re.compile(r"(COLAB|COLLAB|CO-LAB|COLAP|扣LAB|扣賴布|扣辣布|CODELAB|COLDLAB)")
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def plain(t):
    return re.sub(r"\[:[^\]]*\]", "", t)


def chunk_lines(lines):
    nsent = lambda t: max(1, len(re.findall(r"[。？！]", t)))
    chunks, cur = [], []
    for l in lines:
        if cur and (l["sec"] != cur[-1]["sec"] or len(plain("".join(x["tts"] for x in cur + [l]))) > MAX_CHARS
                    or sum(nsent(x["tts"]) for x in cur) >= MAX_SENT):
            chunks.append(cur); cur = []
        cur.append(l)
    if cur:
        chunks.append(cur)
    return [dict(name=f"K{i:02d}", ids=[x["id"] for x in c], sec=c[0]["sec"], tts="".join(x["tts"] for x in c),
                 sub="".join(x.get("sub", plain(x["tts"])) for x in c), parts=[plain(x["tts"]) for x in c]) for i, c in enumerate(chunks, 1)]


def generate(out, chunks, names, seeds, ref, ref_text, tag):
    jobs = [dict(name=k["name"], text=k["tts"], ref_audio=str(ref), ref_text=ref_text, edge_voice="zh-TW-YunJheNeural") for k in chunks if k["name"] in names]
    procs = []
    for i, part in enumerate((jobs[0::2], jobs[1::2])):
        if not part:
            continue
        jf = out / f"jobs_{tag}{i}.json"
        jf.write_text(json.dumps(dict(out_dir=f"bv_{tag}{i}", seeds=seeds, jobs=part), ensure_ascii=False, indent=1), encoding="utf-8")
        procs.append(subprocess.Popen(["cmd", "/c", str(TOOLS / "make_breezyvoice.cmd"), str(jf)], cwd=str(out),
                                      stdout=open(out / f"gen_{tag}{i}.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT))
    for p in procs:
        p.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lines"); ap.add_argument("out")
    ap.add_argument("--ref", help="reference voice wav (required unless --assemble-only)"); ap.add_argument("--ref-text", help="transcript of --ref")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--reroll", help="comma list of chunk names to regenerate (e.g. K04,K11)")
    ap.add_argument("--assemble-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(a.lines).read_text(encoding="utf-8-sig"))
    lines = data["lines"] if isinstance(data, dict) else data
    ref_text = a.ref_text
    if not a.assemble_only and not (a.ref and ref_text):
        ap.error("--ref and --ref-text are required to generate")
    cj = out / "chunks.json"
    chunks = json.loads(cj.read_text(encoding="utf-8")) if cj.exists() else chunk_lines(lines)
    cj.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.reroll:
        names = set(a.reroll.split(",")); n = len(list(out.glob("jobs_r*0.json")))
        print(f"[narration] 重抽 {sorted(names)}（{a.seeds} 個候選）", flush=True)
        generate(out, chunks, names, a.seeds, a.ref, ref_text, f"r{n}")
    elif not a.assemble_only and not list(out.glob("bv_g*")):
        print(f"[narration] {len(lines)} 句 → {len(chunks)} 塊，每塊 {a.seeds} 個候選", flush=True)
        generate(out, chunks, {k["name"] for k in chunks}, a.seeds, a.ref, ref_text, "g")
    assemble(out, chunks)


def assemble(out, chunks):
    import numpy as np
    import soundfile as sf
    sys.path.insert(0, str(TOOLS))
    from breezyvoice_pick import norm, py_same          # noqa: E402
    from stt import _add_cuda_dll_dirs, MODEL_CACHE      # noqa: E402
    _add_cuda_dll_dirs()
    from faster_whisper import WhisperModel              # noqa: E402
    asr = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=str(MODEL_CACHE))

    def fix(t):
        t = plain(t); t = re.sub(r"(\d+)\.(\d+)", r"\1點\2", t)
        for x, y in [("顯示卡", "顯卡"), ("臺", "台"), ("云", "雲"), ("賬", "帳"), ("訊息", "消息"), ("兩百", "二百"), ("它", "他")]:
            t = t.replace(x, y)
        t = norm(t).replace("REPORT", "REPO").replace("CLOUDCODE", "CLAUDECODE").replace("CLOUD", "CLAUDE")
        return CO.sub("扣LAB", t)

    cands = {}                                           # 所有輪次的候選一起比（重抽的不會蓋掉舊的）
    for d in sorted(out.glob("bv_*")):
        pj = d / "picks.json"
        if pj.exists():
            for name, p in json.loads(pj.read_text(encoding="utf-8")).items():
                cands.setdefault(name, []).extend((d, c) for c in p["cands"])
    parts, rep, bad, t = [], [], [], LEAD
    for i, k in enumerate(chunks):
        want = fix(k["tts"]); marked = set(re.findall(r"(.)\[:", k["tts"]))

        def score(dc):
            d, c = dc
            x, sr = sf.read(str(d / "cand" / c["file"]), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
            pk = float(np.abs(x).max()) or 1.0
            tail = float(np.abs(x[-int(0.06 * sr):]).max()) / pk < 0.05
            clean = not any(str(b)[:1] in marked for b in (c.get("tw_bad") or []))
            return (py_same(fix(c["asr"]), want) and c["len_ratio"] <= 1.8, clean, tail, c["tw_score"])
        if k["name"] not in cands:
            sys.exit(f"{k['name']} 沒有候選：先跑生成")
        d, best = max(cands[k["name"]], key=score); sc = score((d, best))
        if not sc[0]:
            bad.append(k["name"])
        src = d / "cand" / best["file"]; x, sr = sf.read(str(src), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
        import librosa
        _, (s0, s1) = librosa.effects.trim(x, top_db=40); x = x[max(0, s0 - int(0.08 * sr)): min(len(x), s1 + int(0.15 * sr))]
        tmp = out / "_tmp.wav"; sf.write(str(tmp), x, sr)
        segs, _ = asr.transcribe(str(tmp), language="zh", beam_size=5, word_timestamps=True, condition_on_previous_text=False)
        ws = [w for s in segs for w in s.words]
        if ws:
            end = float(ws[-1].end)
            if len(x) / sr - end > 0.35 and float(np.abs(x[int((end + 0.1) * sr):]).max(initial=0)) > 0.02:   # 句尾多念的小字
                x = x[: int((end + 0.2) * sr)].copy(); f = int(0.03 * sr); x[-f:] *= np.linspace(1, 0, f)
        if sr != 24000:
            x = librosa.resample(x, orig_sr=sr, target_sr=24000)
        sr = 24000; dur = len(x) / sr
        # 每句的起訖：用字級時間的累計字數對應每句字數（字幕用）
        lens = [len(re.sub(r"[^\w]", "", p)) for p in k["parts"]]; tot = sum(lens) or 1
        wc = [(len(re.sub(r"[^\w]", "", w.word)), float(w.end)) for w in ws]
        line_t, acc, wi, cum, start = [], 0, 0, 0, 0.0
        for j, ln in enumerate(lens):
            acc += ln; target = acc / tot * sum(c for c, _ in wc) if wc else acc / tot
            while wi < len(wc) and cum + wc[wi][0] <= target + 1e-6:
                cum += wc[wi][0]; wi += 1
            e = wc[wi - 1][1] if wi and wc else dur * acc / tot
            if j == len(lens) - 1:
                e = dur
            line_t.append(dict(id=k["ids"][j], start=round(t + start, 3), end=round(t + min(e, dur), 3))); start = min(e, dur)
        end_p = re.sub(r"[」』）\s]+$", "", k["sub"])[-1:]
        gap = SEC_GAP if i + 1 < len(chunks) and chunks[i + 1]["sec"] != k["sec"] else GAP.get(end_p, 0.5)
        parts.append((x, gap if i + 1 < len(chunks) else 0.0))
        rep.append(dict(name=k["name"], ids=k["ids"], sec=k["sec"], start=round(t, 3), end=round(t + dur, 3), pick=f"{d.name}/{best['file']}",
                        ok=sc[0], marked_clean=sc[1], heard=best["asr"], lines=line_t))
        t += dur + parts[-1][1]
    buf = np.concatenate([np.zeros(int(LEAD * 24000), np.float32)] + [np.concatenate([x, np.zeros(int(g * 24000), np.float32)]) for x, g in parts]
                         + [np.zeros(int(TAIL * 24000), np.float32)])
    sf.write(str(out / "narration.wav"), buf, 24000, subtype="PCM_16")
    (out / "_tmp.wav").unlink(missing_ok=True)
    tl = dict(total=round(len(buf) / 24000, 3), chunks=rep, lines=[l for r in rep for l in r["lines"]], needs_reroll=bad)
    (out / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[narration] narration.wav {tl['total']:.1f} 秒；{len(chunks) - len(bad)}/{len(chunks)} 塊聽寫逐字對", flush=True)
    if bad:
        print(f"[narration] 要重抽：--reroll {','.join(bad)} --seeds 10", flush=True)
        for r in rep:
            if not r["ok"]:
                print(f"   {r['name']} 聽到：{r['heard']}", flush=True)
    print("[narration] 交片前：整支再跑一次連續聽寫＋人耳聽一遍（自動檢查抓不到聲調、「額度」這類字常不穩）", flush=True)


if __name__ == "__main__":
    main()
