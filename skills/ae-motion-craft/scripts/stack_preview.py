# -*- coding: utf-8 -*-
"""不开 AE，先用 numpy 照打算在 AE 里做的叠法，把几帧叠出来看（几秒出一张拼图）。

做法和 blender-3d.md 第 7 节一样：每一层取灰度和透明，从下往上按混合模式叠在一张中灰的底上，
最后过一道三色调（暗 → 墨，中 → 底色，亮 → 纸白）。正式合成前，用目标工程的色彩设置渲一帧核对。

用法:
  python -I stack_preview.py <输出.jpg> <列数> <每格宽> <帧> --layer <目录>:<模式>:<不透明度>[:灰度系数][:inv][:white] [--layer ...]
        [--ground 0.5] [--tritone 202020,808080,F0F0F0] [--gray] [--save <目录>]
  帧：1,12,24 或 1-24:3
  --layer 从下往上写，可以写好几个；同一个目录可以用不同模式叠几次。
    模式：normal screen overlay softlight hardlight difference multiply lighten darken add
    灰度系数：先把这一层的灰度做这个次方（>1 压暗）；inv：先把灰度反过来；white：这一层只用透明（当一块白）
  --ground：底的灰度，0.5 上色以后正好是中间那个颜色
  --tritone：暗、中、亮三个颜色（十六进制）；--gray：不上色，直接看灰度
  --save：再把每帧整张存成 PNG（原尺寸）

注意：中灰的底上，白的东西用差值翻不动底（0.5 翻过来还是 0.5）；要白，直接垫一层 white。
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

MODES = ("normal", "screen", "overlay", "softlight", "hardlight", "difference", "multiply", "lighten", "darken", "add")


def blend(mode, b, t):
    if mode == "normal":
        return t
    if mode == "screen":
        return 1 - (1 - b) * (1 - t)
    if mode == "multiply":
        return b * t
    if mode == "overlay":
        return np.where(b < 0.5, 2 * b * t, 1 - 2 * (1 - b) * (1 - t))
    if mode == "hardlight":
        return np.where(t < 0.5, 2 * b * t, 1 - 2 * (1 - b) * (1 - t))
    if mode == "softlight":
        return np.where(t < 0.5, b - (1 - 2 * t) * b * (1 - b), b + (2 * t - 1) * (np.sqrt(np.clip(b, 0, 1)) - b))
    if mode == "difference":
        return np.abs(b - t)
    if mode == "lighten":
        return np.maximum(b, t)
    if mode == "darken":
        return np.minimum(b, t)
    if mode == "add":
        return np.clip(b + t, 0, 1)
    raise SystemExit("不认识的模式 %s（可用：%s）" % (mode, " ".join(MODES)))


def hexrgb(s):
    s = s.strip().lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def tritone(G, lo, mid, hi):
    G = np.clip(G, 0, 1)[..., None]
    a = lo * (1 - G * 2) + mid * (G * 2)
    b = mid * (1 - (G - 0.5) * 2) + hi * ((G - 0.5) * 2)
    return np.where(G < 0.5, a, b)


def main():
    args = sys.argv[1:]
    layers, opts = [], {}
    i = 0
    rest = []
    while i < len(args):
        a = args[i]
        if a == "--layer":
            layers.append(args[i + 1]); i += 2
        elif a in ("--ground", "--tritone", "--save"):
            opts[a] = args[i + 1]; i += 2
        elif a == "--gray":
            opts[a] = True; i += 1
        else:
            rest.append(a); i += 1
    if len(rest) < 4 or not layers:
        raise SystemExit(__doc__)
    out, cols, cw, fspec = rest[0], int(rest[1]), int(rest[2]), rest[3]
    ground = float(opts.get("--ground", 0.5))
    lo, mid, hi = [hexrgb(x) for x in opts.get("--tritone", "202020,808080,F0F0F0").split(",")]
    spec = []
    for item in layers:
        # Windows 路径可能含盘符，从右边拆
        q = item.rsplit(":", 5)
        # 找到模式所在的位置
        k = next((j for j, v in enumerate(q) if v in MODES), None)
        if k is None:
            raise SystemExit("--layer 里找不到模式：" + item)
        d = ":".join(q[:k])
        mode = q[k]
        op = float(q[k + 1]) if len(q) > k + 1 else 1.0
        extra = q[k + 2:]
        gam = 1.0
        for e in extra:
            try:
                gam = float(e)
            except ValueError:
                pass
        spec.append(dict(dir=d, mode=mode, op=op, gam=gam, inv="inv" in extra, white="white" in extra, idx=seqio.seq_index(d)))
    frames = seqio.frames_of(fspec)
    tiles = []
    if "--save" in opts:
        os.makedirs(opts["--save"], exist_ok=True)
    for f in frames:
        G = None
        for L in spec:
            p = L["idx"].get(f)
            if p is None or L["op"] <= 0:
                continue
            im = seqio.rgba(seqio.imread(p))
            if G is None:
                G = np.full(im.shape[:2], ground, np.float32)
            v = 0.114 * im[..., 0] + 0.587 * im[..., 1] + 0.299 * im[..., 2]
            v = np.power(np.clip(v, 0, 1), L["gam"])
            if L["white"]:
                v = np.ones_like(v)
            if L["inv"]:
                v = 1 - v
            al = im[..., 3] * L["op"]
            G = G * (1 - al) + blend(L["mode"], G, v) * al
        if G is None:
            print("第 %d 帧哪一层都没有，跳过" % f)
            continue
        rgb = np.repeat(np.clip(G, 0, 1)[..., None], 3, axis=2) if opts.get("--gray") else tritone(G, lo, mid, hi)
        img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
        if "--save" in opts:
            img.save(os.path.join(opts["--save"], "f%04d.png" % f))
        t = img.resize((cw, int(cw * img.height / img.width)), Image.LANCZOS)
        d = ImageDraw.Draw(t)
        d.rectangle([0, 0, 72, 22], fill=(0, 0, 0))
        d.text((4, 1), "f%d" % f, fill=(255, 230, 120), font=seqio.font(16))
        tiles.append(t)
    if not tiles:
        raise SystemExit("一帧都没叠出来：看看目录和帧号对不对")
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0].height
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * 6, rows * th + (rows + 1) * 6), (20, 20, 20))
    for j, t in enumerate(tiles):
        sheet.paste(t, (6 + (j % cols) * (cw + 6), 6 + (j // cols) * (th + 6)))
    sheet.save(out, quality=92)
    print("叠了 %d 帧 → %s %s" % (len(tiles), out, sheet.size))


if __name__ == "__main__":
    main()
