@echo off
rem 16GB VRAM + 32GB RAM. Same models as the full version (verified, see docs\hardware.md).
rem Start ComfyUI with --reserve-vram 1.5; run one GPU job at a time; close browsers and other big apps while generating.
rem If VAE decode crashes, add: --disable-pinned-memory --disable-async-offload
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set COMFY_EXTRA_ARGS=--reserve-vram 1.5
echo [profile] 16GB VRAM + 32GB RAM: same models as full version, start ComfyUI with %COMFY_EXTRA_ARGS%. Close other big apps.
