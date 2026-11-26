# -*- coding: utf-8 -*-
"""动态模糊不整段开：清晰、模糊各渲一份，AE 里模糊那份按拍、按转速盖（blender-3d.md 第 5 节）。这支算每帧盖多少。

输入是 bl_camera_motion.py 出的相机表（frame, view_deg, up_deg, move_m：每帧视线转了几度、相机的「上」转了几度、走了几米）。
可调的叠加强度：
  拍上：拍点那一帧 100%、下一帧 100%、第 2 帧 60%、第 3 帧 25%（--kick）
  转头：前后两帧视线转速的平均，每帧 3° 起盖，到 15° 线性涨至 90%（--turn 3:15:90）
  跳机位（一帧跳过去的切）那一帧不盖：快门居中时，模糊那份会把前后两个机位抹在一起（--jumps）
  --fast 再按前进量和滚转盖，写法同 --turn：如 10:22:85,4.5:9.5:80 = 每帧走 10 米起盖、封顶 85%；滚转每帧 4.5° 起盖、封顶 80%
输出 AE 的定格关键帧：[{"time": 秒, "value": 0—100}, …]，时间从表里第一帧算起（AE 里这一层从第一帧起放）。

用法: python -I blur_cover.py <相机表.csv> <输出.json> --beat <第一拍的帧>:<一拍几帧> [--fps 30]
        [--kick 100,100,60,25] [--turn 3:15:90] [--jumps 25,49] [--fast 10:22:85,4.5:9.5:80]
  例：120 BPM、30 fps、第一拍在第 1 帧 → --beat 1:15
"""
import csv
import json
import math
import sys

sys.stdout.reconfigure(encoding="utf-8")


def ramp(x, a, b, top):
    """a 起盖，到 b 线性涨到 1，再封顶 top。"""
    return min(top, max(0.0, (x - a) / (b - a))) if b > a else (top if x >= a else 0.0)


def beat_before(f, b0, bl):
    """不晚于第 f 帧的最后一个拍点（拍点四舍五入到整帧）。"""
    k = math.floor((f - b0) / bl)
    cands = [round(b0 + j * bl) for j in (k - 1, k, k + 1)]
    ok = [c for c in cands if c <= f]
    return max(ok) if ok else None


def main():
    a = sys.argv[1:]
    opt = {"--fps": "30", "--kick": "100,100,60,25", "--turn": "3:15:90", "--jumps": "", "--fast": "", "--beat": None}
    for k in list(opt):
        if k in a:
            i = a.index(k); opt[k] = a[i + 1]; del a[i:i + 2]
    if len(a) < 2 or not opt["--beat"]:
        raise SystemExit(__doc__)
    rows = list(csv.DictReader(open(a[0], encoding="utf-8")))
    out = a[1]
    fps = float(opt["--fps"])
    b0, bl = [float(x) for x in opt["--beat"].split(":")]
    kick = [float(x) / 100 for x in opt["--kick"].split(",")]
    t_a, t_b, t_top = [float(x) for x in opt["--turn"].split(":")]
    jumps = set(int(x) for x in opt["--jumps"].split(",") if x.strip())
    fast = [[float(x) for x in s.split(":")] for s in opt["--fast"].split(",") if s.strip()]
    ang = {int(r["frame"]): float(r["view_deg"]) for r in rows}
    upd = {int(r["frame"]): float(r["up_deg"]) for r in rows}
    mov = {int(r["frame"]): float(r["move_m"]) for r in rows}
    for j in jumps:                    # 跳切那一帧的转角、前进、滚转都是跳过去的，不算
        for d in (ang, upd, mov):
            if j in d:
                d[j] = d.get(j - 1, 0.0)
    frames = sorted(ang)
    f0 = frames[0]
    vals = []
    for f in frames:
        prev = beat_before(f, b0, bl)
        d = f - prev if prev is not None else 99
        v = kick[d] if 0 <= d < len(kick) else 0.0
        sp = (ang.get(f, 0.0) + ang.get(f + 1, ang.get(f, 0.0))) / 2.0
        v = max(v, ramp(sp, t_a, t_b, t_top / 100))
        if fast and f not in jumps:
            mv = (mov.get(f, 0.0) + mov.get(f + 1, mov.get(f, 0.0))) / 2.0
            ru = (upd.get(f, 0.0) + upd.get(f + 1, upd.get(f, 0.0))) / 2.0
            if len(fast) > 0:
                v = max(v, ramp(mv, fast[0][0], fast[0][1], fast[0][2] / 100))
            if len(fast) > 1:
                v = max(v, ramp(ru, fast[1][0], fast[1][1], fast[1][2] / 100))
        if f in jumps:
            v = 0.0
        vals.append(int(round(100 * v)))
    keys, last = [], None
    for i, v in enumerate(vals):
        if v != last:
            keys.append({"time": round(i / fps, 5), "value": v})
            last = v
    json.dump(keys, open(out, "w", encoding="utf-8"))
    print("%d 帧（%d—%d），定格关键帧 %d 个；盖 ≥ 50%% 的 %d 帧，盖 > 0 的 %d 帧 → %s" % (
        len(vals), f0, frames[-1], len(keys), sum(v >= 50 for v in vals), sum(v > 0 for v in vals), out))


if __name__ == "__main__":
    main()
