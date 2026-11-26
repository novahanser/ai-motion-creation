# -*- coding: utf-8 -*-
"""把三维里的位置逐帧导出来，给 AE 里的二维件跟着走（blender-3d.md 第 7 节）。只读，不存。

能导的（像素，渲染尺寸，左上角是原点；相机按时间轴标记找，没有标记用场景相机，也可以用 --cams 指定几台）：
  pos:<物体>      物体原点在画面上的 [x, y, 在不在镜头前 1/-1]
  bbox:<物体>     物体（算完修改器以后）的外接框在画面上的 [左, 上, 右, 下]；整个在镜头后面时是 null
  dist:<物体>     物体原点到相机的距离（米）
  vanish:<相机>   沿一个世界方向（--vanish，默认 0,0,-1）往前、往后很远的一点在画面上的 [x, y, 前见 1/-1, 后见 1/-1]
                  往前、往后两个消失点投到同一处，差的只是哪一个在镜头前面
  roll:<相机>     一条世界轴（--roll-axis，默认 1,0,0）在画面上的角度（度），看滚转
  cam             这一帧用的是哪台相机；travel / travel_sum：主相机这一帧走了几米、一共走了几米
输出 JSON：{"f0": 第一帧, "w": 宽, "h": 高, "fps": …, "<名字>": [逐帧的值]}。
在 AE 中导入 JSON，将图层入点对齐表里的第一帧，再从入点开始索引：
  var d = JSON.parse(footage("track.json").sourceText); var i = timeToFrames(time - inPoint); d["pos:Object"][i]
使用 aerender 出片前，先渲染一帧验证表达式数据的读取结果（pitfalls.md）。
半宽换算：要一个框在画面上跟着三维里某处走、大小也跟着变，半宽（像素）= 焦距的像素数 × 半宽（米）÷ 距离，
焦距的像素数 = 焦距毫米 ÷ 传感器宽 × 画面宽（像素）。

用法: blender -b <工程.blend> --python bl_track.py -- <输出.json> [--frames a-b] [--pos 物体,…] [--bbox 物体,…]
        [--vanish x,y,z] [--roll-axis x,y,z] [--cams 名字,…] [--csv 输出.csv]
"""
import csv
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
FAR = 1.0e5


def main():
    a = B.args()
    fr = B.pop(a, "--frames")
    pos = B.pop(a, "--pos")
    bbox = B.pop(a, "--bbox")
    van = B.pop(a, "--vanish", "0,0,-1")
    rax = B.pop(a, "--roll-axis", "1,0,0")
    cams_opt = B.pop(a, "--cams")
    csv_out = B.pop(a, "--csv")
    if not a:
        raise SystemExit(__doc__)
    out = a[0]
    sc = bpy.context.scene
    W, H = B.resolution(sc)
    fwd = Vector([float(x) for x in van.split(",")]).normalized()
    axis = Vector([float(x) for x in rax.split(",")]).normalized()
    pos = [n for n in (pos or "").split(",") if n]
    bbox = [n for n in (bbox or "").split(",") if n]
    fixed = [bpy.data.objects[n] for n in cams_opt.split(",")] if cams_opt else None
    marks = B.marker_cameras(sc)
    frames = B.frames(fr, sc)
    D = {"f0": frames[0], "w": W, "h": H, "fps": sc.render.fps / sc.render.fps_base, "cam": [], "travel": [], "travel_sum": []}

    def scr(cam, p):
        v = world_to_camera_view(sc, cam, p)
        return v.x * W, (1 - v.y) * H, v.z

    prev, acc = None, 0.0
    for f in frames:
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        cams = fixed or [B.camera_at(f, marks, sc)]
        main_cam = cams[0]
        D["cam"].append(main_cam.name)
        for cam in cams:
            sfx = "" if not fixed else "@" + cam.name
            loc = cam.matrix_world.translation.copy()
            x1, y1, z1 = scr(cam, loc + fwd * FAR)
            x2, y2, z2 = scr(cam, loc - fwd * FAR)
            x, y = (x1, y1) if z1 > 0 else (x2, y2)
            D.setdefault("vanish:" + cam.name, []).append([round(x, 2), round(y, 2), 1 if z1 > 0 else -1, 1 if z2 > 0 else -1])
            cf = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
            p0 = loc + cf * 50.0
            pa, pb = scr(cam, p0), scr(cam, p0 + axis)
            D.setdefault("roll:" + cam.name, []).append(round(math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0])), 3))
            for n in pos:
                ob = bpy.data.objects[n]
                p = ob.matrix_world.translation
                x, y, z = scr(cam, p)
                D.setdefault("pos:" + n + sfx, []).append([round(x, 2), round(y, 2), 1 if z > 0 else -1])
                D.setdefault("dist:" + n + sfx, []).append(round((p - loc).length, 4))
            for n in bbox:
                ev = bpy.data.objects[n].evaluated_get(dg)
                pts = [scr(cam, ev.matrix_world @ Vector(c)) for c in ev.bound_box]
                pts = [q for q in pts if q[2] > 0]
                D.setdefault("bbox:" + n + sfx, []).append(
                    [round(min(q[0] for q in pts)), round(min(q[1] for q in pts)), round(max(q[0] for q in pts)), round(max(q[1] for q in pts))]
                    if pts else None)
        loc = main_cam.matrix_world.translation.copy()
        step = 0.0 if prev is None else (loc - prev).length
        acc += step
        prev = loc
        D["travel"].append(round(step, 4))
        D["travel_sum"].append(round(acc, 3))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(D, fh, ensure_ascii=False)
    print("写了 %s：%d 帧（%d—%d），%s" % (out, len(frames), frames[0], frames[-1], "、".join(k for k in D if isinstance(D[k], list))))
    if csv_out:
        keys = [k for k in D if isinstance(D[k], list)]
        with open(csv_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["frame"] + keys)
            for i, f in enumerate(frames):
                w.writerow([f] + [json.dumps(D[k][i], ensure_ascii=False) if isinstance(D[k][i], list) else D[k][i] for k in keys])
        print("也写了", csv_out)


main()
