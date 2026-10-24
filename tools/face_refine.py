"""遠景小臉精修（ComfyUI-H3-FaceRefine；2026-10-24 原頻道實測後定為交片前步驟）。

⚠ 實測環境：ComfyUI 0.40、RTX 5090 32GB。本 repo 本機版預設 ComfyUI 0.37 缺 FaceRefine 用到的 `_denoise_mask_conds`，節點仍能跑但未實測（作者說可能出現格狀紋）→ 建議先升級 0.40；16GB 顯卡、Colab 未實測。安裝見 docs/06_安裝.md「遠景小臉精修」。

用法（H3 venv；或 face_refine.cmd 會先確保 ComfyUI 在跑）：
  face_refine.py <鏡資料夾或 clip.mp4> --ref <角色定妝照.png> [--subject 角色key] [--select top_most] [--out 資料夾]
  選項：--track（只追臉、看選到誰就停）  --force（臉 ≥ --max-px 也照修）  --max-px 50  --denoise 0.4  --index 0  --seed 42
        --who "外觀描述"（shot.json 沒有 subjects 時必填）

流程：①追臉（6–9 秒）→ 報告臉高、存 preview.png（裁出來的臉）→ 臉平均高 ≥ --max-px 就停（大臉修了也看不出差，見
2026-10-24 實測：70px 幾乎沒差、25–30px 明顯變清楚）；②逐格裁 512 → FL2VA 剪枝 int8＋fl2v turbo 8 步、er_sde、denoise 0.4
（H3PerFrameDenoise 依臉大小調）、原片音軌鎖住對嘴 → 只把臉羽化貼回。每鏡約 30 秒。
輸出（預設 <鏡資料夾>/facerefine/）：refined.mp4（原尺寸、原音）、preview.png、cropsin.mp4、cropsout.mp4、prompt.txt、report.json。
注意：一次修一張臉；畫面有更大的路人臉時 --select top_most／left_most…（先 --track 確認）；有台詞要人看嘴型；之後照舊 RTX VSR 放大。
實測（原頻道 3 鏡）：臉 25–30 px 從一團糊變成認得出本人、還修掉 H3 畫錯的眼鏡；70 px 幾乎沒差；不閃；嘴大致跟原音。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8188"
COMFY = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0"))  # same convention as h3_shot.py
CLIP = os.environ.get("H3_CLIP", "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors")
SELECTS = ["largest_face", "smallest_face", "left_most", "right_most", "top_most", "bottom_most"]
STYLE = ("Photorealistic cinematic footage shot on ARRI Alexa with anamorphic lenses, 35mm grain, natural skin texture, "
         "soft believable lighting.")


def req(path, data=None):
    r = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data else None,
                               headers={"Content-Type": "application/json"} if data else {})
    return json.loads(urllib.request.urlopen(r).read())


def stage(src, name):
    d = COMFY / "input" / "facerefine"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, d / name)
    return f"facerefine/{name}"


def build_prompt(spec, subject_key, who, seconds):
    subs = spec.get("subjects") or []
    sub = next((s for s in subs if s.get("key") == subject_key), subs[0] if subs else None)
    desc = who or (sub["desc"] if sub else None)
    if not desc:
        sys.exit("shot.json 沒有 subjects：請用 --who 給外觀描述")
    shot = (spec.get("shots") or [{}])[0]
    act = shot.get("action", "").strip()
    lines = [d for d in shot.get("dialogue", []) if not sub or d.get("subject") == sub.get("key")]
    voice = (sub or {}).get("voice", "a natural voice")
    if lines:
        act += " " + " ".join(f"<Subject 1> says in {voice}: \"{d['line']}\" The mouth moves clearly with every syllable." for d in lines)
        act += " After the line the lips close and stay closed."
    else:
        act += " <Subject 1>'s lips stay closed."
    return "\n\n".join([
        f"subject_definitions:\n<Subject 1> is {desc}, shown in <Picture 1>. Use the reference for the identity, facial features, "
        "glasses, hairstyle and clothing.",
        f"summary:\n[reference generation] A {seconds:.1f}-second continuous close-up that follows the face of <Subject 1>. {act}",
        "retention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - preserve the identity, face, glasses, hairstyle and "
        "clothing from <Picture 1>.",
        "detailed_description:\n" + STYLE + " Setting: " + spec.get("setting", "") + ". [Shot 1] The camera holds a tight close-up on the "
        "head and shoulders of <Subject 1>, keeping the face large and sharp in the centre of the frame and following the head as it "
        "moves. " + act + " The face stays the same person the whole time. No captions and no text appear.",
        "overall_soundscape:\n" + (spec.get("soundscape") or "Quiet room tone."),
        "non_diegetic_music:\nN/A",
    ])


def track_nodes(clip_name, a):
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": clip_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "H3FaceTrackCrop", "inputs": {
            "images": ["2", 0], "detector": "face_yolov8m.pt", "confidence": 0.35, "crop_factor": 3.0,
            "canvas_width": 768, "canvas_height": 768, "canvas_mode": "auto_capped_768", "smooth_window": 21,
            "size_smooth_window": 51, "smooth_method": "gaussian", "size_mode": "per_frame",
            "select": a.select, "select_index": a.index, "fallback_detector": "none", "cut_detection": "none"}},
    }


def save(g, nid, images, tag, kind, audio=None):
    g[f"{nid}a"] = {"class_type": "CreateVideo", "inputs": dict({"images": images, "fps": 24}, **({"audio": audio} if audio else {}))}
    g[f"{nid}b"] = {"class_type": "SaveVideo", "inputs": {"video": [f"{nid}a", 0], "filename_prefix": f"facerefine/{tag}_{kind}",
                                                          "format": "mp4", "codec": "h264"}}


def run(g, tag, out):
    pid = req("/prompt", {"prompt": g})["prompt_id"]
    while True:
        time.sleep(3)
        h = req(f"/history/{pid}")
        if pid in h:
            break
    e = h[pid]
    st = e.get("status", {})
    if st.get("status_str") != "success":
        sys.exit("ComfyUI 失敗：" + json.dumps([m for m in st.get("messages", []) if m[0] == "execution_error"], ensure_ascii=False)[:2000])
    texts = {}
    for nid, o in e["outputs"].items():
        for v in (o.get("images") or []) + (o.get("videos") or []):
            fn = v["filename"]
            if fn.endswith(".mp4") and fn.startswith(tag + "_"):
                kind = fn[len(tag) + 1:].split("_")[0]
                shutil.copy2(COMFY / "output" / v.get("subfolder", "") / fn, out / f"{kind}.mp4")
        if "text" in o:
            texts[nid] = o["text"][0] if isinstance(o["text"], list) else o["text"]
    return texts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shot")
    ap.add_argument("--ref", required=False)
    ap.add_argument("--subject")
    ap.add_argument("--who")
    ap.add_argument("--select", default="largest_face", choices=SELECTS)
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--out")
    ap.add_argument("--track", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-px", type=float, default=50)
    ap.add_argument("--denoise", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        ver = req("/system_stats")["system"].get("comfyui_version", "0")
        if tuple(int(x) for x in re.findall(r"\d+", ver)[:2]) < (0, 40):
            print(f"[warn] ComfyUI {ver} < 0.40：FaceRefine 只在 0.40 實測過（見檔頭）", flush=True)
    except Exception:
        pass
    p = Path(a.shot)
    clip = p / "clip.mp4" if p.is_dir() else p
    spec_p = clip.parent / "shot.json"
    spec = json.loads(spec_p.read_text(encoding="utf-8")) if spec_p.exists() else {}
    out = Path(a.out) if a.out else clip.parent / "facerefine"
    out.mkdir(parents=True, exist_ok=True)
    tag = f"fr_{clip.parent.name}_{int(time.time())}"
    clip_name = stage(clip, f"{tag}.mp4")

    # ① 追臉
    g = track_nodes(clip_name, a)
    save(g, "90", ["3", 0], tag, "cropsin")
    g["94"] = {"class_type": "PreviewAny", "inputs": {"source": ["3", 3]}}
    rep = run(g, tag, out)["94"]
    (out / "track_report.txt").write_text(rep, encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(out / "cropsin.mp4"), "-frames:v", "1", str(out / "preview.png")])
    mh = re.search(r"face height\s+min=(\d+)px\s+mean=(\d+)px\s+max=(\d+)px", rep)
    mean_px = float(mh.group(2)) if mh else 0
    found = re.search(r"face=(\d+) \((\d+)%\)", rep)
    print(f"[track] select={a.select} 臉高 平均 {mean_px:.0f}px（{mh.group(0) if mh else '?'}）偵測到 {found.group(2) if found else '?'}% 格；"
          f"裁切預覽 {out / 'preview.png'}", flush=True)
    if a.track:
        return
    if mean_px >= a.max_px and not a.force:
        print(f"[skip] 臉平均 {mean_px:.0f}px ≥ {a.max_px:.0f}px：修了看不出差（要修加 --force）")
        return
    if not a.ref:
        sys.exit("--ref 必填（角色定妝照）")

    # ② 精修
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)],
                               capture_output=True, text=True).stdout)
    prompt = build_prompt(spec, a.subject, a.who, dur)
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    g = track_nodes(clip_name, a)
    g.update({
        "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "11": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "13": {"class_type": "LoadImage", "inputs": {"image": stage(Path(a.ref), f"{tag}_ref{Path(a.ref).suffix}")}},
        "14": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["10", 0], "prompt": prompt, "width": ["3", 4], "height": ["3", 5], "length": ["3", 6],
            "ref_image_size": "match", "vae": ["11", 0], "audio_vae": ["12", 0], "ref_images.ref_image_0": ["13", 0]}},
        "15": {"class_type": "H3InjectVideoLatent", "inputs": {"av_latent": ["14", 1], "images": ["3", 0], "vae": ["11", 0]}},
        "20": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "21": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["20", 0], "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength_model": 1.0}},
        "22": {"class_type": "ModelAttentionBackend", "inputs": {"model": ["21", 0], "attention": "comfy kitchen attention"}},
        "23": {"class_type": "MiniMaxH3NativeAudioLock", "inputs": {"model": ["22", 0], "av_latent": ["15", 0], "audio_vae": ["12", 0], "audio": ["2", 1]}},
        "24": {"class_type": "H3PerFrameDenoise", "inputs": {
            "model": ["23", 0], "av_latent": ["23", 1], "transform": ["3", 1], "denoise_multiplier_small_face": 1.0,
            "denoise_multiplier_large_face": 0.35, "scale_mode": "absolute_px", "face_px_small": 30.0, "face_px_large": 120.0,
            "gamma": 1.0, "smooth_frames": 9}},
        "25": {"class_type": "BasicGuider", "inputs": {"model": ["24", 2], "conditioning": ["14", 0]}},
        "26": {"class_type": "BasicScheduler", "inputs": {"model": ["24", 2], "scheduler": "simple", "steps": 8, "denoise": a.denoise}},
        "27": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "er_sde"}},
        "28": {"class_type": "RandomNoise", "inputs": {"noise_seed": a.seed}},
        "29": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["28", 0], "guider": ["25", 0], "sampler": ["27", 0], "sigmas": ["26", 0], "latent_image": ["24", 0]}},
        "30": {"class_type": "VAEDecode", "inputs": {"samples": ["29", 0], "vae": ["11", 0]}},
        "31": {"class_type": "H3FaceStitch", "inputs": {
            "base_images": ["2", 0], "refined_crops": ["30", 0], "transform": ["3", 1], "paste_region": "face_only",
            "mask_dilation": 24, "feather": 24, "colour_match": 1.0, "blend": 1.0, "undetected_frames": "fade_out"}},
        "47": {"class_type": "PreviewAny", "inputs": {"source": ["24", 1]}},
    })
    save(g, "40", ["31", 0], tag, "refined", audio=["2", 1])
    save(g, "42", ["30", 0], tag, "cropsout")
    (out / "workflow_api.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    t0 = time.time()
    texts = run(g, tag, out)
    (out / "report.json").write_text(json.dumps({"track": rep, "denoise": texts.get("47"), "select": a.select, "ref": a.ref,
                                                 "clip": str(clip), "seconds": round(time.time() - t0, 1)}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"[ok] {time.time() - t0:.0f}s → {out / 'refined.mp4'}")


if __name__ == "__main__":
    main()
