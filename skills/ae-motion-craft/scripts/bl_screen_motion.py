# -*- coding: utf-8 -*-
"""不看渲出来的图，按几何算「画面里的东西每帧挪多少」。只读，不存。

光流在大位移或低纹理区域可能不稳。这支从相机往画面打一格格射线（blender-3d.md 第 10 节），
把第 f−1 帧打中的点（记在那个物体自己的坐标里）放到第 f 帧重新投到画面上，看挪了多少。物体自己在动也算进去。

输出每帧：打中的占比、挪动的中位（画宽 = 1）、往左挪的占比、几乎不动（< 0.005 画宽）的占比；最后打印各分位。
用法: blender -b <工程.blend> --python bl_screen_motion.py -- <输出.json> [--cam 名字] [--frames a-b] [--grid 32x18] [--only 集合,集合]
  不给 --cam 就按时间轴标记找相机；切点那一帧（前后两帧不是同一台相机）不算。
  --only：只让这几个顶层集合参加（和渲染时一样），别的在内存里关掉。
"""
import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def main():
    a = B.args()
    cam_name = B.pop(a, "--cam")
    fr = B.pop(a, "--frames")
    grid = B.pop(a, "--grid", "32x18")
    only = B.pop(a, "--only")
    if not a:
        raise SystemExit(__doc__)
    out = a[0]
    NX, NY = [int(v) for v in grid.lower().split("x")]
    sc = bpy.context.scene
    if only:
        keep = set(only.split(","))
        for c in sc.collection.children:
            c.hide_viewport = c.name not in keep
    W, H = B.resolution(sc)
    asp = H / W
    marks = B.marker_cameras(sc)
    frames = B.frames(fr, sc)

    def cam_for(f):
        return bpy.data.objects[cam_name] if cam_name else B.camera_at(f, marks, sc)

    def cast(cam, dg):
        ce = cam.evaluated_get(dg)
        mw = ce.matrix_world
        R = mw.to_3x3()
        cd = ce.data
        tr, br, bl, tl = [Vector(p) for p in cd.view_frame(scene=sc)]
        res = []
        for iy in range(NY):
            for ix in range(NX):
                u, v = (ix + 0.5) / NX, (iy + 0.5) / NY
                if cd.type == "ORTHO":           # 正交相机：射线平行，起点铺在画面上
                    w = cd.ortho_scale
                    o = mw @ Vector(((u - 0.5) * w + cd.shift_x * w, (0.5 - v) * w * asp + cd.shift_y * w, 0.0))
                    d = (R @ Vector((0, 0, -1))).normalized()
                else:
                    o = mw.translation
                    d = (R @ (tl + (tr - tl) * u + (bl - tl) * v)).normalized()
                ok, loc, nrm, idx, ob, mat = sc.ray_cast(dg, o, d)
                if ok:
                    res.append((ob.name, ob.evaluated_get(dg).matrix_world.inverted() @ loc, u, 1 - v))
        return res

    rows = []
    for f in frames[1:]:
        c0, c1 = cam_for(f - 1), cam_for(f)
        if c0 != c1:
            rows.append(dict(f=f, cut=True))
            continue
        sc.frame_set(f - 1)
        hits = cast(c1, bpy.context.evaluated_depsgraph_get())
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        mags, dxs = [], []
        for name, pl, u, v in hits:
            ob = bpy.data.objects.get(name)
            if ob is None:
                continue
            c = world_to_camera_view(sc, c1, ob.evaluated_get(dg).matrix_world @ pl)
            if c.z <= 0:
                continue
            dx, dy = c.x - u, (c.y - v) * asp
            dxs.append(dx)
            mags.append(math.hypot(dx, dy))
        mags.sort()
        rows.append(dict(f=f, cam=c1.name, hit=round(len(hits) / (NX * NY), 3),
                         median=round(mags[len(mags) // 2], 5) if mags else None,
                         left=round(sum(d < 0 for d in dxs) / len(dxs), 3) if dxs else None,
                         slow=round(sum(m < 0.005 for m in mags) / len(mags), 3) if mags else None))
        print(f, rows[-1]["median"], flush=True)
    meds = sorted(r["median"] for r in rows if r.get("median") is not None)
    q = (lambda p: meds[min(len(meds) - 1, int(p * len(meds)))]) if meds else (lambda p: None)
    summary = dict(frames=len(rows), cuts=sum(1 for r in rows if r.get("cut")), p10=q(0.1), p50=q(0.5), p90=q(0.9),
                   pixels_p50=round(q(0.5) * W, 1) if meds else None)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dict(file=bpy.data.filepath, grid=[NX, NY], width=W, summary=summary, rows=rows), fh, ensure_ascii=False, indent=0)
    print("每帧挪动的中位（画宽 = 1）：10%% %s，50%% %s（约 %s 像素），90%% %s；切点 %d 个 → %s" % (
        summary["p10"], summary["p50"], summary["pixels_p50"], summary["p90"], summary["cuts"], out))


main()
