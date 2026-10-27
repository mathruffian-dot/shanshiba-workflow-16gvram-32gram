"""YuE2 唱詞歌（本機 ComfyUI 原生 YuE2 節點）：一次抽多個 seed，同時存下 YuE2 寫的 ABC 譜。
預設＝templates/song_yue2_v14 的「14 版」配方：melody 規劃模式（只規劃人聲旋律、伴奏自由發揮）、int8 checkpoint。
用法：python yue_song.py <名稱> <角色> --style 風格.txt --lyrics 歌詞.txt --out 輸出資料夾 [--seeds 1,...,12] [--cot melody|full|off] [--ckpt int8|bf16] [--abc 譜] [--secs 150]
輸出 <out>/<角色>_s<seed>.flac 與 .abc；之後用 pick_song.py 只留 144 BPM、依逐句聽寫排序。
環境變數：COMFY_HOST（預設 http://127.0.0.1:8188）、COMFY_DIR（ComfyUI 資料夾，拿輸出檔用）。"""
import argparse, json, os, shutil, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY_OUT = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0")) / "output"
CK = {"int8": "yue2_3b_int8_convrot.safetensors", "bf16": "yue2_3b_bf16.safetensors"}


def req(path, data=None):
    r = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return json.loads(f.read().decode())


def graph(ck, style, lyrics, seed, cot, abc, secs, prefix):
    g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CK[ck]}},
         "3": {"class_type": "EmptyYuE2LatentAudio", "inputs": {"seconds": ["2", 1], "batch_size": 1}},
         "4": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
         "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["4", 0], "latent_image": ["3", 0], "seed": seed,
                                                    "steps": 32, "cfg": 1.0, "sampler_name": "dpm_2", "scheduler": "sgm_uniform", "denoise": 1.0}},
         "6": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
         "7": {"class_type": "SaveAudio", "inputs": {"audio": ["6", 0], "filename_prefix": prefix}}}
    gm = {"clip": ["1", 1], "style": style, "lyrics": lyrics, "seed": seed, "mode": cot if cot != "off" else "full", "max_duration": float(secs),
          "temperature": 1.0, "top_p": 0.95, "top_k": 100, "repetition_penalty": 1.2}
    if cot == "off":
        gm["abc"] = ""; gm["cfg_scale"] = 1.01
    elif abc:
        gm["abc"] = abc
        g["9"] = {"class_type": "PreviewAny", "inputs": {"source": abc}}
    else:
        g["8"] = {"class_type": "YuE2GenerateABC", "inputs": {"clip": ["1", 1], "style": style, "lyrics": lyrics, "seed": seed, "mode": cot, "max_abc_tokens": 8192,
                                                              "temperature": 0.7, "top_p": 0.9, "top_k": 30, "repetition_penalty": 1.005, "penalty_window": 100}}
        gm["abc"] = ["8", 0]
        g["9"] = {"class_type": "PreviewAny", "inputs": {"source": ["8", 0]}}
    g["2"] = {"class_type": "YuE2GenerateMusic", "inputs": gm}
    return g


ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("who")
ap.add_argument("--ckpt", default="int8"); ap.add_argument("--cot", default="melody"); ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10,11,12")
ap.add_argument("--abc"); ap.add_argument("--style", required=True); ap.add_argument("--lyrics", required=True); ap.add_argument("--secs", type=float, default=150)
ap.add_argument("--out", required=True, help="輸出資料夾")
a = ap.parse_args()
style = Path(a.style).read_text(encoding="utf-8").strip()
lyrics = Path(a.lyrics).read_text(encoding="utf-8").strip()
abc = Path(a.abc).read_text(encoding="utf-8") if a.abc else None
od = Path(a.out); od.mkdir(parents=True, exist_ok=True)
(od / "config.json").write_text(json.dumps(vars(a), ensure_ascii=False, indent=1), encoding="utf-8")
for seed in [int(s) for s in a.seeds.split(",")]:
    dest = od / f"{a.who}_s{seed}.flac"
    if dest.exists():
        continue
    pid = req("/prompt", {"prompt": graph(a.ckpt, style, lyrics, seed, a.cot, abc, a.secs, f"audio/YuE2/{a.name}_{a.who}_{seed}")})["prompt_id"]
    t0 = time.time()
    while True:
        time.sleep(2); h = req(f"/history/{pid}")
        if pid in h:
            break
    st = h[pid]["status"]
    if st.get("status_str") == "error":
        print("ERROR", seed, json.dumps(st, ensure_ascii=False)[:1500], flush=True); continue
    for o in h[pid]["outputs"].values():
        for f in o.get("audio") or []:
            shutil.copy2(COMFY_OUT / f.get("subfolder", "") / f["filename"], dest)
        for t in o.get("text") or []:
            (od / f"{a.who}_s{seed}.abc").write_text(t if isinstance(t, str) else json.dumps(t), encoding="utf-8")
    print(a.name, a.who, seed, round(time.time() - t0, 1), "s", flush=True)
