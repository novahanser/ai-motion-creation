# -*- coding: utf-8 -*-
"""看某几帧里，每台相机前面最近的是哪样东西：往画面上一格格打射线，报每样东西打中了几条、最近多远。只读，不存。

什么时候用：
- 相机贴着东西穿过去，某几帧突然一片暗面、一团白（「谁糊在镜头前面」）；
- 加细分、改形以前：最近不到一个单位的那几帧，那样东西一磨就会换一批挡镜头的帧（blender-3d.md 第 9 节）；
- 改前改后各跑一遍：最近的是谁、多远、几条射线都一样，才算只改了表面。
正交相机也对。

用法: blender -b <工程.blend> --python bl_who_blocks.py -- <帧，如 1,12 或 1-24:3> [--cams 名字,名字] [--grid 7x5] [--only 集合,集合]
  不给 --cams：按时间轴标记找这一帧的相机（没有标记用场景相机）。
  --only：只让这几个顶层集合参加（和渲染时开的一样）；别的集合在内存里关掉视图显示，不存。
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def main():
    a = B.args()
    names = B.pop(a, "--cams")
    grid = B.pop(a, "--grid", "7x5")
    only = B.pop(a, "--only")
    if not a:
        raise SystemExit(__doc__)
    NX, NY = [int(v) for v in grid.lower().split("x")]
    sc = bpy.context.scene
    if only:
        keep = set(only.split(","))
        for c in sc.collection.children:
            c.hide_viewport = c.name not in keep
    marks = B.marker_cameras(sc)
    W, H = B.resolution(sc)
    asp = H / W
    print("==", bpy.data.filepath, "网格 %d×%d" % (NX, NY))
    for f in B.frames(a[0], sc):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        cams = [bpy.data.objects[n] for n in names.split(",")] if names else [B.camera_at(f, marks, sc)]
        for cam in cams:
            ce = cam.evaluated_get(dg)
            mw = ce.matrix_world
            R = mw.to_3x3()
            cd = ce.data
            hits, miss = {}, 0
            for iy in range(NY):
                for ix in range(NX):
                    u, v = (ix + 0.5) / NX - 0.5, 0.5 - (iy + 0.5) / NY
                    if cd.type == "ORTHO":
                        w = cd.ortho_scale
                        o = mw @ Vector((u * w + cd.shift_x * w, v * w * asp + cd.shift_y * w, 0.0))
                        d = (R @ Vector((0, 0, -1))).normalized()
                    else:
                        tr, br, bl, tl = [Vector(p) for p in cd.view_frame(scene=sc)]
                        p = tl + (tr - tl) * (u + 0.5) + (bl - tl) * (0.5 - v)
                        o = mw.translation
                        d = (R @ p).normalized()
                    ok, loc, nrm, idx, ob, mat = sc.ray_cast(dg, o, d)
                    if ok:
                        hits.setdefault(ob.name, []).append((loc - o).length)
                    else:
                        miss += 1
            line = sorted(hits.items(), key=lambda t: (-len(t[1]), min(t[1])))
            near = min(hits.items(), key=lambda t: min(t[1])) if hits else None
            print("帧 %d  %-14s %s  空 %d | 最近：%s" % (
                f, cam.name, "  ".join("%s×%d(%.2f)" % (k, len(v), min(v)) for k, v in line[:6]), miss,
                "%s %.3f" % (near[0], min(near[1])) if near else "-"))


main()
