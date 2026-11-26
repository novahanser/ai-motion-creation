# -*- coding: utf-8 -*-
"""命令行渲：几台相机各一份、按标记换相机、只开某几个集合、别的当挡板、宽一点的视野、快门开关。只在内存里改，不存工程。

用法: blender -b <工程.blend> --python bl_render.py -- <输出目录> [选项]
  --frames a-b|a,b,c     渲哪几帧（默认场景的起止）
  --cams 名字,名字        每台相机渲一份，放在 <输出目录>/<相机名>/f####.png
  （不给 --cams）         按时间轴标记一帧一帧换相机，放在 <输出目录>/f####.png；没有标记就用场景相机
  --show 集合,集合        只渲这几个顶层集合（别的顶层集合 hide_render）
  --holdout 集合,集合     这几个集合当挡板：被它们挡住的地方是透明的（单独渲的一层带遮挡，AE 里直接盖上去）
  --pct 50               分辨率百分比；--samples 16：EEVEE / Cycles 的采样
  --blur on|off          动态模糊开关（默认照工程）；--shutter 0.5
  --transparent          背景渲成透明（film_transparent）
  --wide 1.25            视野放宽：分辨率和传感器宽同乘这个数（正交相机乘正交尺度，连关键帧一起），
                         宽图正中那一块和原来的层是同一个画面、同一个像素尺度（补边用）。相机不许有平移、传感器适配要是 AUTO
  --overwrite            已经有的帧也重渲（默认跳过）
  --time                 每帧打印用了几秒
标记上绑的相机会先在内存里解开（不存）：开着动态模糊时，切点那一帧才不会把上一台相机的画面糊进来。
"""
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def widen(cam, k):
    c = cam.data
    if abs(c.shift_x) > 1e-9 or abs(c.shift_y) > 1e-9:
        raise SystemExit("%s 有平移，--wide 不对：先把平移收回 0" % cam.name)
    if c.sensor_fit != "AUTO":
        raise SystemExit("%s 的传感器适配不是 AUTO" % cam.name)
    if c.type == "PERSP":
        for fc in B.fcurves(c):
            if fc.data_path in ("sensor_width", "sensor_fit", "shift_x", "shift_y"):
                raise SystemExit("%s 的 %s 有动画，--wide 不对" % (cam.name, fc.data_path))
        c.sensor_width *= k
        return
    if c.type == "ORTHO":
        fcs = [fc for fc in B.fcurves(c) if fc.data_path == "ortho_scale"]
        if not fcs:
            c.ortho_scale *= k
        for fc in fcs:
            for kp in fc.keyframe_points:
                kp.co[1] *= k
                kp.handle_left[1] *= k
                kp.handle_right[1] *= k
            fc.update()
        return
    raise SystemExit("不认识的相机 " + c.type)


def main():
    a = B.args()
    fr = B.pop(a, "--frames"); cams = B.pop(a, "--cams"); show = B.pop(a, "--show"); hold = B.pop(a, "--holdout")
    pct = B.pop(a, "--pct"); smp = B.pop(a, "--samples"); blur = B.pop(a, "--blur"); shutter = B.pop(a, "--shutter")
    transp = B.pop(a, "--transparent", flag=True); wide = B.pop(a, "--wide"); over = B.pop(a, "--overwrite", flag=True)
    timing = B.pop(a, "--time", flag=True)
    if not a:
        raise SystemExit(__doc__)
    out = a[0]
    sc = bpy.context.scene
    r = sc.render
    marks = B.marker_cameras(sc)
    B.unbind_markers(sc)
    if pct:
        r.resolution_percentage = int(pct)
    if smp:
        if r.engine == "CYCLES":
            sc.cycles.samples = int(smp)
        elif hasattr(sc.eevee, "taa_render_samples"):
            sc.eevee.taa_render_samples = int(smp)
    if blur:
        r.use_motion_blur = blur == "on"
    if shutter:
        r.motion_blur_shutter = float(shutter)
    if transp:
        r.film_transparent = True
    if show:
        keep = set(show.split(","))
        for c in sc.collection.children:
            c.hide_render = c.name not in keep and not any(o.type == "CAMERA" for o in c.all_objects)
    if hold:
        hs = set(hold.split(","))

        def walk(lc):
            if lc.name in hs:
                lc.holdout = True
                lc.collection.hide_render = False
            for ch in lc.children:
                walk(ch)
        walk(bpy.context.view_layer.layer_collection)
    cam_list = [bpy.data.objects[n] for n in cams.split(",")] if cams else None
    if wide:
        k = float(wide)
        r.resolution_x = int(round(r.resolution_x * k))
        r.resolution_y = int(round(r.resolution_y * k))
        done = set()
        for c in (cam_list or [c for _, c in marks] or [sc.camera]):
            if c.name not in done:
                widen(c, k)
                done.add(c.name)
    W, H = B.resolution(sc)
    print("渲 %s：%d×%d，引擎 %s，动态模糊 %s（快门 %.3f），透明 %s" % (out, W, H, r.engine, r.use_motion_blur, r.motion_blur_shutter, r.film_transparent))
    frames = B.frames(fr, sc)
    jobs = []
    if cam_list:
        for c in cam_list:
            jobs += [(c, f, os.path.join(out, c.name, "f%04d.png" % f)) for f in frames]
    else:
        jobs = [(None, f, os.path.join(out, "f%04d.png" % f)) for f in frames]
    n = skip = 0
    t_all = time.time()
    for c, f, path in jobs:
        if os.path.exists(path) and not over:
            skip += 1
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sc.frame_set(f)
        sc.camera = c or B.camera_at(f, marks, sc)
        r.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        n += 1
        if timing:
            print("  f%d %s %.2f 秒" % (f, sc.camera.name, time.time() - t0), flush=True)
    print("渲了 %d 张，跳过已有的 %d 张，用了 %.0f 秒" % (n, skip, time.time() - t_all))


main()
