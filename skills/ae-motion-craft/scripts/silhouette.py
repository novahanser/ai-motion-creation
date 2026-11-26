# -*- coding: utf-8 -*-
"""把一张平底（纯色或接近纯色的底）的立绘抠成平的剪影：白色 + 透明。只读原图。

做法：从四边往里漫水，颜色和底差得不多的算底；剩下的取最大的一块；外沿收一像素、轻轻羽化。
按背景颜色的变化范围设置容差，在预览中检查轮廓和孔洞。

用法: python -I silhouette.py <原图> <输出.png> [--tol 14] [--pad 12] [--preview 背景色,剪影色]
  --preview：再出一张预览 JPG（默认浅灰底上的深灰剪影：F0F0F0,202020），给了 none 就不出
"""
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def hexbgr(s):
    s = s.strip().lstrip("#")
    r, g, b = [int(s[i:i + 2], 16) for i in (0, 2, 4)]
    return np.array([b, g, r], np.float32)


def main():
    a = sys.argv[1:]
    opt = {"--tol": "14", "--pad": "12", "--preview": "F0F0F0,202020"}
    for k in list(opt):
        if k in a:
            i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    if len(a) < 2:
        raise SystemExit(__doc__)
    src, out = a[0], a[1]
    tol, pad = int(opt["--tol"]), int(opt["--pad"])
    im = seqio.imread(src, cv2.IMREAD_COLOR)
    h, w = im.shape[:2]
    blur = cv2.GaussianBlur(im, (0, 0), 1.0)
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
    step = max(8, min(w, h) // 40)
    seeds = [(x, y) for x in range(0, w, step) for y in (0, h - 1)] + [(x, y) for y in range(0, h, step) for x in (0, w - 1)]
    for s in seeds:
        if mask[s[1] + 1, s[0] + 1] == 0:
            cv2.floodFill(blur, mask, s, (0, 0, 0), (tol,) * 3, (tol,) * 3, flags)
    fg = (mask[1:-1, 1:-1] == 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n < 2:
        raise SystemExit("整张都被当成了底：容差太大，或者底不是平的")
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    fg = (lab == big).astype(np.uint8) * 255
    fg = cv2.erode(fg, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(fg, (0, 0), 0.8)
    x, y, bw, bh = cv2.boundingRect((fg > 0).astype(np.uint8))
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
    out_im = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
    out_im[..., :3] = 255
    out_im[..., 3] = alpha[y0:y1, x0:x1]
    seqio.imwrite(out, out_im)
    print("剪影 %s：%d×%d，占原图 %.1f%%，裁在原图的 (%d, %d)" % (out, out_im.shape[1], out_im.shape[0], 100.0 * (fg > 0).mean(), x0, y0))
    if opt["--preview"].lower() != "none":
        bg, ink = [hexbgr(c) for c in opt["--preview"].split(",")]
        al = out_im[..., 3:4].astype(np.float32) / 255.0
        pv = bg[None, None, :] * (1 - al) + ink[None, None, :] * al
        seqio.imwrite(os.path.splitext(out)[0] + "_预览.jpg", pv.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 90])


if __name__ == "__main__":
    main()
