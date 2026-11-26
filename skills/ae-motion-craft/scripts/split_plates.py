# -*- coding: utf-8 -*-
"""把 Blender 渲出来的「版」拆成 AE 里直接能叠的两套图（blender-3d.md 第 3 节）。

渲的时候材质只写两个数：红通道 = 主版的深浅（0 是底，1 最亮），绿通道 = 墨版（1 = 印墨）；透明 = 有没有东西。
色彩管理要设 Raw，数才原样进 PNG。拆成：
  <主版目录>/同名.png   灰度（红通道）+ 原来的透明
  <墨版目录>/同名.png   纯白 + 透明（绿通道 × 原来的透明；AE 里填成墨色）
不要在 AE 里拿绿通道直接当透明：轮廓的抗锯齿在原来的透明里，直接换会出锯齿。
没墨的帧也照样写一张（AE 的序列不能缺帧）。

用法: python -I split_plates.py <渲出来的目录> <主版目录> <墨版目录> [帧，如 1-24] [--value R|G|B] [--ink R|G|B]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
CH = {"B": 0, "G": 1, "R": 2}


def main():
    a = sys.argv[1:]
    opt = {}
    for k in ("--value", "--ink"):
        if k in a:
            i = a.index(k); opt[k] = a[i + 1].upper(); del a[i:i + 2]
    if len(a) < 3:
        raise SystemExit(__doc__)
    src, dv, dk = a[0], a[1], a[2]
    idx = seqio.seq_index(src)
    frames = seqio.frames_of(a[3], idx) if len(a) > 3 else sorted(idx)
    cv, ck = CH[opt.get("--value", "R")], CH[opt.get("--ink", "G")]
    os.makedirs(dv, exist_ok=True)
    os.makedirs(dk, exist_ok=True)
    n = inked = 0
    for f in frames:
        p = idx[f]
        im = seqio.imread(p)
        if im is None or im.ndim != 3 or im.shape[2] != 4:
            print("跳过（不是带透明的四通道图）:", p)
            continue
        mx = 65535 if im.dtype == np.uint16 else 255
        v, k, al = im[..., cv], im[..., ck], im[..., 3]
        blue = np.dstack([v, v, v, al])
        ka = (k.astype(np.uint32) * al.astype(np.uint32) // mx).astype(im.dtype)
        ink = np.dstack([np.full_like(ka, mx)] * 3 + [ka])
        name = os.path.basename(p)
        seqio.imwrite(os.path.join(dv, name), blue)
        seqio.imwrite(os.path.join(dk, name), ink)
        n += 1
        inked += int(ka.max() > 0)
    print("拆了 %d 帧（其中 %d 帧有墨）→ %s、%s" % (n, inked, dv, dk))


if __name__ == "__main__":
    main()
