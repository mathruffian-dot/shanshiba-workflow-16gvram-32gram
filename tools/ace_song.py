"""ACE-Step 1.5 XL 唱詞歌（本機 ComfyUI 原生節點；歌曲 Plan C：歌可以用，但人聲帶金屬聲）。
可直接設 BPM／長度／調性／語言，實測每首拍速都照設定（YuE2 約一半會跑掉）。
用法：python ace_song.py <名稱> <角色> --style 標籤.txt --lyrics 歌詞.txt --out 輸出資料夾 [--model xl_sft|xl_turbo] [--seeds 1,2,3,4] [--secs 90] [--bpm 144] [--key "D minor"]
- xl_sft：50 步、cfg 4，5090 約 18–20 秒一首（品質版）；xl_turbo：8 步、cfg 1，約 10 秒。
- 標籤＝英文逗號關鍵字（曲風、配器、人聲、氣氛；BPM／調性不要寫在標籤裡，用參數給）；
  歌詞段落可加修飾，例 [Verse - aggressive]、[Build]、[Chorus - explosive]。
- 試過不要用：給參考音樂（ReferenceTimbreAudio、關掉 LM 音碼）→ 拍速亂、幾乎沒唱詞。
- 只在 ComfyUI 0.40 實測過（XL 權重）。模型清單 setup/downloads_acestep.json。
環境變數：COMFY_HOST（預設 http://127.0.0.1:8188）、COMFY_DIR（ComfyUI 資料夾）。"""
import argparse, json, os, shutil, time, urllib.request
from pathlib import Path

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0"))
M = {"xl_turbo": ("acestep_v1.5_xl_turbo_bf16.safetensors", 8, 1.0), "xl_sft": ("acestep_v1.5_xl_sft_bf16.safetensors", 50, 4.0)}


def req(path, data=None):
    r = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.loads(f.read().decode())


ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("who")
ap.add_argument("--style", required=True); ap.add_argument("--lyrics", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--model", default="xl_sft"); ap.add_argument("--seeds", default="1,2,3,4")
ap.add_argument("--secs", type=float, default=90); ap.add_argument("--bpm", type=int, default=144)
ap.add_argument("--key", default="D minor"); ap.add_argument("--lang", default="zh"); ap.add_argument("--cfg", type=float)
ap.add_argument("--shift", type=float, default=3.0)
a = ap.parse_args()
unet, steps, cfg = M[a.model]; cfg = a.cfg if a.cfg is not None else cfg
tags = Path(a.style).read_text(encoding="utf-8").strip()
lyrics = Path(a.lyrics).read_text(encoding="utf-8").strip()
od = Path(a.out); od.mkdir(parents=True, exist_ok=True)
(od / "config.json").write_text(json.dumps({**vars(a), "unet": unet, "steps": steps, "cfg": cfg}, ensure_ascii=False, indent=1), encoding="utf-8")
for seed in [int(s) for s in a.seeds.split(",")]:
    dest = od / f"{a.who}_s{seed}.flac"
    if dest.exists():
        continue
    g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
         "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": a.shift}},
         "3": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors", "clip_name2": "qwen_4b_ace15.safetensors", "type": "ace", "device": "default"}},
         "4": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
         "5": {"class_type": "TextEncodeAceStepAudio1.5", "inputs": {"clip": ["3", 0], "tags": tags, "lyrics": lyrics, "seed": seed, "bpm": a.bpm, "duration": a.secs,
                                                                     "timesignature": "4", "language": a.lang, "keyscale": a.key, "generate_audio_codes": True,
                                                                     "cfg_scale": 2.0, "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
         "6": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": a.secs, "batch_size": 1}},
         "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
         "8": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["5", 0], "negative": ["7", 0], "latent_image": ["6", 0], "seed": seed,
                                                    "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
         "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
         "10": {"class_type": "SaveAudio", "inputs": {"audio": ["9", 0], "filename_prefix": f"audio/ACE15/{a.name}_{a.who}_{seed}"}}}
    pid = req("/prompt", {"prompt": g})["prompt_id"]; t0 = time.time()
    while True:
        time.sleep(2); h = req(f"/history/{pid}")
        if pid in h:
            break
    st = h[pid]["status"]
    if st.get("status_str") == "error":
        print("ERROR", seed, json.dumps(st, ensure_ascii=False)[:2500], flush=True); continue
    for o in h[pid]["outputs"].values():
        for f in o.get("audio") or []:
            shutil.copy2(COMFY / "output" / f.get("subfolder", "") / f["filename"], dest)
    print(a.name, a.who, seed, round(time.time() - t0, 1), "s", flush=True)
