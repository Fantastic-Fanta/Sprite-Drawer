"""Shared motion maths: the expression helpers, the config's named motion functions, and the
whole-pixel sprite offsets (style.pixel_bob). Used by render_sprite.py (inside Blender),
sprite_style.py and check_loop.py, so the rendered sub-pixel part of a float and the whole-pixel
shift of the finished sprite always come from the same formula.

motion.functions {name: expr in t}: named functions of the loop position t (0..1), callable from
every pose expression and from each other (e.g. "FY": "hover(t) + lift(t)").
style.pixel_bob {"y": expr, "x": expr}: whole-pixel shift of each finished sprite (+y = up,
+x = right), rounded per frame; the pose renders the leftover fraction (e.g. FY - round(FY)).
The older form {amplitude, cycles, phase[, slow_time]} (a vertical sine) still works.
"""
import math


def slow_t(f, n, fast):
    """frame f of n -> 0..1 loop position with style.fast_frames removed (held during them)"""
    total = sum(b - a for a, b in fast)
    lost = 0
    for a, b in sorted(fast):
        if f >= b:
            lost += b - a
        elif f > a:
            return (a - lost) / (n - total)
    return (f - lost) / (n - total)


def _clamp(x):
    return min(1.0, max(0.0, x))


def helpers():
    """functions every pose / motion expression can use.
    smooth / smoother: eased 0..1 ramps (smoothstep / smootherstep, clamped);
    bump(x): 0 -> 1 -> 0 over 0..1 (sin^2: no jolt at either end);
    damp(x, k): a decaying wobble over 0..1 - k half-swings, amplitude (1-x)^2, eased in, 0 outside;
    jitter(x, k): a shake over 0..1 - k half-swings of a square wave (each swing held for whole
      frames: a pixel-art shake), under a bump envelope, 0 outside;
    wave(p, skew): one cycle per unit of p, a sine whose crest is broad and trough is narrow
      (skew 0 = plain sine): something buoyant hangs at the top and turns quickly at the bottom"""
    def damp(x, k):
        # eased in over the first half-swing (starts at zero speed), so it can join a motion smoothly
        if x <= 0 or x >= 1:
            return 0.0
        u = min(1.0, k * x)
        return math.sin(k * math.pi * x) * (1 - x) ** 2 * u * u * (3 - 2 * u)

    def jitter(x, k):
        if x <= 0 or x >= 1:
            return 0.0
        return (1.0 if int(k * x) % 2 == 0 else -1.0) * math.sin(math.pi * x) ** 2

    def wave(p, skew=0.0):
        th = 2 * math.pi * p
        # sin + 2 skew cos^2: crest (+1) and trough (-1) stay put; crest curvature 1 - 4 skew
        # (flatter), trough 1 + 4 skew (sharper); skew <= 0.25 keeps a single crest
        return math.sin(th) + 2 * skew * math.cos(th) ** 2

    return dict(pi=math.pi, sin=math.sin, cos=math.cos, exp=math.exp, abs=abs, min=min, max=max, round=round,
                smooth=lambda x: (lambda u: u * u * (3 - 2 * u))(_clamp(x)),
                smoother=lambda x: (lambda u: u ** 3 * (u * (6 * u - 15) + 10))(_clamp(x)),
                bump=lambda x: math.sin(math.pi * _clamp(x)) ** 2,
                damp=damp, jitter=jitter, wave=wave)


def env(cfg, params=None):
    """helpers + pose params + the config's motion.functions, compiled (they may call each other)"""
    e = dict(helpers())
    e.update(cfg["pose_params"] if params is None else params)
    e["__builtins__"] = {}
    for name, expr in cfg.get("motion", {}).get("functions", {}).items():
        e[name] = eval(f"lambda t: {expr}", e)
    return e


def offsets(cfg, n):
    """[(dy, dx)] whole-pixel shift per frame from style.pixel_bob (+dy = up, +dx = right)"""
    pb = cfg["style"].get("pixel_bob")
    if not pb:
        return [(0, 0)] * n
    if "amplitude" in pb:
        Af, ff = float(pb["amplitude"]), cfg["style"].get("fast_frames", [])
        return [(int(round(Af * math.sin(2 * math.pi * pb.get("cycles", 1) * (slow_t(i, n, ff) if pb.get("slow_time") else i / n)
                                         + pb.get("phase", 0.0)))), 0) for i in range(n)]
    e = env(cfg)
    ev = lambda expr, t: int(round(eval(expr, e, {"t": t}))) if expr else 0
    return [(ev(pb.get("y"), i / n), ev(pb.get("x"), i / n)) for i in range(n)]
