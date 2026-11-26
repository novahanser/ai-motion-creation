# -*- coding: utf-8 -*-
"""bl_*.py 共用的小工具。只能在 Blender 里用（命令行：blender -b 工程.blend --python bl_xxx.py -- 参数）。

- 参数：取 `--` 后面的部分。
- 动画曲线：Blender 4.4 起动作是分层的，F 曲线要从 action.layers[i].strips[j].channelbag(slot).fcurves 取；
  老的 action.fcurves 在 5.x 里没有了。这里两种都认。
- 保存改动时使用另存（copy=True），输入工程用于读取。
"""
import os
import sys

import bpy


def utf8():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def pop(a, name, default=None, flag=False):
    """从参数表里取出 --name 的值（flag=True 时是开关），取过的删掉。"""
    if name in a:
        i = a.index(name)
        if flag:
            del a[i]
            return True
        v = a[i + 1]
        del a[i:i + 2]
        return v
    return False if flag else default


def frames(spec, sc=None):
    """「a-b」「a-b:s」「a,b,c」→ 帧号列表；None 用场景的起止。"""
    sc = sc or bpy.context.scene
    if not spec:
        return list(range(sc.frame_start, sc.frame_end + 1))
    out = []
    for part in str(spec).split(","):
        step = 1
        if ":" in part:
            part, s = part.split(":")
            step = int(s)
        if "-" in part[1:]:
            i = part.index("-", 1)
            out += list(range(int(part[:i]), int(part[i + 1:]) + 1, step))
        elif part.strip():
            out.append(int(part))
    return out


def fcurves(idb):
    ad = getattr(idb, "animation_data", None)
    if ad is None or ad.action is None:
        return []
    act = ad.action
    layers = getattr(act, "layers", None)
    if layers is not None and len(layers):
        slot = getattr(ad, "action_slot", None)
        out = []
        for lay in layers:
            for st in lay.strips:
                try:
                    cb = st.channelbag(slot) if slot is not None else None
                except Exception:
                    cb = None
                if cb is not None:
                    out += list(cb.fcurves)
        return out
    return list(getattr(act, "fcurves", []))


def drivers(idb):
    ad = getattr(idb, "animation_data", None)
    return list(ad.drivers) if ad else []


def owners():
    """带动画的东西：(标签, ID)。物体、物体数据、材质和世界的节点树、场景。"""
    out = [("物体:" + o.name, o) for o in bpy.data.objects]
    out += [("相机数据:" + c.name, c) for c in bpy.data.cameras]
    out += [("灯:" + l.name, l) for l in bpy.data.lights]
    out += [("网格:" + m.name, m) for m in bpy.data.meshes if m.animation_data]
    out += [("形状键:" + k.name, k) for k in bpy.data.shape_keys]
    out += [("材质:" + m.name, m.node_tree) for m in bpy.data.materials if m.node_tree]
    out += [("世界:" + w.name, w.node_tree) for w in bpy.data.worlds if w.node_tree]
    out += [("节点组:" + g.name, g) for g in bpy.data.node_groups]
    out += [("场景:" + s.name, s) for s in bpy.data.scenes]
    return out


def marker_cameras(sc=None):
    sc = sc or bpy.context.scene
    return sorted([(m.frame, m.camera) for m in sc.timeline_markers if m.camera is not None], key=lambda t: t[0])


def camera_at(f, marks=None, sc=None):
    """第 f 帧用的相机：按时间轴标记；没有标记就是场景相机。"""
    sc = sc or bpy.context.scene
    marks = marker_cameras(sc) if marks is None else marks
    cur = sc.camera
    for mf, c in marks:
        if mf <= f:
            cur = c
    if marks and cur is None:
        cur = marks[0][1]
    return cur


def unbind_markers(sc=None):
    """只在内存里把标记上绑的相机解开：开着动态模糊时，切点那一帧不会把上一台相机糊进来。"""
    sc = sc or bpy.context.scene
    for m in sc.timeline_markers:
        m.camera = None


def save_copy(path):
    src = os.path.normcase(os.path.abspath(bpy.data.filepath)) if bpy.data.filepath else ""
    dst = os.path.normcase(os.path.abspath(path))
    if src and src == dst:
        raise SystemExit("请选择与输入工程不同的保存路径：" + path)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    print("另存了", path)


def resolution(sc=None):
    sc = sc or bpy.context.scene
    r = sc.render
    k = r.resolution_percentage / 100.0
    return int(round(r.resolution_x * k)), int(round(r.resolution_y * k))
