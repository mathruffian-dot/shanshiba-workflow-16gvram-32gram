"""生成前試映（一）：16 宮格分鏡草圖。讀 preview/shots.json，每 16 鏡畫一張 4×4 直式草圖（OpenAI Image 2.5，tools/img25.py），
多張同時生成；鏡號用 PIL 疊在每格左上角（不叫模型寫字，模型會寫錯）。只看故事順序與構圖，不附角色參考圖、不驗角色像不像。
2026-10-23 由原頻道各片的 preview/make_storyboard.py 改成通用版（〈颱風假作業包〉27 鏡 2 張約 3 分鐘）。

shots.json（跟 assemble_read.py 共用；說明見 agent/skills/shanshiba-drama/references/table-read.md）：
  {"cast": "Characters (keep consistent across panels): ...",            # 角色外觀一句話（英文），每張草圖都帶
   "shots": [{"id": "S01", "sec": 3, "panel": "extreme close-up: ...", "lines": [...]}, ...],
   "end_card": "頻道名"}                                                   # 有的話最後補一格空白片尾卡
用法：python tools/make_storyboard.py <片資料夾>/preview/shots.json [--landscape]
  → 同資料夾 storyboard_<k>.png（原圖）＋ storyboard_<k>_label.png（疊鏡號）；--landscape＝16:9 格子"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import img25  # noqa: E402
from fonts import font  # noqa: E402

PER_SHEET = 16


def panels(spec):
    p = [(s["id"], s["panel"]) for s in spec["shots"]]
    if spec.get("end_card"):
        p.append(("END", "a plain dark panel, empty, for an end title card"))
    return [p[i:i + PER_SHEET] for i in range(0, len(p), PER_SHEET)]


def prompt(cast, ps, rows, landscape):
    shape = "horizontal 16:9" if landscape else "vertical 9:16"
    lines = "\n".join(f"Panel {i + 1} (row {i // 4 + 1}, column {i % 4 + 1}): {d}" for i, (_, d) in enumerate(ps))
    return (f"A film storyboard sheet: exactly 4 columns and {rows} rows of equal-sized {shape} panels, separated by thin white gutters, "
            "read left to right, top to bottom. Rough pencil sketch with light watercolor tint, simple and clear staging, cinematic "
            "framing, exaggerated comedic acting. Absolutely NO text, letters, numbers, logos or captions anywhere in the image. "
            f"{cast}\n{lines}")


def make(out_dir, k, cast, ps, landscape):
    rows = (len(ps) + 3) // 4
    stem = out_dir / f"storyboard_{k}"
    files = img25.generate(prompt(cast, ps, rows, landscape), str(stem), n=1, size="1536x1024" if landscape else "1024x1536")
    src = Path(files[0]) if files else stem.with_suffix(".png")
    if src != stem.with_suffix(".png"):
        Image.open(src).save(stem.with_suffix(".png"))
    im = Image.open(src).convert("RGB"); W, H = im.size; d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font("jhbd"), max(18, W // 28))
    for i, (sid, _) in enumerate(ps):
        x, y = (i % 4) * W / 4 + 6, (i // 4) * H / rows + 4
        d.rectangle([x, y, x + W // 9, y + W // 22], fill=(0, 0, 0))
        d.text((x + 4, y), sid, font=f, fill=(255, 220, 120))
    out = out_dir / f"storyboard_{k}_label.png"; im.save(out)
    return out


def main():
    sp = Path(sys.argv[1]).resolve()
    spec = json.loads(sp.read_text(encoding="utf-8"))
    landscape = "--landscape" in sys.argv
    sheets = panels(spec)
    with ThreadPoolExecutor(len(sheets)) as ex:
        for p in ex.map(lambda a: make(sp.parent, a[0] + 1, spec.get("cast", ""), a[1], landscape), enumerate(sheets)):
            print(p, flush=True)
    print(f"{len(spec['shots'])} 鏡 → {len(sheets)} 張草圖。這是看節奏與構圖順序用的草圖，不是首幀。")


if __name__ == "__main__":
    main()
