# -*- coding: utf-8 -*-
"""动画曲线：倒出来、查毛病、和以前倒的比。只读，不存。

用法: blender -b <工程.blend> --python bl_curves.py -- <模式> [参数]
  dump <输出.json>      把工程里所有动画曲线原样倒出来：物体、物体数据、材质和世界的节点树、节点组、场景
                        （每个键：帧、值、左右手柄、插值、手柄类型；外推、曲线修改器的个数）
  check [--overshoot 2] [--run 20] [--out 报告.txt]
                        查三样：
                        · 键和键之间冲过头：每段取 8 个点，超出两个键值范围的量 > 两键差 × --overshoot + 1e-4 的段
                          （两个挨得很近的键之间手柄一长，中间的值就会冲出去，一次缩放被顶到 1.26）
                        · 烘过的键：连着 --run 个以上、间隔都不超过 1 帧的一串键（逐帧或更密）。
                          照着相机算出来、本来就逐帧打的键也会列出来，看了再定）
                        · 每条曲线的键数和插值，同一种东西（名字去掉末尾编号）合在一起
  diff <以前倒的.json> [--tol 1e-6]
                        拿现在这个工程和以前倒的比：多了、少了、变了的曲线（变了的报最大差在哪一帧）。
                        「重搭以后只许相机位置那三条不一样」这类话，用它核。
"""
import json
import os
import sys
from collections import defaultdict

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as B  # noqa: E402

B.utf8()


def all_curves():
    out = {}
    for tag, idb in B.owners():
        for fc in B.fcurves(idb):
            out["%s|%s[%d]" % (tag, fc.data_path, fc.array_index)] = fc
    return out


def dump_fc(fc):
    return dict(keys=[[k.co[0], k.co[1], k.handle_left[0], k.handle_left[1], k.handle_right[0], k.handle_right[1],
                       k.interpolation, k.handle_left_type, k.handle_right_type] for k in fc.keyframe_points],
                extrapolation=fc.extrapolation, modifiers=len(fc.modifiers))


def cmd_dump(a):
    res = {k: dump_fc(fc) for k, fc in all_curves().items()}
    with open(a[0], "w", encoding="utf-8") as fh:
        json.dump(dict(file=bpy.data.filepath, curves=res), fh, ensure_ascii=False)
    print("倒了 %d 条曲线、%d 个键 → %s" % (len(res), sum(len(v["keys"]) for v in res.values()), a[0]))


def cmd_check(a):
    over_k = float(B.pop(a, "--overshoot", "2"))
    run_n = int(B.pop(a, "--run", "20"))
    outp = B.pop(a, "--out")
    L = ["# 工程：%s" % bpy.data.filepath]
    bad_over, bad_run, groups = [], [], defaultdict(list)
    curves = all_curves()
    for key, fc in curves.items():
        kps = sorted(fc.keyframe_points, key=lambda k: k.co[0])
        for p, q in zip(kps[:-1], kps[1:]):
            if p.interpolation != "BEZIER":
                continue
            t0, t1, v0, v1 = p.co[0], q.co[0], p.co[1], q.co[1]
            lo, hi = min(v0, v1), max(v0, v1)
            worst, at = 0.0, None
            for i in range(1, 9):
                t = t0 + (t1 - t0) * i / 9
                v = fc.evaluate(t)
                o = max(0.0, v - hi, lo - v)
                if o > worst:
                    worst, at = o, t
            if worst > over_k * (hi - lo) + 1e-4:
                bad_over.append((key, t0, t1, v0, v1, worst, at))
        ts = [k.co[0] for k in kps]
        run, best = 1, 1
        for x, y in zip(ts[:-1], ts[1:]):
            run = run + 1 if y - x <= 1.0 + 1e-6 else 1
            best = max(best, run)
        if best >= run_n:
            bad_run.append((key, len(ts), best))
        owner, path = key.split("|", 1)
        base = owner.rstrip("0123456789").rstrip("_.")
        groups[(base, path)].append((len(ts), best, ",".join(sorted(set(k.interpolation for k in kps))), ts[0] if ts else 0, ts[-1] if ts else 0))
    L.append("# 曲线 %d 条、键 %d 个" % (len(curves), sum(len(fc.keyframe_points) for fc in curves.values())))
    L.append("# 键和键之间冲过头（超出两键范围 > 两键差 × %g）：%d 段" % (over_k, len(bad_over)))
    for key, t0, t1, v0, v1, w, at in bad_over[:200]:
        L.append("  %s  %.2f—%.2f 键 %.5g → %.5g，在 %.2f 冲出 %.5g" % (key, t0, t1, v0, v1, at, w))
    L.append("# 烘过的键（连着 %d 个以上、间隔都不超过 1 帧）：%d 条" % (run_n, len(bad_run)))
    for key, n, best in bad_run:
        L.append("  %s  %d 个键，最长一串 %d" % (key, n, best))
    L.append("# 每条曲线（名字去掉末尾编号合在一起）")
    for (base, path), v in sorted(groups.items()):
        ns = sorted(x[0] for x in v)
        L.append("  %s %s：%d 条，每条 %d—%d 个键，最长连键 %d，插值 %s，%.1f—%.1f" % (
            base, path, len(v), ns[0], ns[-1], max(x[1] for x in v), "/".join(sorted(set(x[2] for x in v))),
            min(x[3] for x in v), max(x[4] for x in v)))
    txt = "\n".join(L)
    print(txt)
    if outp:
        open(outp, "w", encoding="utf-8").write(txt + "\n")


def cmd_diff(a):
    tol = float(B.pop(a, "--tol", "1e-6"))
    old = json.load(open(a[0], encoding="utf-8"))["curves"]
    new = {k: dump_fc(fc) for k, fc in all_curves().items()}
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    same, changed = 0, []
    for k in sorted(set(old) & set(new)):
        ko, kn = old[k]["keys"], new[k]["keys"]
        if len(ko) != len(kn):
            changed.append((k, "键数 %d → %d" % (len(ko), len(kn))))
            continue
        worst, at = 0.0, None
        for x, y in zip(ko, kn):
            for i in range(6):
                d = abs(x[i] - y[i])
                if d > worst:
                    worst, at = d, y[0]
            if x[6:] != y[6:]:
                worst, at = max(worst, 1.0), y[0]
        if worst > tol:
            changed.append((k, "最大差 %.6g（在第 %.2f 帧的键上）" % (worst, at)))
        else:
            same += 1
    print("和 %s 比：一样 %d 条，变了 %d 条，只在以前有 %d 条，只在现在有 %d 条" % (a[0], same, len(changed), len(only_old), len(only_new)))
    for k, s in changed:
        print("  变了", k, s)
    for k in only_old:
        print("  以前有、现在没有", k)
    for k in only_new:
        print("  现在才有", k)


def main():
    a = B.args()
    cmds = dict(dump=cmd_dump, check=cmd_check, diff=cmd_diff)
    if not a or a[0] not in cmds:
        raise SystemExit(__doc__)
    cmds[a[0]](a[1:])


main()
