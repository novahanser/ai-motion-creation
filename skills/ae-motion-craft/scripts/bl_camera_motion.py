# -*- coding: utf-8 -*-
"""相机逐帧走了多少：视线转了几度、相机的「上」转了几度（看滚转）、走了几米。只读，不存。

先列出相机链（相机和它上面的父物体）上每条动画曲线的键数和插值，再逐帧算。输出的表给 blur_cover.py 算模糊盖法，
需要估计画面内的位移时，另用 bl_screen_motion.py 测量。

用法: blender -b <工程.blend> --python bl_camera_motion.py -- [<输出.csv>] [--cam 名字] [--frames a-b]
  不给 --cam：按时间轴标记找每一帧的相机（切点那一帧前后不是同一台，记为 cut=1、数照算，用的时候跳过）。
输出列：frame, view_deg, up_deg, move_m, cam, cut
"""
import csv
import math
import os
import sys
from collections import Counter

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def main():
    a = B.args()
    name = B.pop(a, "--cam")
    fr = B.pop(a, "--frames")
    out = a[0] if a else None
    sc = bpy.context.scene
    marks = B.marker_cameras(sc)
    frames = B.frames(fr, sc)
    first = bpy.data.objects[name] if name else B.camera_at(frames[0], marks, sc)
    print("帧 %d—%d，相机 %s，焦距 %.2f mm，动态模糊 %s 快门 %.3f" % (
        frames[0], frames[-1], first.name, first.data.lens, sc.render.use_motion_blur, sc.render.motion_blur_shutter))
    o = first
    while o:
        for fc in B.fcurves(o):
            it = Counter(k.interpolation for k in fc.keyframe_points)
            ks = fc.keyframe_points
            print("  %-18s %s[%d] 键 %d %s 首 %.1f 尾 %.1f" % (o.name, fc.data_path, fc.array_index, len(ks), dict(it), ks[0].co[0], ks[-1].co[0]))
        o = o.parent
    for fc in B.fcurves(first.data):
        print("  镜头参数的动画", fc.data_path, len(fc.keyframe_points), "个键")
    rows, prev = [], None
    for f in frames:
        sc.frame_set(f)
        cam = bpy.data.objects[name] if name else B.camera_at(f, marks, sc)
        mw = cam.matrix_world
        d = (mw.to_3x3() @ Vector((0, 0, -1))).normalized()
        up = (mw.to_3x3() @ Vector((0, 1, 0))).normalized()
        p = mw.translation.copy()
        if prev is None:
            rows.append([f, 0.0, 0.0, 0.0, cam.name, 0])
        else:
            pd, pu, pp, pc = prev
            ang = math.degrees(pd.angle(d)) if pd.dot(d) < 0.9999999 else 0.0
            roll = math.degrees(pu.angle(up)) if pu.dot(up) < 0.9999999 else 0.0
            rows.append([f, round(ang, 4), round(roll, 4), round((p - pp).length, 4), cam.name, int(pc != cam.name)])
        prev = (d, up, p, cam.name)
    if out:
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["frame", "view_deg", "up_deg", "move_m", "cam", "cut"])
            w.writerows(rows)
        print("写了", out)
    body = [r for r in rows[1:] if not r[5]]
    fast = [(r[0], round(r[1], 1)) for r in body if r[1] > 4.0]
    mv = sorted(r[3] for r in body) or [0.0]
    print("视线转得快的帧（> 4°/帧）%d 个：%s" % (len(fast), fast[:40]))
    print("每帧走：中位 %.3f m，最大 %.3f m；切点 %d 个" % (mv[len(mv) // 2], mv[-1], sum(r[5] for r in rows)))


main()
