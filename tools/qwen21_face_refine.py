"""Per-character refine for multi-person Qwen-Image 2.1 frames (2026-10-06).

Why: stacking two character LoRAs (e.g. 0.8 + 0.8) dilutes both identities. Instead, generate the composition first,
then for each character crop a box around head + upper body, re-denoise ONLY that crop with that character's LoRA at
1.0 and a single-person prompt, and paste it back with a feathered mask. Everything outside the boxes stays identical.

Usage (H3 venv or any python with Pillow; ComfyUI must be running):
  python qwen21_face_refine.py src.png out.png --box x0 y0 x1 y1 --lora afu_img25_qwen21_768_1600.safetensors
         --prompt "afu_img25, the boy Afu, ..." [--box ... --lora ... --prompt ...] [--denoise 0.55] [--seed 1] [--steps 30]
Boxes are in source-image pixels; each --box needs its own --lora and --prompt (same order).

--turbo (2026-10-12, EXPERIMENTAL): Qwen-Image 2.1 Turbo int8, 8 steps, official Turbo sigma list scaled down to the
start sigma that the original sampler would use at the same --denoise (KSampler simple, 30 steps, shift 0.69), so the
"stay high, land late" shape of the official schedule is kept. Default denoise with --turbo = 0.7 (the test used 0.55,
which matched the original 30-step refine closely; 0.7 is the suggested value for the next round and is NOT verified on
many frames yet). ~10 s for two 1024 crops vs ~18 s. Never use euler/simple 8 steps here: it speckles the faces.
Tested 2026-10-12 on the author's RTX 5090.
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, r"C:\AI\tools")
import gen_image as gi  # noqa: E402

WORK = 1024  # crop is processed at this size (square boxes recommended)
BASE_STEPS = 30  # original refine default; also the reference for converting --denoise to a Turbo start sigma
SIMPLE_SHIFT = 0.69  # ComfyUI's built-in shift for Qwen-Image 2.1 with the simple scheduler


def turbo_start_sigma(denoise, steps=BASE_STEPS, shift=SIMPLE_SHIFT):
    """Start sigma that KSampler(simple, steps, denoise) would use: it builds int(steps/denoise) steps, keeps the last ones."""
    total = int(steps / denoise)
    t = steps / total
    return shift * t / (1 + (shift - 1) * t)


def refine_crop(crop_path, lora, prompt, denoise, seed, steps, w, h, turbo=False):
    p = gi.PRESETS["qwen21-turbo" if turbo else "qwen21"]
    g = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": p["unet"], "weight_dtype": "default"}},
         "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": p["clip"], "type": p["clip_type"], "device": "default"}},
         "3": {"class_type": "VAELoader", "inputs": {"vae_name": p["vae"]}},
         "40": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": 1.0}},
         "10": {"class_type": "LoadImage", "inputs": {"image": gi.stage_image(str(crop_path))}},
         "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["3", 0]}},
         "4": {"class_type": "TextEncodeQwenImage21",
               "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": "blurry, deformed", "resolution": 1024}},
         "6": {"class_type": "KSampler", "inputs": {"model": ["40", 0], "latent_image": ["12", 0], "seed": seed, "steps": steps,
                                                    "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": denoise,
                                                    "positive": ["4", 0], "negative": ["4", 1]}},
         "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
         "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "refine/crop"}}}
    if turbo:  # official Turbo sigmas scaled to the same start point as the original sampler at this denoise
        s0 = turbo_start_sigma(denoise)
        g["60"] = gi.sigmas_node([x * s0 for x in gi.TURBO_SIGMAS])
        g["61"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
        g["6"] = {"class_type": "SamplerCustom", "inputs": {"model": ["40", 0], "latent_image": ["12", 0], "add_noise": True,
                                                           "noise_seed": seed, "cfg": 1.0, "sampler": ["61", 0],
                                                           "sigmas": ["60", 0], "positive": ["4", 0], "negative": ["4", 1]}}
    pid = gi._req(gi.DEFAULT_HOST, "/prompt", {"prompt": g})["prompt_id"]
    while True:
        time.sleep(2)
        hist = gi._req(gi.DEFAULT_HOST, f"/history/{pid}")
        if pid in hist:
            break
    st = hist[pid].get("status", {})
    if st.get("status_str") != "success":
        sys.exit(str(st)[:1500])
    f = hist[pid]["outputs"]["8"]["images"][0]
    return Image.open(gi.COMFY_DIR / "output" / f.get("subfolder", "") / f["filename"]).convert("RGB").resize((w, h), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--box", nargs=4, type=int, action="append", required=True)
    ap.add_argument("--lora", action="append", required=True)
    ap.add_argument("--prompt", action="append", required=True)
    ap.add_argument("--denoise", type=float, default=None, help="default 0.55 (0.7 with --turbo)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=None, help=f"default {BASE_STEPS}; --turbo is fixed at 8")
    ap.add_argument("--turbo", action="store_true", help="EXPERIMENTAL: Qwen-Image 2.1 Turbo, 8 steps, scaled official sigmas")
    a = ap.parse_args()
    if a.turbo:
        if a.steps is not None and a.steps != 8:
            print(f"[warn] --turbo is fixed at 8 steps (scaled official sigmas); ignoring --steps {a.steps}", flush=True)
        a.steps = 8
        a.denoise = 0.7 if a.denoise is None else a.denoise
        print(f"[turbo] EXPERIMENTAL denoise={a.denoise} start_sigma={turbo_start_sigma(a.denoise):.4f}", flush=True)
    else:
        a.steps = BASE_STEPS if a.steps is None else a.steps
        a.denoise = 0.55 if a.denoise is None else a.denoise
    assert len(a.box) == len(a.lora) == len(a.prompt), "each --box needs its own --lora and --prompt"
    img = Image.open(a.src).convert("RGB")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for i, (box, lora, prompt) in enumerate(zip(a.box, a.lora, a.prompt)):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        tmp = out.with_name(f"{out.stem}_crop{i}.png")
        img.crop(box).resize((WORK, round(WORK * h / w / 16) * 16), Image.LANCZOS).save(tmp)
        t0 = time.time()
        new = refine_crop(tmp, lora, prompt, a.denoise, a.seed + i, a.steps, w, h, turbo=a.turbo)
        new.save(out.with_name(f"{out.stem}_crop{i}_refined.png"))
        # feathered mask: full inside, fades over the outer ~12% of the box so the seam disappears
        f = max(8, int(min(w, h) * 0.12))
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rectangle((f, f, w - f, h - f), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(f / 2))
        img.paste(new, (x0, y0), m)
        print(f"[box {i}] {lora} {round(time.time() - t0, 1)}s", flush=True)
    img.save(out)
    print("ok", out)


if __name__ == "__main__":
    main()
