"""挑歌（YuE2／ACE-Step 唱詞歌）：量每首拍速，只留目標 BPM（YuE2 約一半會掉到 89 或跳 152），
再用 BS-RoFormer 分人聲 → 歌詞強制對齊 → 逐句聽寫，依字對到的比例排序（整首直接聽寫會幻覺，不要用）。
rap 的聽寫天生偏低（人工確認全對的 Suno 歌也只量到 0.63–0.70），最後一定要人聽。
用法：<Voice venv>/python pick_song.py <輸出資料夾> <歌詞.txt> [--bpm 143.6]（歌詞可含 [Verse] 等段落標籤）→ <資料夾>/pick.json
需要：Voice venv 的 faster-whisper、stable-ts、opencc、librosa、audio-separator（模型 model_bs_roformer_ep_317_sdr_12.9755.ckpt）。"""
import re, os, sys, difflib, json
from pathlib import Path
import numpy as np, soundfile as sf, librosa, subprocess
AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))  # AI_ROOT = install root (default C:\AI)
sys.path.insert(0, str(Path(__file__).resolve().parent)); import stt; stt._add_cuda_dll_dirs()
import stable_whisper, opencc
d, lyr = Path(sys.argv[1]), Path(sys.argv[2])
TARGET = float(sys.argv[sys.argv.index("--bpm") + 1]) if "--bpm" in sys.argv else 143.6
lines = [l.strip() for l in lyr.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("[")]
cc = opencc.OpenCC("s2twp"); norm = lambda s: re.sub(r"[^\u4e00-\u9fff]", "", cc.convert(s))
m = stable_whisper.load_faster_whisper("large-v3", device="cuda", compute_type="float16", download_root=str(AI / "Voice" / "models" / "whisper"))
sep = d / "sep"; sep.mkdir(exist_ok=True); rep = {}
for f in sorted(d.glob("*.flac")):
    y, sr = librosa.load(str(f), sr=22050, mono=True)
    bpm = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])
    if abs(bpm - TARGET) > 1:
        print(f.name, "BPM", round(bpm, 1), "→ 不要"); continue
    voc = next(sep.glob(f"{f.stem}_(Vocals)*"), None)
    if voc is None:
        subprocess.run([str(AI / "Voice" / "venv" / "Scripts" / "audio-separator.exe"), str(f), "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                        "--model_file_dir", str(AI / "Voice" / "models" / "separator"), "--output_dir", str(sep), "--output_format", "FLAC"], check=True, capture_output=True)
        voc = next(sep.glob(f"{f.stem}_(Vocals)*"))
    a, vsr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
    res = m.align(str(voc), "\n".join(lines), language="zh", original_split=True); oks = []
    for l, s in zip(lines, res.segments):
        sf.write(d / "_tmp.wav", a[max(0, int((s.start - .3) * vsr)):int((s.end + .3) * vsr)], vsr)
        t = cc.convert("".join(x.text for x in m.transcribe(str(d / "_tmp.wav"), language="zh", vad=False, condition_on_previous_text=False, verbose=None).segments))
        oks.append(sum(b.size for b in difflib.SequenceMatcher(None, norm(l), norm(t), autojunk=False).get_matching_blocks()) / max(1, len(norm(l))))
    rep[f.name] = {"bpm": round(bpm, 1), "char_ok": round(float(np.mean(oks)), 2), "lines_ok": int(sum(o >= .7 for o in oks)), "lines": len(oks)}
    print(f.name, rep[f.name], flush=True)
(d / "_tmp.wav").unlink(missing_ok=True)
(d / "pick.json").write_text(json.dumps(dict(sorted(rep.items(), key=lambda kv: -kv[1]["char_ok"])), ensure_ascii=False, indent=1), encoding="utf-8")
print("排序結果寫在", d / "pick.json")
