# -*- coding: utf-8 -*-
"""把一个带透明的序列按透明叠到另一个序列上（不开 AE）：单独渲的一层（方框、门、界面件）压到主镜上看效果、出小样。

只是 over：out = 底 × (1 − α) + 上 × α（上面那层当作没有预乘的颜色）。同名帧对同名帧。

用法: python -I alpha_over.py <底的目录> <上面的目录> <输出目录> [帧，如 1-24] [--opacity 1.0]
"""
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def main():
    a = sys.argv[1:]
    op = 1.0
    if "--opacity" in a:
        i = a.index("--opacity"); op = float(a[i + 1]); del a[i:i + 2]
    if len(a) < 3:
        raise SystemExit(__doc__)
    base, over, out = a[0], a[1], a[2]
    ib, io_ = seqio.seq_index(base), seqio.seq_index(over)
    frames = seqio.frames_of(a[3], ib) if len(a) > 3 else sorted(ib)
    os.makedirs(out, exist_ok=True)
    n = miss = 0
    for f in frames:
        if f not in io_:
            miss += 1
            continue
        b = seqio.rgba(seqio.imread(ib[f]))
        t = seqio.rgba(seqio.imread(io_[f]))
        if b.shape[:2] != t.shape[:2]:
            t = cv2.resize(t, (b.shape[1], b.shape[0]), interpolation=cv2.INTER_AREA)
        al = t[..., 3:4] * op
        c = b[..., :3] * (1 - al) + t[..., :3] * al
        outa = np.clip(b[..., 3:4] + al * (1 - b[..., 3:4]), 0, 1)
        im = np.dstack([c, outa]) if b[..., 3].min() < 1 else c
        seqio.imwrite(os.path.join(out, os.path.basename(ib[f])), (np.clip(im, 0, 1) * 255 + 0.5).astype(np.uint8))
        n += 1
    print("叠好 %d 帧 → %s%s" % (n, out, "（上面那层缺 %d 帧，没叠）" % miss if miss else ""))


if __name__ == "__main__":
    main()
