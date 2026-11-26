# -*- coding: utf-8 -*-
"""修改器：一层层看面积、按名字成批加细分、按镜头开关一道修改器、量是谁让一帧变慢（blender-3d.md 第 2、9 节）。

用法: blender -b <工程.blend> --python bl_modifiers.py -- <模式> …
  area <物体> [--frame F]
        把修改器全关，再一层层打开，每开一层量一次算完以后的面数和总面积（只读，不存）。
        线框后面接了磨圆的细分，细杆会变成肥大的面盖满画面：面积一下子涨几倍的那一层就是。
  subdiv <规则> [<规则> …] --save <存成.blend>
        规则 = 名字开头:做法:级数[:nolimit][:smooth]
          cc      在修改器最后加一道磨圆（卡特莫尔-克拉克，名字「末_细分_磨圆」）：前面的扭、弯、起伏都做完了再磨
          simple  在最前面加一道只加段的（简单细分，「首_加段」）：后面的弯更顺，截面不变（齿、带棱的截面）
          raise   最后那道细分本来就有：级数加这么多
          screw   螺旋的步数翻倍，再在最后磨这么多级
          nolimit 新加的磨圆关掉「用极限曲面」：三角面多、顶点乱的网格（网上下的模型、扇形封口）开着它一帧会慢几十倍
          smooth  网格的面改成平滑着色（原来是平面着色的，磨了还是一格一格）；改的是网格本身，关不回去
        已经加过（有「末_细分」「首_加段」）的物体不再加，所以每次从原工程重做。
  by-shot <物体> <修改器名> <帧>=on|off [<帧>=on|off …] --save <存成.blend>
        给一道修改器的开关（渲染、视图）打常量键：只在某几个镜头里关掉它。键放在切点前后两帧的正中间（例如 24.5），
        快门半帧居中时两帧都看不到这一刻，一帧里不会一半开一半关。
  timing <帧> <名字开头,名字开头,…> [--pct 50] [--try off|nolimit]
        先照原样渲一帧计时，再一组一组地把这些物体的细分关掉（--try off）或关掉极限曲面（--try nolimit）各渲一帧，
        报每一组省了几秒。只读，不存。
"""
import os
import sys
import tempfile
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def eval_area(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        return sum(p.area for p in me.polygons), len(me.polygons)
    finally:
        ev.to_mesh_clear()


def cmd_area(a):
    f = int(B.pop(a, "--frame", bpy.context.scene.frame_start))
    ob = bpy.data.objects[a[0]]
    bpy.context.scene.frame_set(f)
    state = [(m.show_viewport, m.show_render) for m in ob.modifiers]
    for m in ob.modifiers:
        m.show_viewport = False
    ar, nf = eval_area(ob)
    print("%s 第 %d 帧：全关 面 %d 面积 %.3f" % (ob.name, f, nf, ar))
    last = ar
    for m in ob.modifiers:
        m.show_viewport = True
        ar, nf = eval_area(ob)
        print("  开到 %-22s %-14s 面 %8d 面积 %10.3f（×%.2f）" % (m.name, m.type, nf, ar, ar / last if last else float("nan")))
        last = ar
    for m, (v, r) in zip(ob.modifiers, state):
        m.show_viewport, m.show_render = v, r


def cmd_subdiv(a):
    rules = []
    for s in a:
        q = s.split(":")
        rules.append(dict(pre=q[0], kind=q[1], n=int(q[2]), nolimit="nolimit" in q[3:], smooth="smooth" in q[3:]))
    done, smoothed = {}, set()
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        for R in rules:
            if not ob.name.startswith(R["pre"]):
                continue
            if any(m.name.startswith(("末_细分", "首_加段")) for m in ob.modifiers):
                break
            k, n = R["kind"], R["n"]
            if k in ("cc", "screw"):
                if k == "screw":
                    for m in ob.modifiers:
                        if m.type == "SCREW":
                            m.steps *= 2
                            m.render_steps *= 2
                m = ob.modifiers.new("末_细分_磨圆", "SUBSURF")
                m.subdivision_type = "CATMULL_CLARK"
                m.levels = m.render_levels = n
                m.use_limit_surface = not R["nolimit"]
            elif k == "raise":
                subs = [m for m in ob.modifiers if m.type == "SUBSURF"]
                if not subs:
                    break
                m = subs[-1]
                m.levels += n
                m.render_levels += n
                m.name = "末_细分_" + m.name
            elif k == "simple":
                m = ob.modifiers.new("首_加段", "SUBSURF")
                m.subdivision_type = "SIMPLE"
                m.levels = m.render_levels = n
                ob.modifiers.move(len(ob.modifiers) - 1, 0)
            else:
                raise SystemExit("做法只有 cc、simple、raise、screw：" + k)
            if R["smooth"] and ob.data.name not in smoothed:
                for p in ob.data.polygons:
                    p.use_smooth = True
                smoothed.add(ob.data.name)
            done[R["pre"]] = done.get(R["pre"], 0) + 1
            break
    print("加了细分的：", "  ".join("%s×%d" % kv for kv in done.items()) or "（一个都没有：名字开头对不上，或者已经加过）")


def cmd_by_shot(a):
    ob = bpy.data.objects[a[0]]
    m = ob.modifiers.get(a[1])
    if m is None:
        raise SystemExit("%s 上没有修改器「%s」" % (a[0], a[1]))
    for item in a[2:]:
        t, st = item.split("=")
        on = st.lower() in ("on", "1", "开")
        for prop in ("show_render", "show_viewport"):
            setattr(m, prop, on)
            ob.keyframe_insert('modifiers["%s"].%s' % (m.name, prop), frame=float(t))
    for fc in B.fcurves(ob):
        if m.name in fc.data_path and "show_" in fc.data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
            fc.update()
            print("  ", fc.data_path, [(round(k.co[0], 2), bool(k.co[1])) for k in fc.keyframe_points])


def render_time(path):
    t0 = time.time()
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return time.time() - t0


def cmd_timing(a):
    pct = int(B.pop(a, "--pct", "50"))
    how = B.pop(a, "--try", "off")
    f, groups = int(a[0]), a[1].split(",")
    sc = bpy.context.scene
    sc.render.resolution_percentage = pct
    sc.frame_set(f)
    tmp = tempfile.mkdtemp(prefix="bltiming_")
    render_time(os.path.join(tmp, "warm.png"))
    base = render_time(os.path.join(tmp, "base.png"))
    print("第 %d 帧 %d%%：原样 %.2f 秒" % (f, pct, base))
    for g in groups:
        touched = []
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name.startswith(g):
                for m in ob.modifiers:
                    if m.type == "SUBSURF":
                        touched.append((m, m.show_render, m.use_limit_surface))
                        if how == "nolimit":
                            m.use_limit_surface = False
                        else:
                            m.show_render = False
        if not touched:
            print("  %-16s 没有带细分的物体" % g)
            continue
        t = render_time(os.path.join(tmp, "g.png"))
        print("  %-16s %s 以后 %.2f 秒（省 %.2f 秒，细分 %d 道）" % (g, "关细分" if how == "off" else "关极限曲面", t, base - t, len(touched)))
        for m, sr, lim in touched:
            m.show_render, m.use_limit_surface = sr, lim
    print("（试渲的图在 %s，可以删）" % tmp)


def main():
    a = B.args()
    save = B.pop(a, "--save")
    cmds = dict(area=cmd_area, subdiv=cmd_subdiv, **{"by-shot": cmd_by_shot}, timing=cmd_timing)
    if not a or a[0] not in cmds:
        raise SystemExit(__doc__)
    if a[0] in ("subdiv", "by-shot") and not save:
        raise SystemExit("这个模式要给 --save <存成.blend>")
    cmds[a[0]](a[1:])
    if a[0] in ("subdiv", "by-shot"):
        B.save_copy(save)


main()
