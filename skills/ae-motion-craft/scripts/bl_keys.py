# -*- coding: utf-8 -*-
"""给相机（或别的物体）打能手改的贝塞尔键：每拍一踢、平滑转头、正弦摇摆、急起缓停的手柄、在父物体上加推进和滚转。
做完另存（--save），打开的工程不动（blender-3d.md 第 4 节）。

用法: blender -b <工程.blend> --python bl_keys.py -- <模式> … --save <存成.blend>
  beats <物体> <属性> <分量> <第一拍的帧> <一拍几帧> <拍数> <每拍走多少> [--kick 1.9] [--pre 0.6] [--from 起始值]
        每拍一个键，值每拍加「每拍走多少」；拍上的出手柄斜率 = --kick × 平均速度，下一拍前的入手柄斜率 = --pre × 平均速度，
        手柄长 = 一拍的三分之一。
        这一段里原有的键先删掉。
  turn  <物体> <属性> <分量> <起始帧> <用几帧> <转多少> [--no-shift]
        平滑转头：角度 = A × (6u⁵ − 15u⁴ + 10u³)，起止转速为 0，最快约是平均的 1.875 倍。只放 5 个键
        （起、¼、中、¾、止），手柄斜率取这条曲线的导数，改起来方便。
        这一段里原有的键先删掉，后面的键整体加上 A（--no-shift 不加）。要和摇摆这类动作叠，转头打在相机链上另一层空物体上。
  sway  <物体> <属性> <分量> <幅度> <周期帧数> <过零的帧> <起始帧> <结束帧> [--base 中心值]
        正弦摇摆：键放在峰、谷、过零（每四分之一个周期一个），手柄斜率照正弦的导数。这一段里原有的键先删掉。
  ease  <物体> <属性> <分量> <x1,y1,x2,y2> [--range a-b]
        把每两个键之间改成一条 cubic-bezier（和 CSS 的写法一样）。匀速示例：0.333,0.333,0.667,0.667。
  parent <相机> <段;段;…> [--axis z] [--sign -1] [--roll-axis z] [--name 相机_加]
        在相机链最上面加一个空物体，只在它上面打要加的推进和滚转。
        段 = 起帧:止帧:多推几米:多滚几度:形状；形状 bell = 起止斜率都是 0、中间最快（冲一段再收），
        ramp = 起点斜率 0、止点斜率 = 平均速度的 2 倍（一路加速，接下一段）。
        --axis / --sign：往前是哪条世界轴的哪个方向（默认 −Z）。
属性写 Blender 的路径：location、rotation_euler、delta_rotation_euler、scale，或者 data.lens 这类；分量是 0/1/2。
rotation 这类属性的值写度，脚本自己换成弧度。
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def target(obname, path):
    ob = bpy.data.objects[obname]
    if path.startswith("data."):
        return ob.data, path[5:]
    return ob, path


def is_rot(path):
    return "rotation" in path


def get_fc(idb, path, idx, create=True):
    for fc in B.fcurves(idb):
        if fc.data_path == path and fc.array_index == idx:
            return fc
    if not create:
        return None
    idb.keyframe_insert(path, index=idx, frame=bpy.context.scene.frame_current)
    fc = get_fc(idb, path, idx, False)
    # 新建时插的那一个键先去掉，后面自己放
    while len(fc.keyframe_points):
        fc.keyframe_points.remove(fc.keyframe_points[0])
    return fc


def value_at(idb, path, idx, fc, t):
    if fc is not None and len(fc.keyframe_points):
        return fc.evaluate(t)
    v = getattr(idb, path)
    try:
        return v[idx]
    except TypeError:
        return v


def remove_between(fc, t0, t1, inclusive=True):
    for k in sorted(list(fc.keyframe_points), key=lambda k: -k.co[0]):
        x = k.co[0]
        if (t0 - 1e-6 <= x <= t1 + 1e-6) if inclusive else (t0 + 1e-6 < x < t1 - 1e-6):
            fc.keyframe_points.remove(k)


def put_keys(fc, keys):
    """keys: [(帧, 值, 左斜率, 右斜率)]，手柄自由，长 = 到相邻键的三分之一（两头用自己这一段的三分之一）。"""
    n0 = len(fc.keyframe_points)
    fc.keyframe_points.add(len(keys))
    new = list(fc.keyframe_points)[n0:]
    for kp, (t, v, sl, sr) in zip(new, keys):
        kp.co = (t, v)
        kp.interpolation = "BEZIER"
        kp.handle_left_type = "FREE"
        kp.handle_right_type = "FREE"
    fc.update()
    kps = sorted(fc.keyframe_points, key=lambda k: k.co[0])
    want = {round(t, 4): (sl, sr) for t, v, sl, sr in keys}
    for i, kp in enumerate(kps):
        key = round(kp.co[0], 4)
        if key not in want:
            continue
        sl, sr = want[key]
        t, v = kp.co
        lp = kps[i - 1].co[0] if i > 0 else None
        np_ = kps[i + 1].co[0] if i < len(kps) - 1 else None
        dl = (t - lp) / 3.0 if lp is not None else ((np_ - t) / 3.0 if np_ is not None else 1.0)
        dr = (np_ - t) / 3.0 if np_ is not None else dl
        kp.handle_left = (t - dl, v - sl * dl)
        kp.handle_right = (t + dr, v + sr * dr)
    fc.update()


def cmd_beats(a):
    kick = float(B.pop(a, "--kick", "1.9")); pre = float(B.pop(a, "--pre", "0.6")); start = B.pop(a, "--from")
    obn, path, idx, b0, bl, n, dist = a[0], a[1], int(a[2]), float(a[3]), float(a[4]), int(a[5]), float(a[6])
    idb, path = target(obn, path)
    fc = get_fc(idb, path, idx)
    v0 = float(start) if start is not None else value_at(idb, path, idx, fc, b0)
    if is_rot(path):
        dist = math.radians(dist)
        v0 = math.radians(float(start)) if start is not None else v0
    remove_between(fc, b0, b0 + n * bl)
    avg = dist / bl
    keys = [(b0 + k * bl, v0 + k * dist, pre * avg, kick * avg) for k in range(n + 1)]
    put_keys(fc, keys)
    print("每拍一踢：%s %s[%d]，%d 拍，每拍 %.4g，拍上出手柄 %.2f×、入手柄 %.2f× 平均速度" % (obn, path, idx, n, dist, kick, pre))


def cmd_turn(a):
    noshift = B.pop(a, "--no-shift", flag=True)
    obn, path, idx, t0, N, A = a[0], a[1], int(a[2]), float(a[3]), float(a[4]), float(a[5])
    idb, path = target(obn, path)
    fc = get_fc(idb, path, idx)
    if is_rot(path):
        A = math.radians(A)
    v0 = value_at(idb, path, idx, fc, t0)
    remove_between(fc, t0, t0 + N)
    if not noshift:
        for k in fc.keyframe_points:
            if k.co[0] > t0 + N:
                k.co[1] += A
                k.handle_left[1] += A
                k.handle_right[1] += A
    s = lambda u: 6 * u ** 5 - 15 * u ** 4 + 10 * u ** 3
    ds = lambda u: 30 * u * u * (1 - u) * (1 - u)
    keys = [(t0 + u * N, v0 + A * s(u), A * ds(u) / N, A * ds(u) / N) for u in (0.0, 0.25, 0.5, 0.75, 1.0)]
    put_keys(fc, keys)
    err = max(abs(fc.evaluate(t0 + i * N / 60) - (v0 + A * s(i / 60))) for i in range(61))
    print("平滑转头：%s %s[%d] 第 %.2f 帧起 %.0f 帧转 %.4g%s，5 个键；和公式的最大差 %.4g%s" % (
        obn, path, idx, t0, N, math.degrees(A) if is_rot(path) else A, "°" if is_rot(path) else "",
        math.degrees(err) if is_rot(path) else err, "°" if is_rot(path) else ""))


def cmd_sway(a):
    base = B.pop(a, "--base")
    obn, path, idx, A, P, z, t0, t1 = a[0], a[1], int(a[2]), float(a[3]), float(a[4]), float(a[5]), float(a[6]), float(a[7])
    idb, path = target(obn, path)
    fc = get_fc(idb, path, idx)
    if is_rot(path):
        A = math.radians(A)
    c = float(base) if base is not None else value_at(idb, path, idx, fc, t0) - A * math.sin(2 * math.pi * (t0 - z) / P)
    if base is not None and is_rot(path):
        c = math.radians(c)
    remove_between(fc, t0, t1)
    q = P / 4.0
    ts = [t0]
    t = z + math.ceil((t0 - z) / q + 1e-9) * q
    while t < t1 - 1e-6:
        ts.append(t)
        t += q
    ts.append(t1)
    w = 2 * math.pi / P
    keys = [(t, c + A * math.sin(w * (t - z)), A * w * math.cos(w * (t - z)), A * w * math.cos(w * (t - z))) for t in ts]
    put_keys(fc, keys)
    err = max(abs(fc.evaluate(t0 + (t1 - t0) * i / 400) - (c + A * math.sin(w * (t0 + (t1 - t0) * i / 400 - z)))) for i in range(401))
    print("摇摆：%s %s[%d] %d 个键，和正弦的最大差 %.4g%s" % (
        obn, path, idx, len(keys), math.degrees(err) if is_rot(path) else err, "°" if is_rot(path) else ""))


def cmd_ease(a):
    rng = B.pop(a, "--range")
    obn, path, idx = a[0], a[1], int(a[2])
    x1, y1, x2, y2 = [float(v) for v in a[3].split(",")]
    idb, path = target(obn, path)
    fc = get_fc(idb, path, idx, create=False)
    if fc is None:
        raise SystemExit("这条曲线没有键：%s %s[%d]" % (obn, path, idx))
    lo, hi = (B.frames(rng)[0], B.frames(rng)[-1]) if rng else (-1e9, 1e9)
    kps = sorted(fc.keyframe_points, key=lambda k: k.co[0])
    n = 0
    for p, q in zip(kps[:-1], kps[1:]):
        t0, v0 = p.co
        t1, v1 = q.co
        if t0 < lo - 1e-6 or t1 > hi + 1e-6:
            continue
        p.interpolation = "BEZIER"
        p.handle_right_type = "FREE"
        q.handle_left_type = "FREE"
        L, dv = t1 - t0, v1 - v0
        p.handle_right = (t0 + x1 * L, v0 + y1 * dv)
        q.handle_left = (t0 + x2 * L, v0 + y2 * dv)
        n += 1
    fc.update()
    print("改了 %d 段：cubic-bezier(%g, %g, %g, %g)" % (n, x1, y1, x2, y2))


def cmd_parent(a):
    axis = "xyz".index(B.pop(a, "--axis", "z")); sign = float(B.pop(a, "--sign", "-1"))
    rax = "xyz".index(B.pop(a, "--roll-axis", "z")); name = B.pop(a, "--name")
    cam = bpy.data.objects[a[0]]
    segs = []
    for s in a[1].split(";"):
        f0, f1, d, r, shape = s.split(":")
        segs.append((float(f0), float(f1), float(d), float(r), shape))
    sc = bpy.context.scene
    name = name or cam.name + "_加"
    top = cam
    while top.parent:
        top = top.parent
    hs = bpy.data.objects.get(name)
    if hs is None:
        hs = bpy.data.objects.new(name, None)
        sc.collection.objects.link(hs)
    if top is not hs:
        mw = top.matrix_world.copy()
        top.parent = hs
        top.matrix_world = mw
    hs.animation_data_clear()
    kz = [(sc.frame_start, 0.0, 0.0, 0.0)]
    kr = [(sc.frame_start, 0.0, 0.0, 0.0)]
    az = ar = 0.0
    for f0, f1, d, r, shape in segs:
        L = f1 - f0
        kz.append((f0, az, 0.0, 0.0)); kr.append((f0, ar, 0.0, 0.0))
        az += sign * d; ar += math.radians(r)
        if shape == "bell":
            kz.append((f1, az, 0.0, 0.0)); kr.append((f1, ar, 0.0, 0.0))
        elif shape == "ramp":
            kz.append((f1, az, 2 * sign * d / L, 2 * sign * d / L)); kr.append((f1, ar, 2 * math.radians(r) / L, 2 * math.radians(r) / L))
        else:
            raise SystemExit("形状只有 bell、ramp：" + shape)
    for path, idx, keys in (("location", axis, kz), ("rotation_euler", rax, kr)):
        fc = get_fc(hs, path, idx)
        put_keys(fc, keys)
    prev, peak = None, {}
    lo = int(min([sc.frame_start] + [s[0] for s in segs]))
    hi = int(max([sc.frame_end] + [s[1] for s in segs]))
    for f in range(lo, hi + 1):
        sc.frame_set(f)
        p = cam.matrix_world.translation.copy()
        if prev is not None:
            for i, (f0, f1, *_r) in enumerate(segs):
                if f0 <= f <= f1:
                    peak[i] = max(peak.get(i, 0.0), (p - prev).length)
        prev = p
    for i, (f0, f1, d, r, shape) in enumerate(segs):
        print("段 %d：%g—%g 帧，多推 %g、多滚 %g°（%s），这一段相机每帧最多走 %.2f" % (i + 1, f0, f1, d, r, shape, peak.get(i, 0.0)))
    print("父物体", hs.name, "（相机链最上面）；原相机关键帧保留")


def main():
    a = B.args()
    save = B.pop(a, "--save")
    cmds = dict(beats=cmd_beats, turn=cmd_turn, sway=cmd_sway, ease=cmd_ease, parent=cmd_parent)
    if not a or a[0] not in cmds or not save:
        raise SystemExit(__doc__ + "\n（要给 --save <存成.blend>）")
    cmds[a[0]](a[1:])
    B.save_copy(save)


main()
