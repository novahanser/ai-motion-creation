# -*- coding: utf-8 -*-
"""动态模糊只开在拍上和转头处：在 Blender 里给快门按帧打常量键（blender-3d.md 第 5 节）。做完另存，打开的工程不动。

快门（render.motion_blur_shutter）：
  拍上：离最近的拍点（往前，容半帧）0、1、2 帧时开 --pulse（默认 0.5、0.3、0.12）
  转头：视线每帧转过 a° 起开，往 b° 线性涨，封顶 m（--turn a:b:m，默认 6:36:0.5）
  两样取大；其余关（写 0.001）。常量插值，一帧一个键。
门槛提高时，快门激活的帧会减少。修改运镜后重新计算。

用法: blender -b <工程.blend> --python bl_shutter.py -- --beat <第一拍的帧>:<一拍几帧> --save <存成.blend>
        [--frames a-b] [--cam 名字] [--pulse 0.5,0.3,0.12] [--turn 6:36:0.5]
  不给 --cam 就按时间轴标记找相机；切点那一帧不按转头算。
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def main():
    a = B.args()
    beat = B.pop(a, "--beat"); save = B.pop(a, "--save"); fr = B.pop(a, "--frames"); cam_name = B.pop(a, "--cam")
    pulse = [float(x) for x in B.pop(a, "--pulse", "0.5,0.3,0.12").split(",")]
    ta, tb, tm = [float(x) for x in B.pop(a, "--turn", "6:36:0.5").split(":")]
    if not beat or not save:
        raise SystemExit(__doc__)
    b0, bl = [float(x) for x in beat.split(":")]
    sc = bpy.context.scene
    marks = B.marker_cameras(sc)
    frames = B.frames(fr, sc)
    for fc in B.fcurves(sc):
        if fc.data_path.endswith("motion_blur_shutter"):
            while len(fc.keyframe_points):
                fc.keyframe_points.remove(fc.keyframe_points[0])
    sc.render.use_motion_blur = True
    prev, prev_cam, shut = None, None, {}
    for f in frames:
        sc.frame_set(f)
        cam = bpy.data.objects[cam_name] if cam_name else B.camera_at(f, marks, sc)
        d = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
        ang = 0.0 if prev is None or cam != prev_cam else math.degrees(prev.angle(d))
        prev, prev_cam = d, cam
        k = math.floor((f - b0) / bl)
        nb = min((f - (b0 + j * bl) for j in (k - 1, k, k + 1) if f - (b0 + j * bl) >= -0.5), default=99)
        i = int(round(nb))
        p = pulse[i] if 0 <= i < len(pulse) and nb < len(pulse) - 0.5 else 0.0
        t = min(tm, max(0.0, (ang - ta) / (tb - ta)) * tm) if tb > ta else 0.0
        shut[f] = max(p, t)
    for f, v in shut.items():
        sc.render.motion_blur_shutter = max(v, 0.001)
        sc.render.keyframe_insert("motion_blur_shutter", frame=f)
    for fc in B.fcurves(sc):
        if fc.data_path.endswith("motion_blur_shutter"):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
            fc.update()
    on = sum(1 for v in shut.values() if v > 0.01)
    print("快门打开的帧 %d / %d（拍上 %s，转头 %g°/帧起、%g°/帧到顶 %g）" % (on, len(shut), pulse, ta, tb, tm))
    B.save_copy(save)


main()
