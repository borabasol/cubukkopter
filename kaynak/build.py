"""Cubukkopter - tek kisilik, cubuguna tutunulan es eksenli kopter (konsept).
Calistir: blender -b --python kaynak/build.py
Birim: metre, Z yukari, kullanicinin yuzu +Y yonune bakar.
"""
import bpy, bmesh, math, os
from mathutils import Vector, Matrix
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene
TAU = math.tau

# ---------- malzemeler ----------
def mat(name, col, metal=0., rough=.5, emit=0., alpha=1.):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    h = col.lstrip('#'); lin = lambda c: c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
    c = [lin(int(h[i:i+2], 16)/255) for i in (0, 2, 4)] + [1]
    b.inputs['Base Color'].default_value = c
    b.inputs['Metallic'].default_value = metal; b.inputs['Roughness'].default_value = rough
    if emit:
        b.inputs['Emission Color'].default_value = c; b.inputs['Emission Strength'].default_value = emit
    if alpha < 1: b.inputs['Alpha'].default_value = alpha
    return m
PAINT = mat('Paint', '#e4572e', .0, .32)
SHELL = mat('Shell', '#efe9dc', .0, .38)
CARBON = mat('Carbon', '#1d2023', .25, .42)
STEEL = mat('Steel', '#a9adb0', 1., .28)
RUBBER = mat('Rubber', '#111213', 0., .85)
CELL = mat('Cell', '#f2b632', .1, .4)
LAMP = mat('Lamp', '#fff3d6', 0, .2, 4)
LEDR = mat('LedRed', '#ff2b2b', 0, .3, 5)
LEDG = mat('LedGreen', '#2bff6a', 0, .3, 5)
GLASS = mat('Screen', '#0c2a2e', 0, .1, .6)
BODY = mat('RiderBody', '#6f7880', 0, .75)
SUIT = mat('RiderDark', '#3b4248', 0, .8)

# ---------- yardimcilar ----------
def empty(name, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None); S.collection.objects.link(e); e.location = loc; return e
def finish(name, bm, m, parent, smooth=35):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(smooth))
    me.materials.append(m)
    o = bpy.data.objects.new(name, me); S.collection.objects.link(o)
    if parent:
        o.parent = parent
        # parcalar dunya koordinatinda yazilir, ebeveyn konumu dusulur
        me.transform(Matrix.Translation(-world(parent)))
    return o
def world(e):
    v = Vector((0, 0, 0))
    while e: v += e.location; e = e.parent
    return v
def lathe(name, prof, m, parent, seg=64, at=(0, 0), axis='Z', origin=None, smooth=35):
    bm = bmesh.new(); rings = []
    for r, z in prof:
        if r < 1e-6: rings.append([bm.verts.new((0, 0, z))])
        else: rings.append([bm.verts.new((r*math.cos(TAU*i/seg), r*math.sin(TAU*i/seg), z)) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            j = (i+1) % seg
            if len(a) == 1 and len(b) == 1: continue
            if len(a) == 1: bm.faces.new((a[0], b[i], b[j]))
            elif len(b) == 1: bm.faces.new((a[i], a[j], b[0]))
            else: bm.faces.new((a[i], a[j], b[j], b[i]))
    if origin is not None:
        if axis == 'X': bm.transform(Matrix.Rotation(math.pi/2, 4, 'Y'))
        if axis == 'Y': bm.transform(Matrix.Rotation(-math.pi/2, 4, 'X'))
        bm.transform(Matrix.Translation(origin))
    return finish(name, bm, m, parent, smooth)
def smoothpath(pts, n=14):
    pts = [Vector(p) for p in pts]; out = []
    P = [2*pts[0]-pts[1]] + pts + [2*pts[-1]-pts[-2]]
    for k in range(len(pts)-1):
        a, b, c, d = P[k:k+4]
        for i in range(n):
            t = i/n
            out.append(.5*((2*b)+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(3*b-a-3*c+d)*t**3))
    return out+[pts[-1]]
def tube(name, pts, rad, m, parent, seg=20, smooth=True, ell=1., n=14):
    path = smoothpath(pts, n) if smooth and len(pts) > 2 else [Vector(p) for p in pts]
    rf = rad if callable(rad) else (lambda t: rad)
    bm = bmesh.new(); rings = []; nrm = None
    for i, p in enumerate(path):
        t = (path[min(i+1, len(path)-1)]-path[max(i-1, 0)]).normalized()
        if nrm is None: nrm = t.cross(Vector((0, 0, 1)) if abs(t.z) < .9 else Vector((1, 0, 0))).normalized()
        nrm = (nrm-t*nrm.dot(t)).normalized(); bi = t.cross(nrm); r = rf(i/(len(path)-1))
        rings.append([bm.verts.new(p+nrm*r*math.cos(TAU*k/seg)+bi*r*ell*math.sin(TAU*k/seg)) for k in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for k in range(seg): bm.faces.new((a[k], a[(k+1) % seg], b[(k+1) % seg], b[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    return finish(name, bm, m, parent)
def capsule(name, a, b, ra, rb, m, parent, seg=24):
    a, b = Vector(a), Vector(b); d = (b-a); L = d.length; pr = []
    for i in range(9): q = math.pi/2*i/8; pr.append((ra*math.sin(q), -ra*math.cos(q)))
    for i in range(9): q = math.pi/2*i/8; pr.append((rb*math.cos(q), L+rb*math.sin(q)))
    pr[0] = (0, -ra); pr[-1] = (0, L+rb)
    bm = bmesh.new(); rings = []
    for r, z in pr:
        rings.append([bm.verts.new((r*math.cos(TAU*i/seg), r*math.sin(TAU*i/seg), z)) for i in range(seg)] if r > 1e-6 else [bm.verts.new((0, 0, z))])
    for x, y in zip(rings, rings[1:]):
        for i in range(seg):
            j = (i+1) % seg
            if len(x) == 1: bm.faces.new((x[0], y[i], y[j]))
            elif len(y) == 1: bm.faces.new((x[i], x[j], y[0]))
            else: bm.faces.new((x[i], x[j], y[j], y[i]))
    bm.transform(Matrix.Translation(a) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4())
    return finish(name, bm, m, parent, 60)
def ring(name, R, w, h, z, m, parent, seg=160, k=20, a0=0., a1=TAU, r0=0.):
    full = abs(a1-a0-TAU) < 1e-6; bm = bmesh.new(); rs = []
    for i in range(seg if full else seg+1):
        a = a0+(a1-a0)*i/seg
        rs.append([bm.verts.new(((R+w*math.cos(TAU*j/k))*math.cos(a), (R+w*math.cos(TAU*j/k))*math.sin(a), z+h*math.sin(TAU*j/k))) for j in range(k)])
    N = len(rs)
    for i in range(N if full else N-1):
        a, b = rs[i], rs[(i+1) % N]
        for j in range(k): bm.faces.new((a[j], b[j], b[(j+1) % k], a[(j+1) % k]))
    if not full: bm.faces.new(rs[0]); bm.faces.new(rs[-1][::-1])
    return finish(name, bm, m, parent)
def rbox(name, size, loc, m, parent, bev=.012, rot=None):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    bm.transform(Matrix.Diagonal((*size, 1)))
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bev, segments=4, affect='EDGES', profile=.5)
    if rot: bm.transform(Matrix.Rotation(rot[1], 4, rot[0]))
    bm.transform(Matrix.Translation(loc)); return finish(name, bm, m, parent, 40)

# ---------- olculer ----------
Z_PEG, Z_BAR, Z_MAST0, Z_MAST1 = .42, 1.58, .16, 2.40
Z_LOW, Z_UP, R_ROT, R_RING = 2.805, 2.975, 1.16, 1.255
root = empty('Cubukkopter')
def node(n, z=0):
    e = empty(n, (0, 0, z)); e.parent = root; return e

# --- Direk ---
g = node('Mast', 1.2)
lathe('mast_tube', [(0, Z_MAST0), (.030, Z_MAST0), (.030, Z_MAST1), (0, Z_MAST1)], CARBON, g)
for z, h in ((.30, .05), (.86, .035), (1.40, .05), (1.76, .035), (2.28, .10)):
    lathe(f'collar_{z}', [(.030, z-.004), (.041, z), (.043, z+.006), (.043, z+h-.006), (.041, z+h), (.030, z+h+.004)], STEEL, g)
lathe('paint_band', [(.030, 1.80), (.0335, 1.803), (.0335, 2.02), (.030, 2.023)], PAINT, g)
for i in range(3): lathe(f'paint_tick{i}', [(.030, 2.05+i*.035), (.0335, 2.052+i*.035), (.0335, 2.066+i*.035), (.030, 2.068+i*.035)], PAINT, g)
# govdeye yaslanma yastigi (uyluk destegi)
prof = []
for i in range(25):
    t = i/24; prof.append((.030+.030*math.sin(math.pi*t)**.5, .98+.34*t))
lathe('thigh_pad', prof, RUBBER, g, 40)
for z in (1.10, 1.20): lathe(f'pad_seam{z}', [(.056, z-.006), (.0625, z-.004), (.0625, z+.004), (.056, z+.006)], PAINT, g, 48)

# --- Ayak ---
g = node('Foot', .15)
lathe('hub', [(0, .12), (.045, .125), (.062, .15), (.066, .20), (.058, .25), (.040, .285), (0, .285)], SHELL, g, 48)
lathe('hub_band', [(.064, .168), (.0695, .172), (.0695, .198), (.064, .202)], PAINT, g, 48)
for i in range(3):
    a = TAU*i/3+math.pi/2; u = Vector((math.cos(a), math.sin(a), 0)); z = Vector((0, 0, 1))
    tube(f'leg{i}', [u*.045+z*.225, u*.16+z*.215, u*.29+z*.13, u*.37+z*.035], lambda t: .021-.007*t, CARBON, g)
    tube(f'damper{i}', [u*.055+z*.145, u*.235+z*.165], .011, STEEL, g, smooth=False)
    c = u*.376
    lathe(f'shoe{i}', [(0, 0), (.034, 0), (.044, .008), (.044, .018), (.030, .032), (.014, .048), (0, .048)], RUBBER, g, 32, origin=(c.x, c.y, 0))

# --- Ayak basma ---
g = node('Pegs', Z_PEG)
lathe('peg_clamp', [(.030, .375), (.050, .380), (.054, .392), (.054, .452), (.050, .464), (.030, .469)], SHELL, g, 48)
for s in (-1, 1):
    tube(f'peg_arm{s}', [(s*.045, 0, Z_PEG), (s*.10, .0, Z_PEG-.004), (s*.14, .02, Z_PEG)], .014, STEEL, g)
    rbox(f'peg_plate{s}', (.115, .265, .018), (s*.165, .035, Z_PEG+.006), CARBON, g, .008)
    for k in range(6): rbox(f'peg_grip{s}{k}', (.095, .014, .008), (s*.165, -.055+k*.036, Z_PEG+.018), RUBBER, g, .003)
    rbox(f'peg_edge{s}', (.012, .25, .022), (s*.224, .035, Z_PEG+.008), PAINT, g, .004)

# --- Gidon ---
g = node('Handlebar', Z_BAR)
rbox('bar_clamp', (.11, .10, .085), (0, .0, Z_BAR), SHELL, g, .02)
for s in (-1, 1):
    tube(f'bar{s}', [(s*.04, .0, Z_BAR), (s*.13, .03, Z_BAR+.01), (s*.22, .035, Z_BAR+.045), (s*.285, .0, Z_BAR+.06), (s*.33, -.085, Z_BAR+.055)], .0135, STEEL, g)
    tube(f'grip{s}', [(s*.288, -.005, Z_BAR+.060), (s*.315, -.052, Z_BAR+.058), (s*.342, -.118, Z_BAR+.053)], .0195, RUBBER, g)
    tube(f'lever{s}', [(s*.262, .052, Z_BAR+.052), (s*.325, .035, Z_BAR+.052), (s*.372, -.05, Z_BAR+.045)], .0065, STEEL, g, 12)
    lathe(f'grip_end{s}', [(0, -.008), (.018, -.006), (.022, 0), (.018, .006), (0, .008)], PAINT, g, 24, axis='Y', origin=(s*.344, -.124, Z_BAR+.0525))
tilt = Matrix.Rotation(math.radians(38), 4, 'X')
def tilted(o, c):
    c = Vector(c)-world(o.parent); o.data.transform(Matrix.Translation(c) @ tilt @ Matrix.Translation(-c))
c = (0, -.072, Z_BAR+.115)
for nm, pr, m in (('dash_body', [(0, -.022), (.050, -.020), (.062, -.010), (.066, .004), (.060, .012), (.052, .012), (.050, .008), (0, .008)], CARBON),
                  ('dash_screen', [(0, .0095), (.0495, .0095), (.0495, .0075), (0, .0075)], GLASS),
                  ('dash_ring', [(.040, .0098), (.0435, .011), (.047, .0098)], CELL)):
    tilted(lathe(nm, pr, m, g, 48, origin=c), c)
tube('dash_stem', [(0, -.03, Z_BAR+.03), (0, -.066, Z_BAR+.10)], .012, CARBON, g, smooth=False)

# --- Gimbal (kafayi yatiran mafsal) ---
g = node('Gimbal', 2.45)
pr = [(.030, 2.385)]
for i in range(5): pr += [(.062, 2.395+i*.026), (.048, 2.408+i*.026)]
lathe('bellows', pr+[(.03, 2.53)], RUBBER, g, 48, smooth=20)
for i in range(3):
    a = TAU*i/3+math.pi/6; u = Vector((math.cos(a), math.sin(a), 0)); z = Vector((0, 0, 1))
    tube(f'act_lo{i}', [u*.050+z*2.32, u*.088+z*2.43], .013, SHELL, g, smooth=False)
    tube(f'act_hi{i}', [u*.084+z*2.42, u*.122+z*2.545], .007, STEEL, g, smooth=False)
    tube(f'act_pin{i}', [u*.03+z*2.315, u*.06+z*2.315], .009, STEEL, g, smooth=False)

# --- Guc kafasi ---
g = node('Pod', 2.62)
lathe('pod_lower', [(0, 2.525), (.09, 2.525), (.135, 2.532), (.158, 2.550), (.162, 2.572), (.155, 2.580), (0, 2.580)], SHELL, g, 80)
lathe('pod_core', [(0, 2.575), (.105, 2.575), (.105, 2.70), (0, 2.70)], CARBON, g, 64)
for i in range(12):
    a = TAU*(i+.5)/12; u = Vector((math.cos(a), math.sin(a), 0))
    p = u*.128; lathe(f'cell{i}', [(0, 2.582), (.0225, 2.582), (.025, 2.586), (.025, 2.684), (.0225, 2.688), (0, 2.688)], CELL if i % 3 else PAINT, g, 24, origin=(p.x, p.y, 0))
lathe('pod_upper', [(0, 2.70), (.06, 2.715), (.10, 2.712), (.145, 2.704), (.160, 2.694), (.158, 2.686), (.10, 2.684), (0, 2.684)], SHELL, g, 80)
lathe('pod_stripe', [(.160, 2.548), (.1655, 2.553), (.1665, 2.566), (.1625, 2.572)], PAINT, g, 80)
lathe('headlamp_body', [(0, -.05), (.026, -.045), (.040, -.01), (.042, .02), (.038, .024), (.034, .018), (0, .018)], CARBON, g, 40, axis='Y', origin=(0, .165, 2.552))
lathe('headlamp', [(0, .023), (.02, .0225), (.034, .019), (.034, .016), (0, .016)], LAMP, g, 40, axis='Y', origin=(0, .165, 2.552))
lathe('shaft', [(0, 2.69), (.028, 2.69), (.028, 3.03), (0, 3.03)], STEEL, g, 40)
lathe('spacer', [(.028, 2.856), (.060, 2.859), (.066, 2.868), (.066, 2.912), (.060, 2.921), (.028, 2.924)], CARBON, g, 56)
lathe('nose', [(.028, 3.021), (.05, 3.025), (.052, 3.037), (.044, 3.060), (.026, 3.081), (0, 3.089)], PAINT, g, 48)

# --- Koruma halkasi ---
g = node('Ring', 2.89)
ring('ring_body', R_RING, .019, .115, 2.89, SHELL, g, k=32)
ring('ring_band', R_RING+.0150, .006, .030, 2.89, PAINT, g)
ring('ring_led', R_RING, .0075, .006, 2.776, LAMP, g, k=10)
for i in range(6):
    a = TAU*i/6+math.pi/6; u = Vector((math.cos(a), math.sin(a), 0)); z = Vector((0, 0, 1))
    tube(f'spoke{i}', [u*.055+z*2.89, u*.5+z*2.895, u*(R_RING-.005)+z*2.89], lambda t: .017-.006*t, CARBON, g, 16, ell=.75)
    lathe(f'spoke_cap{i}', [(0, 0), (.024, .002), (.030, .012), (.024, .022), (0, .024)], STEEL, g, 24, axis='Z', origin=tuple(u*R_RING+z*2.995))
for s, m in ((1, LEDG), (-1, LEDR)):
    ring(f'nav{s}', R_RING+.0145, .006, .013, 2.945, m, g, seg=14, k=10, a0=(0 if s > 0 else math.pi)-.10, a1=(0 if s > 0 else math.pi)+.10)

# --- Pervaneler ---
def rotor(name, z0, sgn, phase):
    g = node(name, z0)
    lathe(name+'_hub', [(.028, z0-.045), (.066, z0-.042), (.074, z0-.028), (.074, z0+.028), (.066, z0+.042), (.028, z0+.045)], STEEL, g, 48)
    lathe(name+'_hubband', [(.073, z0-.012), (.0765, z0-.009), (.0765, z0+.009), (.073, z0+.012)], PAINT, g, 48)
    for b in range(3):
        for part, m, t0, t1 in (('blade', CARBON, 0, .86), ('tip', PAINT, .86, 1)):
            bm = bmesh.new(); rs = []; NS = 26; NC = 18
            for i in range(NS+1):
                t = t0+(t1-t0)*i/NS; r = .07+(R_ROT-.07)*t
                ease = min(1, t/.16); ease = ease*ease*(3-2*ease)
                chord = (.040*(1-ease)+.150*ease)*(1-.46*max(0, t-.16)/.84)
                if t > .95: chord *= math.sqrt(max(.04, 1-((t-.95)/.05)**2*.96))
                th = (.034*(1-ease)+.0165*ease)*(1-.45*t)
                tw = math.radians(24-17*t)*ease*sgn
                sweep = -.045*max(0, t-.5)**2*4*sgn; V = []
                for k in range(NC):
                    q = TAU*k/NC; cx = math.cos(q)*.5; cy = math.sin(q)*.5*(1+.55*math.cos(q)*ease)
                    x = (cx+.18*ease*0)*chord*sgn+sweep; y = cy*th+(.25-cx*cx)*.10*chord*ease
                    V.append(bm.verts.new((r, x*math.cos(tw)-y*math.sin(tw), x*math.sin(tw)+y*math.cos(tw))))
                rs.append(V)
            for a, c_ in zip(rs, rs[1:]):
                for k in range(NC): bm.faces.new((a[k], a[(k+1) % NC], c_[(k+1) % NC], c_[k]))
            bm.faces.new(rs[0]); bm.faces.new(rs[-1])
            bm.transform(Matrix.Translation((0, 0, z0)) @ Matrix.Rotation(TAU*b/3+phase, 4, 'Z'))
            finish(f'{name}_{part}{b}', bm, m, g, 50)
        a = TAU*b/3+phase; u = Vector((math.cos(a), math.sin(a), 0))
        tube(f'{name}_root{b}', [u*.06+Vector((0, 0, z0)), u*.125+Vector((0, 0, z0))], .025, STEEL, g, smooth=False)
rotor('RotorLower', Z_LOW, 1, 0.2)
rotor('RotorUpper', Z_UP, -1, .95)

# --- Olcek mankeni (1.76 m) ---
g = node('Rider', 0)
Y = -.235; H = Z_PEG+.02
def c2(n, a, b, ra, rb, m): capsule('rd_'+n, a, b, ra, rb, m, g)
def loft(n, secs, m, seg=40):
    """secs: (z, rx, ry, y) elips kesitleri, yumusak gecisli"""
    P = smoothpath([(q[0], q[1], q[2]) for q in secs], 8); Ys = smoothpath([(q[0], q[3], 0) for q in secs], 8)
    pr = []; bm = bmesh.new(); rings = []
    for p, q in zip(P, Ys):
        rx, ry = max(p.y, .002), max(p.z, .002)
        rings.append([bm.verts.new((rx*math.copysign(abs(math.cos(TAU*i/seg))**.85, math.cos(TAU*i/seg)), q.y+ry*math.copysign(abs(math.sin(TAU*i/seg))**.9, math.sin(TAU*i/seg)), p.x)) for i in range(seg)])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg): bm.faces.new((a[i], a[(i+1) % seg], b[(i+1) % seg], b[i]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1]); finish('rd_'+n, bm, m, g, 60)
for s in (-1, 1):
    an, kn, hp = (s*.160, -.030, H+.09), (s*.150, -.020, H+.50), (s*.092, Y-.02, H+.88)
    c2(f'foot{s}', (s*.162, -.045, H+.045), (s*.170, .105, H+.032), .046, .036, SUIT)
    c2(f'shin{s}', an, kn, .046, .062, SUIT); c2(f'thigh{s}', kn, hp, .064, .088, SUIT)
    sh, el, hd = (s*.195, Y-.005, H+1.39), (s*.345, Y-.015, H+1.15), (s*.318, -.085, Z_BAR+.052)
    c2(f'uparm{s}', sh, el, .058, .043, BODY); c2(f'forearm{s}', el, hd, .042, .031, BODY)
    c2(f'hand{s}', (s*.303, -.045, Z_BAR+.058), (s*.332, -.088, Z_BAR+.058), .037, .034, SUIT)
loft('hips', [(H+.80, .03, .03, Y-.02), (H+.83, .13, .10, Y-.02), (H+.90, .172, .122, Y-.02), (H+.98, .158, .112, Y-.02), (H+1.03, .150, .106, Y-.018)], SUIT)
loft('torso', [(H+1.02, .146, .103, Y-.018), (H+1.10, .143, .100, Y-.015), (H+1.22, .172, .116, Y-.012), (H+1.33, .200, .122, Y-.010), (H+1.41, .190, .100, Y-.008), (H+1.455, .110, .072, Y-.004), (H+1.49, .060, .058, Y)], BODY)
lathe('rd_belt', [(.1, H+1.005), (.164, H+1.008), (.164, H+1.04), (.1, H+1.043)], PAINT, g, 48)
for o in list(g.children):
    if o.name == 'rd_belt':
        for v in o.data.vertices: v.co.y = v.co.y*.74+(Y-.018)
c2('neck', (0, Y, H+1.44), (0, Y+.005, H+1.54), .052, .050, BODY)
loft('helmet', [(H+1.500, .060, .070, Y+.015), (H+1.52, .094, .108, Y+.015), (H+1.58, .118, .132, Y+.015), (H+1.65, .124, .138, Y+.010), (H+1.71, .108, .122, Y+.004), (H+1.75, .066, .076, Y), (H+1.765, .012, .014, Y)], SHELL)
loft('visor', [(H+1.575, .06, .05, Y+.07), (H+1.59, .098, .070, Y+.087), (H+1.63, .108, .078, Y+.083), (H+1.67, .100, .072, Y+.080), (H+1.685, .06, .05, Y+.07)], GLASS)

# ---------- rapor + disa aktarim ----------
dg = bpy.context.evaluated_depsgraph_get()
lo, hi, tri = Vector((9,)*3), Vector((-9,)*3), 0
for o in S.objects:
    if o.type != 'MESH': continue
    o.data.calc_loop_triangles(); tri += len(o.data.loop_triangles)
    for v in o.data.vertices:
        p = world(o)+v.co
        if not o.name.startswith('rd_'):
            lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
print('BBOX', [round(x, 3) for x in hi-lo], 'TRI', tri)
# ayni dugum + ayni malzemeyi birlestir (cizim cagrisi azalir)
bpy.context.view_layer.update()
for e in list(root.children):
    by = {}
    for o in e.children: by.setdefault(o.data.materials[0].name, []).append(o)
    for mn, obs in by.items():
        bpy.ops.object.select_all(action='DESELECT')
        for o in obs: o.select_set(True)
        bpy.context.view_layer.objects.active = obs[0]
        if len(obs) > 1: bpy.ops.object.join()
        obs[0].name = f'{e.name}_{mn}'
bpy.ops.export_scene.gltf(filepath=f'{ROOT}/model/cubukkopter.glb', export_format='GLB', export_yup=True)
bpy.ops.object.select_all(action='DESELECT')
for o in S.objects:
    if o.type == 'MESH' and not o.name.startswith('Rider'): o.select_set(True)
bpy.ops.wm.stl_export(filepath=f'{ROOT}/model/cubukkopter.stl', export_selected_objects=True, global_scale=1000)

# ---------- onizleme ----------
w = bpy.data.worlds.new('w'); S.world = w; w.use_nodes = True
bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND'); bg.inputs[0].default_value = (.42, .56, .62, 1); bg.inputs[1].default_value = .55
def area(loc, e, size, tgt=(0, 0, 1.8)):
    l = bpy.data.lights.new('a', 'AREA'); l.energy = e; l.size = size
    o = bpy.data.objects.new('a', l); S.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(tgt)-Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
area((-3, 3.5, 5), 480, 2.5); area((4, 1, 3), 160, 3); area((0, -4, 4), 260, 2)
fl = bpy.data.meshes.new('fl'); fl.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)]); fl.materials.append(mat('Floor', '#c9d0d0', 0, .9))
S.collection.objects.link(bpy.data.objects.new('fl', fl))
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); S.collection.objects.link(co); S.camera = co
S.render.engine = 'BLENDER_EEVEE'; S.render.threads_mode = 'FIXED'; S.render.threads = 2; S.eevee.taa_render_samples = 48
S.view_settings.view_transform = 'Standard'
def shot(fn, loc, tgt, lens, res):
    co.location = loc; co.rotation_euler = (Vector(tgt)-Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); cam.lens = lens
    S.render.resolution_x, S.render.resolution_y = res; S.render.filepath = fn; S.render.image_settings.file_format = 'PNG'; bpy.ops.render.render(write_still=True)
out = os.environ.get('SHOTS')
if out:
    shot(out+'/a.png', (3.6, 5.4, 2.0), (0, 0, 1.62), 48, (1400, 1200))
    shot(out+'/b.png', (-1.5, -1.9, 2.5), (0, 0, 2.45), 32, (1300, 900))
    shot(out+'/c.png', (1.2, -1.5, 1.2), (0, 0, .95), 30, (900, 1200))
    shot(out+'/d.png', (4.6, 0, 1.8), (0, 0, 1.6), 42, (1000, 1100))
