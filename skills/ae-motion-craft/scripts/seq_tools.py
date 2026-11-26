# -*- coding: utf-8 -*-
"""PNG 序列的几样日常活：出带声音的小样、通览、几段连续帧、任意几张图拼一张、几段接成一条、AE 的无损 AVI 拆回序列。
只读源文件。ffmpeg 不在 PATH 里时，把环境变量 FFMPEG_DIR 指到它所在的目录。

用法:
  video <目录> <帧 a-b> <输出.mp4> [--fps 30] [--w 960] [--audio <音频> --audio-at <序列第一帧对应音频的第几秒>] [--label]
        序列 → mp4（libx264、yuv420p、crf 18）。给了音频就从 --audio-at 秒起截一样长的一段带上。
        --label：左上角标帧号。用 --w 指定预览宽度。
  sheet <目录> <输出.jpg> <帧，如 1-24:3> [--cols 8] [--w 300] [--title 标题]
        通览：每格左上角标帧号。
  rows  <目录> <输出.jpg> <每格宽> <a-b> [<a-b> …]
        几段连续的帧，每段排一行（看单帧、切点前后）。
  grid  <输出.jpg> <列数> <每格宽> <图[::标签]> [<图[::标签]> …]
        任意几张图拼一张（不同尺寸的图按宽缩放、上对齐）。
  join  <输出.mp4> <目录:a-b> [<目录:a-b> …] [--fps 30] [--w 960] [--audio <音频> --audio-at <秒>]
        几段序列按顺序接成一条（看接缝）。
  extract <无损.avi> <PNG 目录> <第一帧的帧号> [--mp4 <输出.mp4> --audio <音频> --audio-at <秒>]
        AE 渲出来的无损 AVI 拆成 f####.png（帧号接着片子的帧号），可以顺手出一条带声音的 mp4。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import cv2
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seqio  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FF = os.environ.get("FFMPEG_DIR", "")
FFMPEG = os.path.join(FF, "ffmpeg") if FF else "ffmpeg"


def pop(a, name, default=None, flag=False):
    if name in a:
        i = a.index(name)
        if flag:
            del a[i]
            return True
        v = a[i + 1]
        del a[i:i + 2]
        return v
    return default


def label(img, text, sz=16):
    d = ImageDraw.Draw(img)
    f = seqio.font(sz)
    w = int(d.textlength(text, font=f)) + 10
    d.rectangle([0, 0, w, sz + 8], fill=(0, 0, 0))
    d.text((5, 2), text, fill=(255, 230, 120), font=f)


def to_pil(p, w=None):
    im = seqio.imread(p, cv2.IMREAD_COLOR)
    if w and im.shape[1] != w:
        im = cv2.resize(im, (w, int(round(im.shape[0] * w / im.shape[1]))), interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))


def encode(tmp, n, out, fps, audio=None, at=0.0):
    cmd = [FFMPEG, "-y", "-v", "error", "-framerate", str(fps), "-i", os.path.join(tmp, "%06d.png")]
    if audio:
        cmd += ["-ss", "%.4f" % at, "-t", "%.4f" % (n / fps), "-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out]
    subprocess.check_call(cmd)


def write_frames(items, tmp, w, lab):
    n = 0
    for p, f in items:
        img = to_pil(p, w)
        if img.width % 2 or img.height % 2:
            img = img.resize((img.width // 2 * 2, img.height // 2 * 2))
        if lab:
            label(img, "f%d" % f)
        img.save(os.path.join(tmp, "%06d.png" % n))
        n += 1
    return n


def cmd_video(a):
    fps = float(pop(a, "--fps", "30")); w = int(pop(a, "--w", "960"))
    audio = pop(a, "--audio"); at = float(pop(a, "--audio-at", "0")); lab = pop(a, "--label", flag=True)
    d, spec, out = a[0], a[1], a[2]
    idx = seqio.seq_index(d)
    frames = seqio.frames_of(spec, idx)
    tmp = tempfile.mkdtemp(prefix="seqvid_")
    try:
        n = write_frames([(idx[f], f) for f in frames], tmp, w, lab)
        encode(tmp, n, out, fps, audio, at)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("写了 %s：%d 帧%s" % (out, n, "，带声音（从 %.3f 秒起）" % at if audio else ""))


def cmd_join(a):
    fps = float(pop(a, "--fps", "30")); w = int(pop(a, "--w", "960"))
    audio = pop(a, "--audio"); at = float(pop(a, "--audio-at", "0")); lab = pop(a, "--label", flag=True)
    out, segs = a[0], a[1:]
    items = []
    for s in segs:
        d, spec = s.rsplit(":", 1)
        idx = seqio.seq_index(d)
        items += [(idx[f], f) for f in seqio.frames_of(spec, idx)]
    tmp = tempfile.mkdtemp(prefix="seqjoin_")
    try:
        n = write_frames(items, tmp, w, lab)
        encode(tmp, n, out, fps, audio, at)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("接好 %s：%d 段、%d 帧" % (out, len(segs), n))


def cmd_sheet(a):
    cols = int(pop(a, "--cols", "8")); w = int(pop(a, "--w", "300")); title = pop(a, "--title")
    d, out, spec = a[0], a[1], a[2]
    idx = seqio.seq_index(d)
    frames = seqio.frames_of(spec, idx)
    tiles = []
    for f in frames:
        t = to_pil(idx[f], w)
        label(t, "f%d" % f, 14)
        tiles.append(t)
    top = 34 if title else 0
    th = tiles[0].height
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 4, top + rows * (th + 4) + 4), (20, 20, 20))
    if title:
        ImageDraw.Draw(sheet).text((8, 6), title, fill=(255, 255, 255), font=seqio.font(20))
    for i, t in enumerate(tiles):
        sheet.paste(t, (4 + (i % cols) * (w + 4), top + 4 + (i // cols) * (th + 4)))
    sheet.save(out, quality=90)
    print(out, len(tiles), "格", sheet.size)


def cmd_rows(a):
    d, out, w = a[0], a[1], int(a[2])
    idx = seqio.seq_index(d)
    lines = []
    for s in a[3:]:
        fs = seqio.frames_of(s, idx)
        ts = []
        for f in fs:
            t = to_pil(idx[f], w)
            label(t, "f%d" % f, 14)
            ts.append(t)
        lines.append(ts)
    th = lines[0][0].height
    ncol = max(len(x) for x in lines)
    sheet = Image.new("RGB", (ncol * (w + 4) + 4, len(lines) * (th + 4) + 4), (20, 20, 20))
    for r, ts in enumerate(lines):
        for c, t in enumerate(ts):
            sheet.paste(t, (4 + c * (w + 4), 4 + r * (th + 4)))
    sheet.save(out, quality=90)
    print(out, sheet.size)


def cmd_grid(a):
    out, cols, w = a[0], int(a[1]), int(a[2])
    tiles = []
    for item in a[3:]:
        p, _, lab = item.partition("::")
        t = to_pil(p, w)
        label(t, lab or os.path.basename(p), 14)
        tiles.append(t)
    rows = (len(tiles) + cols - 1) // cols
    hs = [max(t.height for t in tiles[r * cols:(r + 1) * cols]) for r in range(rows)]
    sheet = Image.new("RGB", (cols * (w + 4) + 4, sum(hs) + 4 * (rows + 1)), (20, 20, 20))
    y = 4
    for r in range(rows):
        for c, t in enumerate(tiles[r * cols:(r + 1) * cols]):
            sheet.paste(t, (4 + c * (w + 4), y))
        y += hs[r] + 4
    sheet.save(out, quality=90)
    print(out, sheet.size)


def cmd_extract(a):
    mp4 = pop(a, "--mp4"); audio = pop(a, "--audio"); at = float(pop(a, "--audio-at", "0")); fps = pop(a, "--fps", "30")
    src, d, first = a[0], a[1], int(a[2])
    os.makedirs(d, exist_ok=True)
    subprocess.check_call([FFMPEG, "-y", "-v", "error", "-i", src, "-start_number", str(first), os.path.join(d, "f%04d.png")])
    n = len(seqio.seq_index(d))
    print("拆了 %s → %s（共 %d 张，从 f%04d 起）" % (src, d, n, first))
    if mp4:
        cmd = [FFMPEG, "-y", "-v", "error", "-i", src]
        if audio:
            cmd += ["-ss", "%.4f" % at, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-r", fps, mp4]
        subprocess.check_call(cmd)
        print("出了", mp4)


def main():
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    cmds = dict(video=cmd_video, join=cmd_join, sheet=cmd_sheet, rows=cmd_rows, grid=cmd_grid, extract=cmd_extract)
    if a[0] not in cmds:
        raise SystemExit(__doc__)
    cmds[a[0]](a[1:])


if __name__ == "__main__":
    main()
