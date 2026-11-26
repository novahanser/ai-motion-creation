# -*- coding: utf-8 -*-
"""只读地看一个 Blender 工程（不存）：用于编辑前检查结构、曲线和相机。

用法: blender -b <工程.blend> --python bl_inspect.py -- <模式> [参数]
  scene                         渲染设置、时间轴标记和绑的相机、相机链、每个物体在世界里的范围、修改器、有没有动画和驱动器、
                                节点组里引用的物体和集合
  objects <名字,名字> [--frame F]  修改器的参数；修改器算完以后的网格：顶点、面、范围、总面积、平滑着色占比、
                                五条边以上的面（ngon）、连着 7 条边以上的顶点（加细分前看「用极限曲面」会不会很慢）
  faces [--frame F] [--prefix 甲,乙]  每样东西算完以后的面数、平滑占比、修改器一串（按面数排；名字去掉末尾编号合并）
  nodes <节点组名>               节点组的接口、每个节点没连线的输入值、连线
  keys <物体名,物体名>           这些物体（连同它们的数据）上的每条动画曲线：键数、插值、首尾帧和值；修改器上的动画、指向已经不在的修改器的动画
  instances [--frame F] [--axis z] [--bin 250]   几何节点撒出来的实例：每个物体撒了多少、沿一个轴每段有几个
  camera <帧,帧…> [--cam 名字]   相机在这几帧的位置、朝向、焦距（不给 --cam 就按标记，没有标记用场景相机）
"""
import math
import os
import sys
from collections import Counter

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()
sc = bpy.context.scene


def r3(v, n=2):
    return tuple(round(x, n) for x in v)


def world_range(ob, dg):
    ev = ob.evaluated_get(dg)
    try:
        bb = [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    except Exception as e:
        return "范围? %s" % e
    xs, ys, zs = [v.x for v in bb], [v.y for v in bb], [v.z for v in bb]
    return "x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def cmd_scene(a):
    r = sc.render
    print("文件", bpy.data.filepath)
    print("场景", sc.name, "帧", sc.frame_start, "—", sc.frame_end, "fps", r.fps / r.fps_base, "引擎", r.engine,
          "分辨率", r.resolution_x, r.resolution_y, "%d%%" % r.resolution_percentage, "胶片透明", r.film_transparent)
    print("动态模糊", r.use_motion_blur, "快门", round(r.motion_blur_shutter, 3), "色彩管理", sc.view_settings.view_transform,
          "Look", sc.view_settings.look, "曝光", sc.view_settings.exposure, "输出", r.filepath)
    for attr in ("taa_render_samples", "use_raytracing"):
        if hasattr(sc.eevee, attr):
            print("  EEVEE", attr, getattr(sc.eevee, attr))
    if r.engine == "CYCLES":
        print("  Cycles 采样", sc.cycles.samples, "降噪", sc.cycles.use_denoising)
    print("场景相机", sc.camera.name if sc.camera else None)
    for m in sorted(sc.timeline_markers, key=lambda m: m.frame):
        print("  标记", m.frame, m.name, "→", m.camera.name if m.camera else "")
    cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
    for c in cams:
        chain, o = [], c
        while o:
            chain.append(o.name)
            o = o.parent
        print("  相机", c.name, "%s %.1f mm" % (c.data.type, c.data.lens), "链", " ← ".join(chain),
              "平移", r3((c.data.shift_x, c.data.shift_y), 3), "动画", bool(B.fcurves(c)))
    sc.frame_set(sc.frame_start)
    dg = bpy.context.evaluated_depsgraph_get()
    print("物体（第 %d 帧）" % sc.frame_start)
    for ob in bpy.data.objects:
        anim, drv = len(B.fcurves(ob)), len(B.drivers(ob))
        colls = ",".join(c.name for c in ob.users_collection)
        if ob.type in ("CAMERA", "LIGHT", "EMPTY"):
            print("  %-6s %-24s 位置 %s 父 %s 曲线 %d 驱动 %d [%s]" % (
                ob.type, ob.name, r3(ob.matrix_world.translation, 1), ob.parent.name if ob.parent else "-", anim, drv, colls))
            continue
        mods = []
        for md in ob.modifiers:
            s = md.type + ("" if md.show_render else "(渲染关)")
            if md.type == "NODES" and md.node_group:
                s += ":" + md.node_group.name
            mods.append(s)
        print("  %-6s %-24s %s 不渲 %s 修改器 %s 曲线 %d 驱动 %d [%s]" % (
            ob.type, ob.name, world_range(ob, dg), ob.hide_render, " → ".join(mods) or "-", anim, drv, colls))
    for ng in bpy.data.node_groups:
        for nd in ng.nodes:
            if nd.type in ("OBJECT_INFO", "COLLECTION_INFO"):
                v = nd.inputs[0].default_value if nd.inputs and hasattr(nd.inputs[0], "default_value") else None
                print("  节点组", ng.name, nd.type, getattr(v, "name", v))
    for tag, idb in B.owners():
        for d in B.drivers(idb):
            for var in d.driver.variables:
                for t in var.targets:
                    if t.id:
                        print("  驱动", tag, d.data_path, "←", t.id.name, t.data_path)


def eval_mesh(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        nv, nf = len(me.vertices), len(me.polygons)
        area = sum(p.area for p in me.polygons)
        smooth = sum(1 for p in me.polygons if p.use_smooth) / max(1, nf)
        ngon = sum(1 for p in me.polygons if p.loop_total > 4)
        tri = sum(1 for p in me.polygons if p.loop_total == 3)
        val = Counter()
        for e in me.edges:
            val[e.vertices[0]] += 1
            val[e.vertices[1]] += 1
        high = sum(1 for k, v in val.items() if v >= 7)
        co = [v.co for v in me.vertices]
        rng = ([round(min(p[i] for p in co), 2) for i in range(3)], [round(max(p[i] for p in co), 2) for i in range(3)]) if co else None
        return dict(nv=nv, nf=nf, area=area, smooth=smooth, ngon=ngon, tri=tri, high=high, rng=rng)
    finally:
        ev.to_mesh_clear()


def cmd_objects(a):
    f = int(B.pop(a, "--frame", sc.frame_start))
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for nm in a[0].split(","):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            print("没有", nm)
            continue
        base = ob.data
        print("== %s（第 %d 帧）缩放 %s 原网格 顶点 %s 面 %s" % (nm, f, r3(ob.matrix_world.to_scale(), 3),
              len(base.vertices) if hasattr(base, "vertices") else "-", len(base.polygons) if hasattr(base, "polygons") else "-"))
        for m in ob.modifiers:
            d = {}
            for k in ("levels", "render_levels", "subdivision_type", "use_limit_surface", "thickness", "use_replace", "offset",
                      "angle", "factor", "deform_method", "deform_axis", "strength", "steps", "render_steps", "screw_offset",
                      "width", "use_bisect_axis", "iterations"):
                if hasattr(m, k):
                    v = getattr(m, k)
                    d[k] = round(v, 4) if isinstance(v, float) else v
            print("   %-22s %-14s %s%s" % (m.name, m.type, d, "" if m.show_render else "（渲染关）"))
        if ob.type == "MESH":
            e = eval_mesh(ob, dg)
            print("   算完以后：顶点 %d 面 %d（三角 %d、五边以上 %d）连 7 条边以上的顶点 %d 平滑 %.0f%% 总面积 %.2f 范围 %s" % (
                e["nv"], e["nf"], e["tri"], e["ngon"], e["high"], 100 * e["smooth"], e["area"], e["rng"]))


def cmd_faces(a):
    f = int(B.pop(a, "--frame", sc.frame_start))
    pre = B.pop(a, "--prefix")
    pre = tuple(pre.split(",")) if pre else None
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    rows, tot = {}, 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" or (pre and not ob.name.startswith(pre)):
            continue
        e = eval_mesh(ob, dg)
        key = ob.name.rstrip("0123456789").rstrip("_.")
        mods = " → ".join("%s%s" % (m.type, (":%d" % m.render_levels) if m.type == "SUBSURF" else "") for m in ob.modifiers)
        r = rows.setdefault(key, [0, 0, 0.0, 0, mods])
        r[0] += 1; r[1] += e["nf"]; r[2] += e["smooth"]; r[3] += e["high"]
        tot += e["nf"]
    print("第 %d 帧，算完以后的面一共 %d" % (f, tot))
    for key, (n, nf, sm, high, mods) in sorted(rows.items(), key=lambda t: -t[1][1]):
        print("  %-22s ×%-4d 面 %9d 平滑 %3.0f%% 7 边以上的顶点 %6d | %s" % (key, n, nf, 100 * sm / n, high, mods))


def cmd_nodes(a):
    ng = bpy.data.node_groups.get(a[0])
    if ng is None:
        raise SystemExit("没有这个节点组：" + a[0])
    print("== 节点组", ng.name, ng.bl_idname)
    for it in ng.interface.items_tree:
        if getattr(it, "item_type", "") == "SOCKET":
            print("  接口", it.in_out, it.name, getattr(it, "default_value", ""))
    for nd in ng.nodes:
        vals = []
        for s in nd.inputs:
            if s.is_linked or not hasattr(s, "default_value"):
                continue
            v = s.default_value
            try:
                v = tuple(round(x, 3) for x in v)
            except TypeError:
                v = round(v, 3) if isinstance(v, float) else getattr(v, "name", v)
            vals.append("%s=%s" % (s.name, v))
        extra = "".join(" %s=%s" % (k, getattr(nd, k)) for k in ("operation", "data_type", "domain", "mode") if hasattr(nd, k))
        print("  %-22s %-28s%s | %s" % (nd.type, nd.name, extra, "; ".join(vals)[:400]))
    for lk in ng.links:
        print("  连", lk.from_node.name, lk.from_socket.name, "→", lk.to_node.name, lk.to_socket.name)


def cmd_keys(a):
    for nm in a[0].split(","):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            print("没有", nm)
            continue
        print("==", nm, "修改器", " → ".join("%s:%s" % (m.name, m.type) for m in ob.modifiers) or "-")
        for tag, idb in (("物体", ob), ("数据", ob.data)):
            if idb is None:
                continue
            for fc in B.fcurves(idb):
                ks = sorted(fc.keyframe_points, key=lambda k: k.co[0])
                it = Counter(k.interpolation for k in ks)
                broken = ""
                if fc.data_path.startswith("modifiers[") and '"' in fc.data_path:
                    mn = fc.data_path.split('"')[1]
                    broken = "" if mn in ob.modifiers else "【修改器已经不在了】"
                print("  %s %s[%d] 键 %d %s 首 %.2f=%.4g 尾 %.2f=%.4g 外推 %s%s" % (
                    tag, fc.data_path, fc.array_index, len(ks), dict(it), ks[0].co[0], ks[0].co[1], ks[-1].co[0], ks[-1].co[1],
                    fc.extrapolation, broken))
            for d in B.drivers(idb):
                print("  %s 驱动 %s[%d] %s" % (tag, d.data_path, d.array_index, d.driver.expression))


def cmd_instances(a):
    f = int(B.pop(a, "--frame", sc.frame_start))
    ax = "xyz".index(B.pop(a, "--axis", "z"))
    bin_ = float(B.pop(a, "--bin", "250"))
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    vals = {}
    for inst in dg.object_instances:
        if not inst.is_instance:
            continue
        par = inst.parent.original.name if inst.parent else "?"
        vals.setdefault(par, []).append(inst.matrix_world.translation[ax])
    for par, lst in sorted(vals.items(), key=lambda t: -len(t[1])):
        lst.sort()
        bins = Counter(int(math.floor(v / bin_)) for v in lst)
        print("实例 %-26s %7d 个，%s 从 %.1f 到 %.1f" % (par, len(lst), "xyz"[ax], lst[0], lst[-1]))
        print("    每 %g：%s" % (bin_, " ".join("%g:%d" % (b * bin_, bins[b]) for b in sorted(bins))))


def cmd_camera(a):
    name = B.pop(a, "--cam")
    marks = B.marker_cameras()
    for f in B.frames(a[0] if a else None):
        sc.frame_set(f)
        cam = bpy.data.objects[name] if name else B.camera_at(f, marks)
        mw = cam.matrix_world
        fw = (mw.to_3x3() @ Vector((0, 0, -1))).normalized()
        up = (mw.to_3x3() @ Vector((0, 1, 0))).normalized()
        print("帧 %d %-16s 位置 %s 朝向 %s 上 %s 焦距 %.2f" % (f, cam.name, r3(mw.translation), r3(fw, 3), r3(up, 3), cam.data.lens))


def main():
    a = B.args()
    cmds = dict(scene=cmd_scene, objects=cmd_objects, faces=cmd_faces, nodes=cmd_nodes, keys=cmd_keys,
                instances=cmd_instances, camera=cmd_camera)
    if not a or a[0] not in cmds:
        raise SystemExit(__doc__)
    cmds[a[0]](a[1:])


main()
