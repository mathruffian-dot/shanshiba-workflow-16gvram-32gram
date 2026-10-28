"""Breeze TTS 2 常把句尾截斷：最後 60 ms 的最大振幅 / 全句峰值 > 0.05 的候選移到 cand_trunc/，不給挑選工具挑。
用法：python breeze_tailfilter.py bv6"""
import shutil, sys
from pathlib import Path
import numpy as np, soundfile as sf
d = Path(sys.argv[1]); bad = d / "cand_trunc"; bad.mkdir(exist_ok=True); n = 0
for f in sorted((d / "cand").glob("*.wav")):
    a, sr = sf.read(f); a = a if a.ndim == 1 else a.mean(1)
    if np.abs(a[-int(0.06 * sr):]).max() / max(1e-9, np.abs(a).max()) > 0.05:
        shutil.move(str(f), bad / f.name); n += 1
print("truncated moved:", n)
