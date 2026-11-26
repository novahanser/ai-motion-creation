# -*- coding: utf-8 -*-
"""同一层的两版渲染（改前、改后）逐帧对：核「只改了表面，没动相机和运动」，找坏帧，裁块并排看（blender-3d.md 第 9、10 节）。

三种用法:
  summary <改前目录> <改后目录> [帧]   汇总：盖住的面积、轮廓重合（交/并）、重心挪了多少、亮度差；列出重合最低、重心挪得最多的 8 帧，
                                        和读不到、尺寸不对、改后几乎是空的、轮廓里几乎全黑的帧
  frames  <改前目录> <改后目录> [帧] [--below 0.9]   逐帧列出来（只列重合低于 --below 的）
  crops   <改前目录> <改后目录> <输出.jpg> <帧:x,y> [<帧:x,y> …] [--size 1100x720] [--bg 0.35] [--gamma 1.3]
                                        同一帧各裁一块并排（x,y 是左上角的像素），透明处垫一块灰，看棱磨圆了没有
帧：1-24、1-24:3、6,18；不给就用两边都有的全部帧。

怎么读：
- 加细分会把形往里收一点，重合不会是 1；相机和运动没变的话，每一帧都高而且平稳。
  某一帧突然掉下去，就是那一帧有东西炸开、不见了、或者动画错了位。
- 没改的层应当逐像素一样：亮度差 0、重合 1。
- 轮廓很小的层（远处只有几十个像素）重合会很低，不算数，看面积。
"""
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
W, H = 480, 270


def load_small(p):
    raw = seqio.imread(p) if p else None
    if raw is None:
        return None, None
    size = (raw.shape[1], raw.shape[0])
    return cv2.resize(seqio.rgba(raw), (W, H), interpolation=cv2.INTER_AREA), size


def measure(a, b):
    ma, mb = a[..., 3] > 0.5, b[..., 3] > 0.5
    union = (ma | mb).sum()
    iou = (ma & mb).sum() / union if union else 1.0
    if ma.any() and mb.any():
        ya, xa = np.nonzero(ma)
        yb, xb = np.nonzero(mb)
        shift = float(np.hypot(xa.mean() - xb.mean(), ya.mean() - yb.mean()))
    else:
        shift = 0.0
    la = (a[..., :3] * a[..., 3:4]).mean(axis=2)
    lb = (b[..., :3] * b[..., 3:4]).mean(axis=2)
    return dict(ca=float(ma.mean()), cb=float(mb.mean()), iou=float(iou), shift=shift,
                dl=float(np.abs(la - lb).mean()), lb_in=float(lb[mb].mean()) if mb.any() else 0.0)


def pairs(a_dir, b_dir, spec):
    ia, ib = seqio.seq_index(a_dir), seqio.seq_index(b_dir)
    frames = seqio.frames_of(spec) if spec else sorted(set(ia) | set(ib))
    return ia, ib, frames


def cmd_summary(a_dir, b_dir, spec, below=None, per_frame=False):
    ia, ib, frames = pairs(a_dir, b_dir, spec)
    rows, bad = [], []
    full_w = None
    for f in frames:
        a, sa = load_small(ia.get(f))
        b, sb = load_small(ib.get(f))
        if a is None or b is None:
            bad.append("f%d 读不到：%s%s" % (f, "改前 " if a is None else "", "改后" if b is None else ""))
            continue
        full_w = full_w or sa[0]
        if sa != sb:
            bad.append("f%d 尺寸不一样：改前 %s 改后 %s" % (f, sa, sb))
        m = measure(a, b)
        m["shift"] *= sa[0] / W
        m["f"] = f
        rows.append(m)
        if m["ca"] > 0.02 and m["cb"] < 0.2 * m["ca"]:
            bad.append("f%d 改后几乎是空的：盖住 %.3f → %.3f" % (f, m["ca"], m["cb"]))
        if m["cb"] > 0.02 and m["lb_in"] < 0.01:
            bad.append("f%d 改后轮廓里几乎全黑" % f)
    if not rows:
        print("一帧都没对上：", a_dir, b_dir)
        for s in bad:
            print("  !!", s)
        sys.exit(1)
    if per_frame:
        print("帧 | 盖住 改前→改后 | 重合 | 重心挪（原图像素） | 亮度差")
        for m in rows:
            if below is None or m["iou"] < below:
                print("f%d | %.3f → %.3f | %.3f | %.1f | %.4f" % (m["f"], m["ca"], m["cb"], m["iou"], m["shift"], m["dl"]))
    iou = np.array([m["iou"] for m in rows])
    sh = np.array([m["shift"] for m in rows])
    dl = np.array([m["dl"] for m in rows])
    ca = np.mean([m["ca"] for m in rows]); cb = np.mean([m["cb"] for m in rows])
    print("%s  对  %s：%d 帧" % (a_dir, b_dir, len(rows)))
    print("盖住   改前平均 %.3f   改后平均 %.3f   改后/改前 %.3f" % (ca, cb, cb / max(ca, 1e-6)))
    print("重合   平均 %.3f   最低 %.3f   低于 0.80 的 %d 帧" % (iou.mean(), iou.min(), int((iou < 0.80).sum())))
    print("重心   平均挪 %.1f 像素   最多 %.1f 像素（按原图宽 %d 算）" % (sh.mean(), sh.max(), full_w))
    print("亮度差 平均 %.4f   最多 %.4f" % (dl.mean(), dl.max()))
    order = np.argsort(iou)[:8]
    print("重合最低的 8 帧：", "  ".join("f%d %.3f" % (rows[i]["f"], iou[i]) for i in order))
    order = np.argsort(-sh)[:8]
    print("重心挪得最多的 8 帧：", "  ".join("f%d %.0f" % (rows[i]["f"], sh[i]) for i in order))
    if bad:
        print("要看的：")
        for s in bad:
            print("  !!", s)
    else:
        print("没有读不到的、尺寸不对的、空的、全黑的帧")


def cmd_crops(a_dir, b_dir, out, specs, size="1100x720", bg=0.35, gamma=1.3):
    cw, ch = [int(v) for v in size.lower().split("x")]
    ia, ib = seqio.seq_index(a_dir), seqio.seq_index(b_dir)
    rows = []
    for spec in specs:
        f, xy = spec.split(":")
        x, y = [int(v) for v in xy.split(",")]
        tiles = []
        for idx, tag in ((ia, "before"), (ib, "after")):
            im = seqio.rgba(seqio.imread(idx[int(f)]))
            rgb = im[..., :3] * im[..., 3:4] + bg * (1 - im[..., 3:4])
            crop = np.power(np.clip(rgb[y:y + ch, x:x + cw], 0, 1), gamma)
            t = (crop * 255).astype(np.uint8).copy()
            if t.shape[:2] != (ch, cw):
                pad = np.full((ch, cw, 3), int(bg * 255), np.uint8)
                pad[:t.shape[0], :t.shape[1]] = t
                t = pad
            cv2.putText(t, "f%s %s" % (f, tag), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 220, 255), 2)
            tiles.append(t)
        rows.append(np.hstack(tiles))
    sheet = np.vstack(rows)
    seqio.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(out, sheet.shape[1], "x", sheet.shape[0])


def main():
    a = sys.argv[1:]
    opt = {}
    for k in ("--below", "--size", "--bg", "--gamma"):
        if k in a:
            i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    if len(a) < 3:
        raise SystemExit(__doc__)
    mode = a[0]
    if mode == "summary":
        cmd_summary(a[1], a[2], a[3] if len(a) > 3 else None)
    elif mode == "frames":
        cmd_summary(a[1], a[2], a[3] if len(a) > 3 else None, float(opt.get("--below", 2.0)), per_frame=True)
    elif mode == "crops":
        cmd_crops(a[1], a[2], a[3], a[4:], opt.get("--size", "1100x720"), float(opt.get("--bg", 0.35)), float(opt.get("--gamma", 1.3)))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
