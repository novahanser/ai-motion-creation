# -*- coding: utf-8 -*-
"""查找模型、检查下载文件并记录资源元数据（blender-3d.md 第 2 节）。

Poly Haven 的模型按 CC0 提供。下载前检查文件名、来源、大小与许可。
用法:
  ph-search <词> [<词> …] [--json <存下来的清单.json>]
        在 Poly Haven 的模型清单里按词找（名字、标签、类别）。不给 --json 就现取一次清单（api.polyhaven.com/assets?t=models）。
  ph-list <模型 id> [<id> …] [--res 1k]
        只列 glTF 的文件、大小、面数、作者，不下。
  ph-get <存到哪个目录> <模型 id> [<id> …] [--res 1k]
        下 glTF（带 .bin 和贴图）到 <目录>/polyhaven_<id>/，逐个文件核 md5，写一份 来源.txt（地址、许可、作者、面数、日期、每个文件的大小和 md5）。
        每个模型放一个新的空文件夹。
  sf-list <搜索结果.json> [<…>] [--max 面数上限]
        读 Sketchfab 公开搜索接口存下来的结果，列名字、许可、面数、作者、uid。此命令只读导出的元数据。
        结果这样存：https://api.sketchfab.com/v3/search?type=models&q=<词>&downloadable=true&count=24&sort_by=-likeCount
"""
import datetime
import hashlib
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "model-fetch/1.0"}


def api(path):
    req = urllib.request.Request("https://api.polyhaven.com/" + path, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def files_of(aid, res):
    g = api("files/" + aid)["gltf"][res]["gltf"]
    out = [(os.path.basename(g["url"]), g["url"], g["size"], g.get("md5"))]
    for rel, inf in g.get("include", {}).items():
        out.append((rel, inf["url"], inf["size"], inf.get("md5")))
    return out


def pop(a, name, default=None):
    if name in a:
        i = a.index(name)
        v = a[i + 1]
        del a[i:i + 2]
        return v
    return default


def ph_search(a):
    js = pop(a, "--json")
    d = json.load(open(js, encoding="utf-8")) if js else api("assets?t=models")
    words = [w.lower() for w in a]
    print("Poly Haven 模型共 %d 个" % len(d))
    n = 0
    for k, v in sorted(d.items()):
        hay = " ".join([k, v.get("name", "")] + v.get("tags", []) + v.get("categories", [])).lower()
        hit = [w for w in words if w in hay]
        if hit:
            n += 1
            dim = v.get("dimensions") or [0, 0, 0]
            print("%-34s 面数 %-8s 尺寸mm %s  类 %s  标 %s  [%s]" % (
                k, v.get("polycount"), [int(x) for x in dim], ",".join(v.get("categories", [])),
                ",".join(v.get("tags", [])[:9]), ",".join(hit)))
    print("找到 %d 个" % n)


def ph_list(a):
    res = pop(a, "--res", "1k")
    for aid in a:
        info = api("info/" + aid)
        fs = files_of(aid, res)
        tot = sum(f[2] for f in fs)
        print("== %s「%s」 面数 %s  许可 CC0  作者 %s  共 %.1f MB（glTF %s）" % (
            aid, info.get("name"), info.get("polycount"), ",".join(info.get("authors", {}).keys()), tot / 1e6, res))
        for rel, url, size, md5 in fs:
            print("   %-46s %8.2f MB" % (rel, size / 1e6))


def ph_get(a):
    res = pop(a, "--res", "1k")
    root = a[0]
    for aid in a[1:]:
        info = api("info/" + aid)
        fs = files_of(aid, res)
        dst = os.path.join(root, "polyhaven_" + aid)
        if os.path.exists(dst) and os.listdir(dst):
            raise SystemExit("目标文件夹不是空的，先换一个：" + dst)
        os.makedirs(dst, exist_ok=True)
        lines = ["%s「%s」" % (aid, info.get("name")),
                 "来源：Poly Haven  https://polyhaven.com/a/%s" % aid,
                 "许可：CC0（公共领域）",
                 "作者：%s" % ",".join(info.get("authors", {}).keys()),
                 "面数：%s" % info.get("polycount"),
                 "下载：%s，glTF %s，只从 api.polyhaven.com 给的地址下" % (datetime.date.today().isoformat(), res),
                 "文件："]
        tot = 0
        for rel, url, size, md5 in fs:
            p = os.path.join(dst, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                data = r.read()
            if len(data) != size:
                raise SystemExit("大小不对：%s %d ≠ %d" % (rel, len(data), size))
            if md5 and hashlib.md5(data).hexdigest() != md5:
                raise SystemExit("md5 不对：" + rel)
            with open(p, "wb") as f:
                f.write(data)
            tot += len(data)
            lines.append("  %s  %.2f MB  md5 %s" % (rel, len(data) / 1e6, md5 or "（清单里没有）"))
        lines.append("合计：%.1f MB" % (tot / 1e6))
        with open(os.path.join(dst, "来源.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("下好了 %s（%.1f MB）" % (dst, tot / 1e6))


def sf_list(a):
    mx = pop(a, "--max")
    mx = int(mx) if mx else None
    for p in a:
        d = json.load(open(p, encoding="utf-8"))
        rs = d.get("results", [])
        print("==", p, "共", len(rs))
        for r in rs:
            fc = r.get("faceCount") or 0
            if mx and fc > mx:
                continue
            lic = (r.get("license") or {}).get("label") or "?"
            print("  %-52s 许可 %-22s 面 %-8s 赞 %-5s 作者 %-20s %s" % (
                (r.get("name") or "")[:52], lic, fc, r.get("likeCount"), ((r.get("user") or {}).get("username") or "")[:20], r.get("uid")))


def main():
    a = sys.argv[1:]
    cmds = {"ph-search": ph_search, "ph-list": ph_list, "ph-get": ph_get, "sf-list": sf_list}
    if not a or a[0] not in cmds:
        raise SystemExit(__doc__)
    cmds[a[0]](a[1:])


if __name__ == "__main__":
    main()
