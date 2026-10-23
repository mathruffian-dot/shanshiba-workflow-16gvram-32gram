"""Turn a reference video into a gray 3D-mannequin ("white model") video for H3 motion transfer  (added 2026-10-14).

Pipeline (ComfyUI 0.37 core nodes only, no custom nodes):
  source video -> person detection (1 person: RT-DETR v4 boxes; 2+ people: SAM 3.1 video tracking, stable identities)
  -> MoGe-3 field of view (from the first frame) -> SAM 3D Body pose -> face expression -> temporal smoothing -> mesh render.
Then use the result as the H3 motion reference: in the h3_shot.py spec put
  "camera_video": {"file": "<white model>.mp4", "kind": "motion"}
(see docs/02).  Tested 2026-10-14: on a dance clip this beat
SDPose skeleton control (arm shape, hook kick, crossed landing, timing) on 2 seeds; 124 frames render in ~25 s.

Only use reference footage you are allowed to use; the source is for motion only and never appears in the final film.

Usage (H3 venv):  C:\\AI\\H3\\venv\\Scripts\\python.exe tools\\make_whitemodel.py SRC.mp4 --out OUT.mp4
  --start 13.72 --frames 124       trim (seconds / frame count at 24 fps; frames should be 17n+5 to match an H3 shot length)
  --crop W:H:X:Y                   crop the source first (pixels of the source), e.g. to match the character's place in the first frame
  --size 1280x704                  output size (default: cropped source size); use the H3 shot size
  --people 2                       number of people to track (default 1)
  --bg black | 206,206,208         background (default black; a light gray plate is needed for h3_edit.py swaps)
  --overlay                        also write OUT_overlay.mp4 (mesh over the source) to check the fit
  --colors blue,red                one fixed color per tracked person (needs custom node setup/comfy_nodes/whitemodel_color, 2026-10-15);
                                   prints which side of frame 0 each color starts on, so the shot spec can say "the blue mannequin is ..."
Needs ComfyUI >= 0.37 running (tools\\start_comfy.cmd) and the models from setup/downloads_whitemodel.json:
  models/detection/sam_3d_body_dinov3_bf16.safetensors, models/geometry_estimation/moge_3_vitg_fp16.safetensors,
  models/diffusion_models/rt_detr_v4-x-hgnet_fp16.safetensors, models/checkpoints/sam3.1_multiplex_fp16.safetensors
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import h3_shot as H


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True).stdout.strip()
    return tuple(int(x) for x in r.split(","))


def main():
    ap = argparse.ArgumentParser(description="reference video -> gray mannequin video (SAM 3D Body) for H3 motion transfer")
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--frames", type=int)
    ap.add_argument("--crop")
    ap.add_argument("--size")
    ap.add_argument("--people", type=int, default=1)
    ap.add_argument("--bg", default="black")
    ap.add_argument("--overlay", action="store_true")
    ap.add_argument("--colors")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tag = f"wm_{int(time.time())}"

    # 1. normalise the source: 24 fps, trim, crop, scale
    vf = ["fps=24"]
    if a.crop:
        w, h, x, y = a.crop.split(":")
        vf.append(f"crop={w}:{h}:{x}:{y}")
    if a.size:
        W, Hh = (int(v) for v in a.size.lower().split("x"))
        vf.append(f"scale={W}:{Hh}")
    prep = out.with_name(out.stem + "_src24.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a.start), "-i", a.src, "-vf", ",".join(vf), "-an", "-c:v", "libx264", "-crf", "14"]
    if a.frames:
        cmd += ["-frames:v", str(a.frames)]
    subprocess.run(cmd + [str(prep)], check=True)
    W, Hh = probe(prep)
    src_name = H.stage(prep, f"{tag}_src.mp4")
    prep.unlink()

    g = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": src_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "5": {"class_type": "SAM3DBody_Loader", "inputs": {"model_file": "sam_3d_body_dinov3_bf16.safetensors"}},
        "6": {"class_type": "LoadMoGeModel", "inputs": {"model_name": "moge_3_vitg_fp16.safetensors"}},
        "7": {"class_type": "ImageFromBatch", "inputs": {"image": ["2", 0], "batch_index": 0, "length": 1}},
        "8": {"class_type": "MoGeInference", "inputs": {"moge_model": ["6", 0], "image": ["7", 0], "resolution_level": 9, "fov_x_degrees": 0.0,
              "batch_size": 1, "force_projection": True, "apply_mask": True, "refine_steps": 3}},
        "9": {"class_type": "MoGeGeometryToFOV", "inputs": {"moge_geometry": ["8", 0], "axis": "vertical", "unit": "degrees"}},
        "10": {"class_type": "SAM3DBody_Predict", "inputs": {"sam3d_body_model": ["5", 0], "image": ["2", 0], "run_hand_refinement": True,
               "fov": ["9", 0], "batch_size": 64}},
        "11": {"class_type": "SAM3DBody_FaceExpression", "inputs": {"sam3d_body_model": ["5", 0], "mhr_pose_data": ["10", 0], "image": ["2", 0],
               "strength": 1.0, "mouth_strength": 1.0, "eye_strength": 2.0, "brow_strength": 2.0, "input_threshold": 0.02,
               "blendshape_smooth_window": 7}},
        "12": {"class_type": "SAM3DBody_Smooth", "inputs": {"mhr_pose_data": ["11", 0], "strength": 1.0, "method": "gaussian", "window": 7,
               "rotation_threshold_degrees": 20.0}},
        "19": {"class_type": "PreviewAny", "inputs": {"source": ["9", 0]}},
    }
    if a.people <= 1:
        g["3"] = {"class_type": "UNETLoader", "inputs": {"unet_name": "rt_detr_v4-x-hgnet_fp16.safetensors", "weight_dtype": "default"}}
        g["4"] = {"class_type": "RTDETR_detect", "inputs": {"model": ["3", 0], "image": ["2", 0], "threshold": 0.5, "class_name": "person",
                  "max_detections": 1}}
        g["10"]["inputs"]["bboxes"] = ["4", 0]
    else:  # stable identities across frames for fights / duets
        g["3"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sam3.1_multiplex_fp16.safetensors"}}
        g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 1], "text": "person"}}
        g["13"] = {"class_type": "SAM3_VideoTrack", "inputs": {"images": ["2", 0], "model": ["3", 0], "detection_threshold": 0.5,
                   "max_objects": a.people, "detect_interval": 1, "conditioning": ["4", 0]}}
        g["10"]["inputs"]["track_data"] = ["13", 0]

    def render(nid, bg_node, opacity, prefix):
        g[nid] = {"class_type": "SAM3DBody_Render", "inputs": {"pose_data": ["12", 0], "width": W, "height": Hh, "render_style": "mesh",
                  "render_style.shader": "default", "render_style.opacity": opacity, "render_style.person_palette_falloff": 0.6,
                  "render_style.region": "full_body"}}  # region is required in the API although the UI hides it
        if bg_node:
            g[nid]["inputs"]["background"] = bg_node
        g[nid + "v"] = {"class_type": "CreateVideo", "inputs": {"images": [nid, 0], "fps": 24}}
        g[nid + "s"] = {"class_type": "SaveVideo", "inputs": {"video": [nid + "v", 0], "filename_prefix": f"whitemodel/{tag}_{prefix}",
                        "format": "mp4", "codec": "h264"}}

    bg = None
    if a.bg != "black":
        from PIL import Image
        rgb = tuple(int(v) for v in a.bg.split(","))
        plate = out.with_name(out.stem + "_plate.png")
        Image.new("RGB", (W, Hh), rgb).save(plate)
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": H.stage(plate, f"{tag}_plate.png")}}
        plate.unlink()
        g["21"] = {"class_type": "GetImageSize", "inputs": {"image": ["2", 0]}}
        g["22"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["20", 0], "amount": ["21", 2]}}
        bg = ["22", 0]
    render("30", bg, 1.0, "mesh")
    if a.colors:  # per-person colors (track order) via the whitemodel_color custom node
        g["30"] = {"class_type": "SAM3DBody_RenderColored", "inputs": {"pose_data": ["12", 0], "width": W, "height": Hh, "colors": a.colors}}
        if bg:
            g["30"]["inputs"]["background"] = bg
    if a.overlay:
        render("40", ["2", 0], 0.85, "overlay")

    t0 = time.time()
    pid = H.req("/prompt", {"prompt": g})["prompt_id"]
    while True:
        time.sleep(3)
        h = H.req(f"/history/{pid}")
        if pid in h:
            break
    e = h[pid]
    if e.get("status", {}).get("status_str") != "success":
        print(json.dumps(e.get("status", {}), ensure_ascii=False)[:3000])
        sys.exit(1)
    for nid, dst in (("30s", out), ("40s", out.with_name(out.stem + "_overlay.mp4"))):
        if nid in e["outputs"]:
            v = (e["outputs"][nid].get("images") or e["outputs"][nid].get("videos"))[0]
            shutil.copy2(H.COMFY / "output" / v.get("subfolder", "") / v["filename"], dst)
            print(f"[ok] {dst}")
    if a.colors and out.exists():
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        f0 = np.frombuffer(raw, np.uint8).reshape(Hh, W, 3).astype(int)
        ref = {"blue": (0, 0, 1), "red": (1, 0, 0), "green": (0, 1, 0), "magenta": (1, 0, 1), "cyan": (0, 1, 1), "yellow": (1, 1, 0)}
        sat = f0.max(-1) - f0.min(-1)
        for c in [x.strip() for x in a.colors.split(",")]:
            if c not in ref:
                continue
            hi = np.array(ref[c]) == 1
            m = (sat > 60) & (f0[..., hi].min(-1) - f0[..., ~hi].max(-1) > 40)  # pixel clearly in that hue
            if m.sum() > 50:
                print(f"  frame 0: {c:8s} x={np.nonzero(m)[1].mean() / W:.2f}  ({'left' if np.nonzero(m)[1].mean() < W / 2 else 'right'})")
            else:
                print(f"  frame 0: {c:8s} not visible")
    print(f"fov(vertical)={e['outputs'].get('19', {}).get('text', ['?'])[0]}  people={a.people}  {W}x{Hh}  {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
