# -*- coding: utf-8 -*-
"""接着一个做好的场景往后做：把所有动画往后延一段，转的接着转、炸的接着炸。做完另存，打开的工程不动（blender-3d.md 第 9 节）。

在既有工程的副本中延长动画，保持已经渲染的部分与续段接得上。

做法（每一条动画曲线）：
  · 把「窗口」（最后几小节，帧 W0—W1）里的键抄到后面，数值都加上窗口里的净变化（W1 处的值 − W0 处的值），曲线就接上了；
  · 给了两张拍表（--old 窗口里的拍、--new 后面的拍，个数一样、最后一个是下一小节的头），抄的时候按拍对齐：
    一个键离哪个拍近就跟着哪个拍走（拍前半帧换大小的那种键才不会跑到拍后面去）；不给就整段平移 W1 − W0；
  · 窗口里只有一个键或没有键的曲线（头尾两个键的匀速转动）：改成线性外推，照原来的速度接着走。
场景的结束帧挪到新的最后一拍。

用法: blender -b <工程.blend> --python bl_extend.py -- --window <W0>-<W1> --save <存成.blend> [--old 1,13,25 --new 25,37,49]
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def main():
    a = B.args()
    win = B.pop(a, "--window"); save = B.pop(a, "--save"); old = B.pop(a, "--old"); new = B.pop(a, "--new")
    if not win or not save:
        raise SystemExit(__doc__)
    W0, W1 = [float(x) for x in win.split("-")]
    OLD = [float(x) for x in old.split(",")] if old else None
    NEW = [float(x) for x in new.split(",")] if new else None
    if (OLD is None) != (NEW is None) or (OLD and len(OLD) != len(NEW)):
        raise SystemExit("--old 和 --new 要一起给、个数一样")
    if OLD and (abs(OLD[0] - W0) > 1e-6 or abs(OLD[-1] - W1) > 1e-6):
        raise SystemExit("--old 的第一个和最后一个要正好是窗口的两头")
    shift = W1 - W0

    def map_t(f):
        if not OLD:
            return f + shift
        i = max(j for j in range(len(OLD) - 1) if OLD[j] <= f)
        pa, pb = f - OLD[i], OLD[i + 1] - f
        return NEW[i] + pa if pa <= pb else NEW[i + 1] - pb

    stat = {"抄": 0, "线性外推": 0, "跳过": 0}
    seen = set()
    for act in bpy.data.actions:
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        if fc.as_pointer() in seen:
                            continue
                        seen.add(fc.as_pointer())
                        kps = sorted(fc.keyframe_points, key=lambda k: k.co[0])
                        if len(kps) < 2:
                            stat["跳过"] += 1
                            continue
                        inwin = [k for k in kps if W0 <= k.co[0] < W1]
                        if len(inwin) <= 1:
                            fc.extrapolation = "LINEAR"
                            stat["线性外推"] += 1
                            continue
                        dv = fc.evaluate(W1) - fc.evaluate(W0)
                        rows, used = [], set()
                        for k in inwin:
                            f = k.co[0]
                            fn = map_t(f)
                            while round(fn, 3) in used:
                                fn += 0.25
                            used.add(round(fn, 3))
                            rows.append((fn, k.co[1] + dv, (k.handle_left[0] - f + fn, k.handle_left[1] + dv),
                                         (k.handle_right[0] - f + fn, k.handle_right[1] + dv),
                                         k.interpolation, k.handle_left_type, k.handle_right_type))
                        n0 = len(fc.keyframe_points)
                        fc.keyframe_points.add(len(rows))
                        for j, (fn, v, hl, hr, ip, tl, tr) in enumerate(rows):
                            kp = fc.keyframe_points[n0 + j]
                            kp.co = (fn, v)
                            kp.interpolation = ip
                            kp.handle_left_type, kp.handle_right_type = tl, tr
                            kp.handle_left, kp.handle_right = hl, hr
                        fc.update()
                        stat["抄"] += 1
    sc = bpy.context.scene
    sc.frame_end = int(round(NEW[-1] - 1 if NEW else W1 + shift))
    print("动画往后延：", stat, "；场景结束帧 →", sc.frame_end)
    B.save_copy(save)


main()
