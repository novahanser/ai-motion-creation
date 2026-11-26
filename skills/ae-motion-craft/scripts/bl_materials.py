# -*- coding: utf-8 -*-
"""材质库（blender-3d.md 第 3 节）：在别的 Blender 脚本里 import 着用；单独跑是搭一个试样场景、渲一张看。

两路，不要混：
一、出「版」（不打灯、全自发光；色彩管理设 Raw，红 = 主版的深浅，绿 = 墨版，透明 = 有没有东西；渲完用 split_plates.py 拆）
  mat_plate(名字, 深浅, 墨)                   平的一块版
  mat_chrome(名字, …)                         不打灯的铬：反射方向查一张带条纹的「环境」（波浪纹理），硬边亮条一转就跑；
                                              乘环境光遮蔽，边上一圈亮；墨只留在缝里和反光里很窄的一段
  mat_glass(名字, …)                          同样的反光，大部分透明，只有亮条和边是实的
  mat_rock(名字, …)                           像 matcap：法线转到相机坐标、和一个方向点乘、查一条常量色带（像等高线），乘遮蔽
  mat_cut(名字, …)                            石头的切面：绕轴一圈圈的线（波浪纹理 RINGS），两档深浅
二、成品的颜色（色彩管理 Standard）
  mat_flat(名字, 颜色)                        自发光的平涂
  mat_metal(名字, 粗糙度, 底色)               铬或其他金属外观，粗糙度与底色可独立设置
  world_reflection_only(场景, hdr 路径, …)    环境图只给反射：镜头看到的是底色（或透明），金属上照得出环境；
                                              可以让环境自己转（整段转几圈）以改变反光方向
  mat_glass_dispersion(名字, 染色, …)         Cycles 的色散玻璃：Blender 5.2 的玻璃没有色散输入，拆成红绿蓝三个玻璃加起来，IOR 各差约 0.035
  mat_distance_gradient(名字, 颜色们, 近, 远)  渐变跟到相机的距离走（取对数）：长墙上按生成坐标取渐变看不出来
  hue_cycle(材质, 每圈几帧, 起始帧)           色相每帧转：值节点打线性键 + 取小数，进色相；不用驱动器
  mix_to_metal(材质, [(帧, 金属度), …], 粗糙度) 自发光的平涂按打键的「金属度」慢慢变成金属
单独跑:
  blender -b --python bl_materials.py -- --demo <存成.blend> [--render <出图目录>] [--hdr <环境图.hdr>]
  搭一个试样场景（几样东西各挂一种材质），存下来；给了 --render 就渲三张：版（Raw，透明底）、成品颜色（EEVEE，Standard：
  金属、慢慢变金属、转色相、距离渐变）、色散玻璃（Cycles 32 采样）。
"""
import math
import os
import sys

import bpy
from mathutils import Vector

# ------------------------------------------------------------------ 共用的节点小工具


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m, nt, em, out


def _ramp(nt, fac, stops, interp="LINEAR"):
    """stops：[(位置, 灰度)] 或 [(位置, (r,g,b))]。"""
    r = nt.nodes.new("ShaderNodeValToRGB")
    cr = r.color_ramp
    cr.interpolation = interp
    if len(stops) == 1:
        stops = [stops[0], (1.0, stops[0][1])]

    def col(v):
        return tuple(v) + (1.0,) if isinstance(v, (tuple, list)) else (v, v, v, 1.0)
    els = cr.elements
    els[0].position, els[0].color = stops[0][0], col(stops[0][1])
    els[1].position, els[1].color = stops[1][0], col(stops[1][1])
    for p, v in stops[2:]:
        e = els.new(p)
        e.color = col(v)
    nt.links.new(fac, r.inputs[0])
    return r.outputs[0]


def _math(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _normal(nt, bump, bump_scale, streak):
    """带一点凹凸的法线。streak：拉丝方向上拉长几倍（1 = 不拉；8—12 是拉丝）。"""
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    if bump <= 0:
        return geo, geo.outputs["Normal"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (bump_scale, bump_scale, bump_scale / max(1.0, streak))
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 3.0
    nt.links.new(mp.outputs[0], nz.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = bump
    bp.inputs["Distance"].default_value = 0.02
    nt.links.new(nz.outputs[0], bp.inputs["Height"])
    nt.links.new(geo.outputs["Normal"], bp.inputs["Normal"])
    return geo, bp.outputs["Normal"]


def _env(nt, geo, nrm, scale, distortion, detail, rand):
    """反射方向 → 波浪纹理：一张带条纹的「环境」，返回 0—1。缩放、细节大了会密成斑马纹，小东西上会闪，从 0.5 试起。"""
    neg = nt.nodes.new("ShaderNodeVectorMath")
    neg.operation = "SCALE"
    neg.inputs[3].default_value = -1.0
    nt.links.new(geo.outputs["Incoming"], neg.inputs[0])
    rf = nt.nodes.new("ShaderNodeVectorMath")
    rf.operation = "REFLECT"
    nt.links.new(neg.outputs[0], rf.inputs[0])
    nt.links.new(nrm, rf.inputs[1])
    vec = rf.outputs[0]
    if rand > 0:
        oi = nt.nodes.new("ShaderNodeObjectInfo")
        cb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(oi.outputs["Random"], cb.inputs[0])
        nt.links.new(oi.outputs["Random"], cb.inputs[2])
        sc = nt.nodes.new("ShaderNodeVectorMath")
        sc.operation = "SCALE"
        sc.inputs[3].default_value = rand
        nt.links.new(cb.outputs[0], sc.inputs[0])
        ad = nt.nodes.new("ShaderNodeVectorMath")
        ad.operation = "ADD"
        nt.links.new(vec, ad.inputs[0])
        nt.links.new(sc.outputs[0], ad.inputs[1])
        vec = ad.outputs[0]
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    wv.wave_profile = "SIN"
    wv.inputs["Scale"].default_value = scale
    wv.inputs["Distortion"].default_value = distortion
    wv.inputs["Detail"].default_value = detail
    wv.inputs["Detail Scale"].default_value = 1.2
    nt.links.new(vec, wv.inputs["Vector"])
    return wv.outputs[1]


def _ao(nt, nrm, dist):
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 12
    ao.inputs["Distance"].default_value = dist
    nt.links.new(nrm, ao.inputs["Normal"])
    return ao.outputs["AO"]


def _emit_plate(nt, em, v, k):
    cc = nt.nodes.new("ShaderNodeCombineColor")
    nt.links.new(v, cc.inputs[0])
    if isinstance(k, (int, float)):
        cc.inputs[1].default_value = k
    else:
        nt.links.new(k, cc.inputs[1])
    cc.inputs[2].default_value = 0.0
    nt.links.new(cc.outputs[0], em.inputs["Color"])


# ------------------------------------------------------------------ 一、出「版」

CHROME_STOPS = [(0.0, 0.28), (0.30, 0.28), (0.36, 1.0), (0.47, 1.0), (0.50, 0.42), (0.66, 0.60), (0.72, 1.0), (0.80, 1.0), (0.84, 0.28)]
CHROME_INK = [(0.0, 1.0), (0.07, 0.0), (0.955, 1.0)]          # 只留很窄的一段印墨；墨主要来自缝里的遮蔽
DARK_STOPS = [(0.0, 0.30), (0.44, 0.30), (0.47, 1.0), (0.52, 1.0), (0.55, 0.30), (0.74, 0.30), (0.76, 1.0), (0.79, 0.30)]
DARK_INK = [(0.0, 1.0), (0.44, 0.0), (0.55, 1.0), (0.74, 0.0), (0.79, 1.0)]
LIGHT_STOPS = [(0.0, 0.55), (0.30, 0.55), (0.36, 1.0), (0.60, 1.0), (0.66, 0.70), (0.84, 0.70), (0.88, 1.0)]


def mat_plate(name, v, k=0.0):
    m, nt, em, out = new_mat(name)
    em.inputs["Color"].default_value = (v, k, 0.0, 1.0)
    return m


def mat_chrome(name, stops=None, ink_stops=None, scale=1.3, distortion=3.0, detail=1.5, rand=0.0, rim=0.75, bump=0.12,
               bump_scale=30.0, streak=1.0, ao_dist=0.5, ao_min=0.18, ink_ao=0.38):
    """暗的反光给比底亮一点的值（0.28），不给 0：0 就是底的颜色，印上去等于没有，圈会断成一截一截。"""
    m, nt, em, out = new_mat(name)
    geo, nrm = _normal(nt, bump, bump_scale, streak)
    e = _env(nt, geo, nrm, scale, distortion, detail, rand)
    v = _ramp(nt, e, stops or CHROME_STOPS)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    nt.links.new(nrm, lw.inputs["Normal"])
    v = _math(nt, "MAXIMUM", v, _ramp(nt, lw.outputs["Facing"], [(0.0, 0.0), (rim, 0.0), (min(0.999, rim + 0.12), 1.0)]))
    ao = _ao(nt, nrm, ao_dist)
    v = _math(nt, "MULTIPLY", v, _ramp(nt, ao, [(0.0, ao_min), (0.35, ao_min), (0.9, 1.0)]))
    k = _math(nt, "MAXIMUM", _math(nt, "LESS_THAN", ao, ink_ao), _ramp(nt, e, list(ink_stops or CHROME_INK), "CONSTANT"))
    _emit_plate(nt, em, v, k)
    return m


def mat_glass(name, stops=None, scale=1.6, distortion=4.0, detail=1.0, rand=1.0, rim=0.62, base_alpha=0.10, ao_dist=0.4):
    m, nt, em, out = new_mat(name)
    geo, nrm = _normal(nt, 0.0, 1.0, 1.0)
    e = _env(nt, geo, nrm, scale, distortion, detail, rand)
    v = _ramp(nt, e, stops or [(0.0, 0.0), (0.40, 0.0), (0.44, 1.0), (0.52, 1.0), (0.56, 0.0), (0.78, 0.0), (0.81, 1.0), (0.86, 0.0)])
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    solid = _math(nt, "MAXIMUM", v, _ramp(nt, lw.outputs["Facing"], [(0.0, 0.0), (rim, 0.0), (min(0.999, rim + 0.10), 1.0)]))
    ao = _ao(nt, nrm, ao_dist)
    k = _math(nt, "LESS_THAN", ao, 0.30)
    alpha = _math(nt, "MAXIMUM", _math(nt, "MAXIMUM", solid, k), base_alpha)
    _emit_plate(nt, em, solid, k)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha, mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


def mat_rock(name, rand=0.0, bump=0.5, bump_scale=9.0, ao_dist=0.7, light_dir=(-0.45, 0.55, 0.70), stops=None):
    m, nt, em, out = new_mat(name)
    geo, nrm = _normal(nt, bump, bump_scale, 1.0)
    vt = nt.nodes.new("ShaderNodeVectorTransform")
    vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
    nt.links.new(nrm, vt.inputs[0])
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = Vector(light_dir).normalized()
    nt.links.new(vt.outputs[0], dot.inputs[0])
    t = _math(nt, "MULTIPLY_ADD", dot.outputs["Value"], 0.5, 0.5)
    if rand > 0:
        oi = nt.nodes.new("ShaderNodeObjectInfo")
        t = _math(nt, "FRACT", _math(nt, "MULTIPLY_ADD", oi.outputs["Random"], rand, t))
    v = _ramp(nt, t, stops or [(0.0, 0.0), (0.22, 0.35), (0.34, 1.0), (0.50, 0.7), (0.58, 1.0), (0.70, 0.8), (0.78, 1.0), (0.90, 0.85)], "CONSTANT")
    ao = _ao(nt, nrm, ao_dist)
    v = _math(nt, "MULTIPLY", v, _ramp(nt, ao, [(0.0, 0.25), (0.4, 0.25), (0.95, 1.0)]))
    k = _math(nt, "MAXIMUM", _math(nt, "LESS_THAN", t, 0.22), _math(nt, "LESS_THAN", ao, 0.42))
    _emit_plate(nt, em, v, k)
    return m


def mat_cut(name, scale=4.0, distortion=2.2, ao_dist=0.5):
    m, nt, em, out = new_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type, wv.rings_direction, wv.wave_profile = "RINGS", "Z", "SIN"
    wv.inputs["Scale"].default_value = scale
    wv.inputs["Distortion"].default_value = distortion
    wv.inputs["Detail"].default_value = 2.0
    wv.inputs["Detail Scale"].default_value = 1.5
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    f = wv.outputs[1]
    v = _ramp(nt, f, [(0.0, 0.62), (0.5, 0.80)], "CONSTANT")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    ao = _ao(nt, geo.outputs["Normal"], ao_dist)
    v = _math(nt, "MULTIPLY", v, _ramp(nt, ao, [(0.0, 0.35), (0.4, 0.35), (0.95, 1.0)]))
    k = _math(nt, "MAXIMUM", _math(nt, "GREATER_THAN", f, 0.90), _math(nt, "LESS_THAN", ao, 0.40))
    _emit_plate(nt, em, v, k)
    return m


# ------------------------------------------------------------------ 二、成品的颜色


def mat_flat(name, rgb, strength=1.0):
    m, nt, em, out = new_mat(name)
    em.inputs["Color"].default_value = tuple(rgb) + (1.0,)
    em.inputs["Strength"].default_value = strength
    return m


def mat_metal(name, rough=0.16, base=0.86):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    c = base if isinstance(base, (tuple, list)) else (base, base, base)
    b.inputs["Base Color"].default_value = tuple(c) + (1.0,)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = rough
    return m


def world_reflection_only(sc, hdr=None, strength=1.0, bg=(0.0, 0.0, 0.0), turns=0.0, f0=None, f1=None, transparent=True):
    """镜头看到 bg（transparent=True 时背景渲成透明），反射和折射里看到环境图。没有 hdr 就用一条上亮下暗的渐变当环境。
    turns：从 f0 到 f1 环境绕 Z 转几圈（打线性键）。"""
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    if hdr:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(hdr, check_existing=True)
        nt.links.new(mp.outputs[0], env.inputs["Vector"])
        envc = env.outputs[0]
    else:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(mp.outputs[0], sep.inputs[0])
        envc = _ramp(nt, _math(nt, "MULTIPLY_ADD", sep.outputs[2], 0.5, 0.5),
                     [(0.0, 0.02), (0.48, 0.05), (0.52, 1.2), (0.62, 0.35), (1.0, 0.8)])
    b_env = nt.nodes.new("ShaderNodeBackground")
    b_env.inputs["Strength"].default_value = strength
    nt.links.new(envc, b_env.inputs["Color"])
    b_cam = nt.nodes.new("ShaderNodeBackground")
    b_cam.inputs["Color"].default_value = tuple(bg) + (1.0,)
    lp = nt.nodes.new("ShaderNodeLightPath")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0])
    nt.links.new(b_env.outputs[0], mx.inputs[1])
    nt.links.new(b_cam.outputs[0], mx.inputs[2])
    o = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(mx.outputs[0], o.inputs["Surface"])
    sc.render.film_transparent = transparent
    if turns and f0 is not None and f1 is not None:
        rot = mp.inputs["Rotation"]
        rot.default_value = (0.0, 0.0, 0.0)
        rot.keyframe_insert("default_value", index=2, frame=f0)
        rot.default_value = (0.0, 0.0, turns * 2 * math.pi)
        rot.keyframe_insert("default_value", index=2, frame=f1)
        _linear(nt)
    try:
        sc.eevee.use_raytracing = True
    except Exception:
        pass
    return w


def _linear(idb):
    ad = idb.animation_data
    if ad and ad.action:
        for lay in getattr(ad.action, "layers", []):
            for st in lay.strips:
                cb = st.channelbag(ad.action_slot)
                if cb:
                    for fc in cb.fcurves:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
                        fc.extrapolation = "LINEAR"
                        fc.update()


def mat_glass_dispersion(name, tint=(0.58, 0.83, 1.0), iors=(1.465, 1.5, 1.535), rough=0.02):
    """用三路折射构造色散玻璃，适用于 Cycles。"""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    shaders = []
    for i, ior in enumerate(iors):
        g = nt.nodes.new("ShaderNodeBsdfGlass")
        c = [0.0, 0.0, 0.0]
        c[i] = tint[i]
        g.inputs["Color"].default_value = tuple(c) + (1.0,)
        g.inputs["IOR"].default_value = ior
        g.inputs["Roughness"].default_value = rough
        shaders.append(g.outputs[0])
    a1 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(shaders[0], a1.inputs[0])
    nt.links.new(shaders[1], a1.inputs[1])
    a2 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(a1.outputs[0], a2.inputs[0])
    nt.links.new(shaders[2], a2.inputs[1])
    nt.links.new(a2.outputs[0], out.inputs["Surface"])
    return m


def mat_distance_gradient(name, colors, near=2.0, far=100.0):
    """colors：[(位置 0—1, (r,g,b))]，0 是近（near 米），1 是远（far 米），中间按距离的对数走。"""
    m, nt, em, out = new_mat(name)
    cd = nt.nodes.new("ShaderNodeCameraData")
    lg = _math(nt, "LOGARITHM", cd.outputs["View Distance"], 10.0)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = math.log10(near)
    mr.inputs["From Max"].default_value = math.log10(far)
    nt.links.new(lg, mr.inputs["Value"])
    nt.links.new(_ramp(nt, mr.outputs["Result"], colors), em.inputs["Color"])
    return m


def hue_cycle(mat, period=12.0, f0=0):
    """在材质的自发光颜色前接一道「色相」，色相每 period 帧转一圈。"""
    nt = mat.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    src = em.inputs["Color"].links[0].from_socket if em.inputs["Color"].is_linked else None
    hs = nt.nodes.new("ShaderNodeHueSaturation")
    if src is not None:
        nt.links.new(src, hs.inputs["Color"])
    else:
        hs.inputs["Color"].default_value = em.inputs["Color"].default_value
    val = nt.nodes.new("ShaderNodeValue")
    val.name = "色相进度"
    sock = val.outputs[0]
    sock.default_value = 0.0
    sock.keyframe_insert("default_value", frame=f0)
    sock.default_value = 1.0
    sock.keyframe_insert("default_value", frame=f0 + period)
    _linear(nt)
    hue = _math(nt, "FRACT", _math(nt, "ADD", sock, 0.5))
    nt.links.new(hue, hs.inputs["Hue"])
    nt.links.new(hs.outputs[0], em.inputs["Color"])
    return mat


def mix_to_metal(mat, keys, rough=0.06):
    """keys：[(帧, 金属度 0—1)]，键之间缓起缓停。自发光那一路的颜色同时给金属当底色。"""
    nt = mat.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    pb = nt.nodes.new("ShaderNodeBsdfPrincipled")
    pb.inputs["Metallic"].default_value = 1.0
    pb.inputs["Roughness"].default_value = rough
    if em.inputs["Color"].is_linked:
        nt.links.new(em.inputs["Color"].links[0].from_socket, pb.inputs["Base Color"])
    else:
        pb.inputs["Base Color"].default_value = em.inputs["Color"].default_value
    val = nt.nodes.new("ShaderNodeValue")
    val.name = "金属度"
    for f, v in keys:
        val.outputs[0].default_value = v
        val.outputs[0].keyframe_insert("default_value", frame=f)
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(val.outputs[0], mx.inputs[0])
    nt.links.new(em.outputs[0], mx.inputs[1])
    nt.links.new(pb.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return mat


# ------------------------------------------------------------------ 单独跑：试样场景


def _demo(path, render_dir=None, hdr=None):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 25
    sc.frame_start, sc.frame_end = 1, 48
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    cam_data = bpy.data.cameras.new("相机")
    cam_data.lens = 35
    cam = bpy.data.objects.new("相机", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0.0, -9.0, 2.2)
    cam.rotation_euler = (math.radians(78), 0.0, 0.0)
    sc.camera = cam

    def add(kind, loc, mat, **kw):
        getattr(bpy.ops.mesh, "primitive_%s_add" % kind)(location=loc, **kw)
        ob = bpy.context.active_object
        ob.data.materials.append(mat)
        for p in ob.data.polygons:
            p.use_smooth = True
        return ob
    plates = dict(chrome=mat_chrome("版_铬"), glass=mat_glass("版_玻璃"), rock=mat_rock("版_石", rand=0.6), cut=mat_cut("版_切面"))
    colors = dict(metal=mat_metal("金属_亮", 0.16), metal_dark=mat_metal("金属_暗", 0.20, 0.22),
                  grad=mat_distance_gradient("距离渐变", [(0.0, (0.21, 0.43, 0.72)), (0.8, (0.81, 0.88, 0.96)), (1.0, (0.97, 0.44, 0.67))], 2.0, 60.0))
    colors["hue"] = hue_cycle(mat_flat("转色相", (0.97, 0.44, 0.67)), 12.0, 1)
    colors["to_metal"] = mix_to_metal(mat_flat("变金属", (0.85, 0.87, 0.9)), [(1, 0.0), (48, 0.65)])
    colors["disp"] = mat_glass_dispersion("色散玻璃")
    obs = dict(chrome=add("torus", (-3.0, 0, 1.0), plates["chrome"], major_radius=1.0, minor_radius=0.35),
               glass=add("ico_sphere", (0.0, 0, 1.0), plates["glass"], subdivisions=3, radius=1.0),
               rock=add("ico_sphere", (3.0, 0, 1.0), plates["rock"], subdivisions=2, radius=1.0),
               cut=add("cylinder", (0.0, 3.0, 0.6), plates["cut"], radius=1.4, depth=1.2),
               floor=add("plane", (0.0, 20.0, 0.0), colors["grad"], size=80.0))
    world_reflection_only(sc, hdr, 1.0, (0.0, 0.0, 0.0), 1.0, 1, 48)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("试样场景存了", path)
    if render_dir:
        os.makedirs(render_dir, exist_ok=True)
        sc.frame_set(12)
        sc.view_settings.view_transform = "Raw"
        sc.render.film_transparent = True
        obs["floor"].hide_render = True                     # 地面不是版的材质，这一张不渲它
        sc.render.filepath = os.path.join(render_dir, "版_f0012.png")
        bpy.ops.render.render(write_still=True)
        obs["floor"].hide_render = False
        sc.view_settings.view_transform = "Standard"
        obs["chrome"].data.materials[0] = colors["metal"]
        obs["glass"].data.materials[0] = colors["to_metal"]
        obs["rock"].data.materials[0] = colors["metal_dark"]
        obs["cut"].data.materials[0] = colors["hue"]
        sc.render.filepath = os.path.join(render_dir, "颜色_f0012.png")
        bpy.ops.render.render(write_still=True)
        obs["glass"].data.materials[0] = colors["disp"]
        sc.render.engine = "CYCLES"
        sc.cycles.samples = 32
        sc.render.filepath = os.path.join(render_dir, "色散_Cycles_f0012.png")
        bpy.ops.render.render(write_still=True)
        print("渲了三张：版（Raw、透明底）、成品颜色（EEVEE，Standard）、色散玻璃（Cycles）→", render_dir)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--demo" in a:
        i = a.index("--demo")
        p = a[i + 1]
        rd = a[a.index("--render") + 1] if "--render" in a else None
        hd = a[a.index("--hdr") + 1] if "--hdr" in a else None
        _demo(p, rd, hd)
    else:
        print(__doc__)
