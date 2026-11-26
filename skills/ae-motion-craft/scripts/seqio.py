# -*- coding: utf-8 -*-
"""这一份技能里几支脚本共用的小工具：按帧号找序列里的图、读写带中文路径的图、字体。

序列：一个文件夹里的图，文件名里最后一组数字是帧号（f0123.png、主_f0123.exr、shot_123.jpg 都行）。
读图用 np.fromfile + cv2.imdecode，写图用 cv2.imencode + tofile：cv2.imread / imwrite 读写不了中文路径。
"""
import glob
import os
import re

import numpy as np
import cv2

EXTS = ("png", "jpg", "jpeg", "tif", "tiff", "exr", "bmp")
_NUM = re.compile(r"(\d+)\.(%s)$" % "|".join(EXTS), re.I)


def seq_index(d, prefix=None):
    """文件夹里的序列：{帧号: 路径}。prefix 给了就只认文件名以它开头的。"""
    out = {}
    for p in glob.glob(os.path.join(d, "*")):
        b = os.path.basename(p)
        if prefix and not b.startswith(prefix):
            continue
        m = _NUM.search(b)
        if m:
            out[int(m.group(1))] = p
    return out


def frames_of(spec, have=None):
    """「a-b」「a-b:s」「a,b,c」或它们的组合（用逗号连）→ 帧号列表。have 给了就只留有的。"""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if ":" in part:
            part, s = part.split(":")
            step = int(s)
        if "-" in part[1:]:
            i = part.index("-", 1)
            a, b = int(part[:i]), int(part[i + 1:])
            out += list(range(a, b + 1, step))
        else:
            out.append(int(part))
    if have is not None:
        out = [f for f in out if f in have]
    return out


def imread(p, flags=cv2.IMREAD_UNCHANGED):
    if p.lower().endswith(".exr"):
        os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    a = np.fromfile(p, np.uint8)
    return cv2.imdecode(a, flags) if a.size else None


def imwrite(p, im, params=None):
    ext = os.path.splitext(p)[1] or ".png"
    ok, buf = cv2.imencode(ext, im, params or [])
    if not ok:
        raise SystemExit("写不出 " + p)
    buf.tofile(p)


def to_float(im):
    """读进来的图 → float32 0—1，保留通道数。"""
    if im.dtype == np.uint16:
        return im.astype(np.float32) / 65535.0
    if im.dtype == np.uint8:
        return im.astype(np.float32) / 255.0
    return im.astype(np.float32)


def rgba(im):
    """任何读进来的图 → float32 的 BGRA（没有透明通道的当全不透明）。"""
    f = to_float(im)
    if f.ndim == 2:
        f = np.dstack([f, f, f])
    if f.shape[2] == 3:
        f = np.dstack([f, np.ones(f.shape[:2], np.float32)])
    return f


def font(sz):
    from PIL import ImageFont
    for name in ("msyh.ttc", "simhei.ttf", "consolab.ttf", "PingFang.ttc",
                 "NotoSansCJK-Regular.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            pass
    return ImageFont.load_default()
