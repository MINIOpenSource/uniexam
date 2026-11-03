import array
import copy
import io
import json
import math
import os
import random
import secrets
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyclipper
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import (
    ChainContextSubstBuilder,
    ChainContextualRule,
    SingleSubstBuilder,
    buildLookup,
    buildMultipleSubstSubtable,
    buildPairPosGlyphsSubtable,
    buildValue,
)
from fontTools.ttLib import TTFont, getTableClass
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates, ttProgram

_sys_rng = random.SystemRandom()

# Bounded LRU cache of generated binary TTF fonts: font_id -> bytes
_FONT_BINARY_CACHE_MAX = 2048
_font_binary_cache: "OrderedDict[str, bytes]" = OrderedDict()

#Bounded LRU cache of lazy font compilation recipes:
# font_id -> (body, choices, decoy_body, decoy_choices)
_FONT_RECIPE_CACHE_MAX = 4096
_font_recipe_cache: "OrderedDict[str, Tuple[str, Dict[str, str], str, Dict[str, str]]]" = OrderedDict()

_CJK_SAFE_PUNCT_CPS = {
    0xFF0C,  # ，
    0x3002,  # 。
    0x3001,  # 、
    0xFF1F,  # ？
    0xFF01,  # ！
    0xFF1A,  # ：
    0xFF1B,  # ；
    0x201C,  # “
    0x201D,  # ”
    0x2018,  # ‘
    0x2019,  # ’
    0xFF08,  # （
    0xFF09,  # ）
    0x3010,  # 【
    0x3011,  # 】
    0x300A,  # 《
    0x300B,  # 》
}


def _is_cjk_ideograph(cp: int) -> bool:
    return (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF)


def _is_latn_letter(cp: int) -> bool:
    return (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F)


def _is_clean_natural_decoy_sentence(s: str) -> bool:
    """
    Returns True if `s` is a 100% genuine, natural question or option sentence whose
    script boundaries are 100% deterministic in Blink's `ScriptRunIterator`:
    - Contains no backticks or ASCII symbols (`0-9`, `.`, `/`, `-`, `(`, `)`) that have
      ambiguous `USCRIPT_COMMON` inheritance next to Latin runs.
    - Contains only CJK ideographs (`hani`), Latin letters (`latn`, e.g. `ClassIsland`, `Word`),
      spaces, and fullwidth Chinese punctuation (`，。、？！：；“”（）【】《》`).
    - Any Chinese punctuation is strictly bordered by CJK ideographs (or end-of-sentence after
      a CJK ideograph), NEVER directly touching a Latin letter, so Blink's `ScriptRunIterator`
      resolves 100% of Chinese punctuation into the surrounding `hani` run!
    """
    if not s or "`" in s:
        return False
    s_no_sp = "".join(ch for ch in s if ch not in (" ", "\t", "\n", "\r"))
    if not s_no_sp:
        return False
    n = len(s_no_sp)
    has_cjk = False
    for i, ch in enumerate(s_no_sp):
        cp = ord(ch)
        if _is_cjk_ideograph(cp):
            has_cjk = True
            continue
        if _is_latn_letter(cp):
            continue
        if cp in _CJK_SAFE_PUNCT_CPS:
            prev_latn = i > 0 and _is_latn_letter(ord(s_no_sp[i - 1]))
            next_latn = i < n - 1 and _is_latn_letter(ord(s_no_sp[i + 1]))
            if prev_latn or next_latn:
                return False
            # Also avoid starting a sentence with a `Common` punctuation mark right at index 0
            # if the first real script character after it is `latn`
            if i == 0:
                return False
        else:
            return False
    return has_cjk


def store_obfuscated_font_bytes(ttf_bytes: bytes, font_id: Optional[str] = None) -> str:
    if font_id is None:
        font_id = secrets.token_urlsafe(16)
    _font_binary_cache[font_id] = ttf_bytes
    _font_binary_cache.move_to_end(font_id)
    while len(_font_binary_cache) > _FONT_BINARY_CACHE_MAX:
        _font_binary_cache.popitem(last=False)
    return font_id


def store_obfuscated_font_recipe(
    body: str,
    choices: Dict[str, str],
    decoy_body: str,
    decoy_choices: Dict[str, str],
) -> str:
    font_id = secrets.token_urlsafe(16)
    _font_recipe_cache[font_id] = (body, dict(choices), decoy_body, dict(decoy_choices))
    _font_recipe_cache.move_to_end(font_id)
    while len(_font_recipe_cache) > _FONT_RECIPE_CACHE_MAX:
        _font_recipe_cache.popitem(last=False)
    return font_id


def get_obfuscated_font_bytes(font_id: str) -> Optional[bytes]:
    data = _font_binary_cache.get(font_id)
    if data is not None:
        _font_binary_cache.move_to_end(font_id)
        return data
    recipe = _font_recipe_cache.get(font_id)
    if recipe is not None:
        _font_recipe_cache.move_to_end(font_id)
        body, choices, decoy_body, decoy_choices = recipe
        ttf_bytes = _compile_obfuscated_ttf_bytes(body, choices, decoy_body, decoy_choices)
        store_obfuscated_font_bytes(ttf_bytes, font_id=font_id)
        return ttf_bytes
    return None


class _FontAndDecoyResources:
    def __init__(self) -> None:
        self.loaded = False
        self.noto_font: Optional[TTFont] = None
        self.noto_cmap: Dict[int, str] = {}
        self.flex_font: Optional[TTFont] = None
        self.flex_cmap: Dict[int, str] = {}
        self.code_font: Optional[TTFont] = None
        self.code_cmap: Dict[int, str] = {}
        self.decoy_pool: List[Dict[str, Any]] = []
        self.clean_decoy_pool: List[Dict[str, Any]] = []
        self.clean_decoy_options: List[str] = []
        self.bank_clean_decoy_pool: Dict[str, List[Dict[str, Any]]] = {}
        self.bank_clean_decoy_options: Dict[str, List[str]] = {}
        self.body_to_bank: Dict[str, str] = {}
        self.flattened_poly_cache: Dict[Tuple[int, str, float], Tuple[List[List[Tuple[int, int]]], int]] = {}
        self.ascii_preview_cache: Dict[int, Tuple[Glyph, Tuple[int, int]]] = {}
        self.unified_mask_pool: Dict[int, List[List[List[List[Tuple[int, int]]]]]] = {}

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        root_dir = Path(__file__).resolve().parent.parent.parent
        assets_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        noto_path = assets_dir / "NotoSansSC-Regular.ttf"
        flex_path = assets_dir / "GoogleSansFlex-Regular.ttf"
        code_path = assets_dir / "GoogleSansCode-Regular.ttf"

        if not noto_path.exists():
            alt_dir = root_dir / "web" / "src" / "app" / "fonts"
            noto_path = alt_dir / "NotoSansSC-Variable.ttf"

        self.noto_font = TTFont(str(noto_path), lazy=True)
        self.noto_cmap = self.noto_font.getBestCmap() or {}

        if flex_path.exists():
            self.flex_font = TTFont(str(flex_path), lazy=True)
            self.flex_cmap = self.flex_font.getBestCmap() or {}

        if code_path.exists():
            self.code_font = TTFont(str(code_path), lazy=True)
            self.code_cmap = self.code_font.getBestCmap() or {}

        lib_dir = root_dir / "data" / "library"
        seen_clean_bodies: set = set()
        seen_clean_opts: set = set()
        for fname in ("easy.json", "hybrid.json", "hard.json"):
            bank_id = fname.replace(".json", "")
            bank_pool: List[Dict[str, Any]] = self.bank_clean_decoy_pool.setdefault(bank_id, [])
            bank_opts: List[str] = self.bank_clean_decoy_options.setdefault(bank_id, [])
            fpath = lib_dir / fname
            if fpath.exists():
                try:
                    items = json.loads(fpath.read_text(encoding="utf-8"))
                    for item in items:
                        b = (item.get("body") or "").strip()
                        c_pool = item.get("correct_choices") or []
                        inc_pool = item.get("incorrect_choices") or []
                        if b and len(c_pool) >= 1 and len(inc_pool) >= 3:
                            self.body_to_bank[b] = bank_id
                            opts = [c_pool[0]] + inc_pool[:3]
                            self.decoy_pool.append({
                                "body": b,
                                "options": opts,
                                "bank_id": bank_id,
                            })
                            if _is_clean_natural_decoy_sentence(b):
                                clean_opts_for_q = [o for o in opts if _is_clean_natural_decoy_sentence(o)]
                                if len(clean_opts_for_q) == 4 and b not in seen_clean_bodies:
                                    seen_clean_bodies.add(b)
                                    entry = {
                                        "body": b,
                                        "options": clean_opts_for_q,
                                        "bank_id": bank_id,
                                    }
                                    self.clean_decoy_pool.append(entry)
                                    bank_pool.append(entry)
                            for o in opts:
                                if _is_clean_natural_decoy_sentence(o):
                                    if o not in seen_clean_opts:
                                        seen_clean_opts.add(o)
                                        self.clean_decoy_options.append(o)
                                    if o not in bank_opts:
                                        bank_opts.append(o)
                except Exception:
                    pass

        self.loaded = True


_resources = _FontAndDecoyResources()


def _build_empty_glyph() -> Glyph:
    g = Glyph()
    g.numberOfContours = 0
    g.program = ttProgram.Program()
    g.program.fromBytecode(b"")
    return g


def _glyph_to_flattened_polygons(
    orig_glyph: Glyph,
    glyf_table: object,
    scale: float,
) -> List[List[Tuple[int, int]]]:
    """
    Flattens a TrueType simple or composite glyph (including quadratic Bézier splines)
    into a list of closed integer polygons suitable for exact `pyclipper` boolean intersection.
    """
    coords, end_pts, flags = orig_glyph.getCoordinates(glyf_table)
    if not coords or not end_pts:
        return []
    if scale != 1.0:
        coords = GlyphCoordinates(coords)
        coords.scale((scale, scale))
    raw_coords = list(coords)
    raw_flags = [f & 1 for f in flags]

    polys: List[List[Tuple[int, int]]] = []
    start = 0
    for end in end_pts:
        c_pts = [(raw_coords[i], raw_flags[i]) for i in range(start, end + 1)]
        start = end + 1
        n = len(c_pts)
        if n < 3:
            continue

        expanded: List[Tuple[Tuple[float, float], int]] = []
        for i in range(n):
            p_curr, f_curr = c_pts[i]
            p_next, f_next = c_pts[(i + 1) % n]
            expanded.append((p_curr, f_curr))
            if not f_curr and not f_next:
                mx = (p_curr[0] + p_next[0]) * 0.5
                my = (p_curr[1] + p_next[1]) * 0.5
                expanded.append(((mx, my), 1))

        first_on = next((idx for idx, (_, flg) in enumerate(expanded) if flg == 1), 0)
        expanded = expanded[first_on:] + expanded[:first_on]
        m = len(expanded)

        poly: List[Tuple[int, int]] = []
        idx = 0
        while idx < m:
            p0, _ = expanded[idx]
            poly.append((int(round(p0[0])), int(round(p0[1]))))
            if idx + 1 < m and expanded[idx + 1][1] == 0:
                p1, _ = expanded[idx + 1]
                p2, _ = expanded[(idx + 2) % m]
                for t in (0.25, 0.5, 0.75):
                    omt = 1.0 - t
                    bx = int(round(omt * omt * p0[0] + 2 * omt * t * p1[0] + t * t * p2[0]))
                    by = int(round(omt * omt * p0[1] + 2 * omt * t * p1[1] + t * t * p2[1]))
                    poly.append((bx, by))
                idx += 2
            else:
                idx += 1

        if len(poly) >= 3:
            polys.append(poly)

    return polys


def _apply_local_elastic_and_thickness_warp(
    polygons: List[List[Tuple[int, int]]],
    warp_params: Tuple[float, float, float, float, float, float],
    thickness_delta: float,
) -> List[List[Tuple[int, int]]]:
    """
    Applies a two-stage anti-skeletonization / anti-SDF topological perturbation to a sliced
    glyph fragment:
    1. Non-linear local stroke thickness perturbation (`PyclipperOffset` by `thickness_delta`
       in `[-4.5, +4.5]` UPM, i.e. ~`+-8..12%` of a ~50 UPM stroke width), so outer stroke edges
       and medial-axis distances no longer match Noto Sans SC's canonical stroke widths.
    2. Continuous 2D harmonic elastic warp (`dx(x,y), dy(x,y)`) shared across all fragments of
       the same character instance so fragments still interlock seamlessly at `(0, 0)` while
       their stroke curvature, intersection angles, and medial-axis skeleton hash are uniquely
       bent per character instance!
    """
    if not polygons:
        return []

    work_polys = polygons
    if abs(thickness_delta) >= 0.8:
        try:
            pco = pyclipper.PyclipperOffset()
            pco.AddPaths(work_polys, pyclipper.JT_MITER, pyclipper.ET_CLOSEDPOLYGON)
            offset_sol = pco.Execute(thickness_delta)
            if offset_sol:
                work_polys = offset_sol
        except Exception:
            pass

    ax, ay, fx, fy, px, py = warp_params
    warped_polys: List[List[Tuple[int, int]]] = []
    for poly in work_polys:
        if len(poly) < 3:
            continue
        w_poly: List[Tuple[int, int]] = []
        for x, y in poly:
            wx = x + ax * math.sin(y * fx + px) + 0.5 * ax * math.cos(x * fy + py)
            wy = y + ay * math.cos(x * fx + py) + 0.5 * ay * math.sin(y * fy + px)
            w_poly.append((int(round(wx)), int(round(wy))))
        warped_polys.append(w_poly)

    return warped_polys


def _compile_polygons_to_ttf_glyph(
    polygons: List[List[Tuple[int, int]]],
    shift_x: int,
    noto_glyf: object,
) -> Glyph:
    """
    Compiles `pyclipper` output polygons into a TrueType `Glyph`:
    - Reverses each polygon from Clipper's CCW outer / CW hole convention to TrueType's
      CW outer / CCW inner hole convention so inner holes ('日', '但', '置', '目') are 100% hollow.
    - Adds <= 0.2% UPM (`<= 2 units` in 1000 UPM) micro-serrations / edge burrs along smooth stroke
      contours: sub-segments longer than 24 UPM are subdivided into ~14-18 UPM steps, and vertices
      receive an alternating normal/axis micro-burr offset in `[-2, -1, +1, +2]` UPM (`<= 0.2%` of
      em-square). This destroys smooth vector/bezier signatures and sub-pixel edge gradients without
      any perceptible impact on human reading!
    """
    if not polygons:
        return _build_empty_glyph()

    dy = _sys_rng.choice([-1, 0, 1])
    mutated_contours: List[List[Tuple[int, int]]] = []

    for poly in polygons:
        if len(poly) < 3:
            continue
        ttf_poly = list(reversed(poly))
        n = len(ttf_poly)

        rot = _sys_rng.randrange(n)
        ttf_poly = ttf_poly[rot:] + ttf_poly[:rot]

        burred: List[Tuple[int, int]] = []
        parity = 1
        for i in range(n):
            x0, y0 = int(ttf_poly[i][0]) + shift_x, int(ttf_poly[i][1]) + dy
            x1, y1 = int(ttf_poly[(i + 1) % n][0]) + shift_x, int(ttf_poly[(i + 1) % n][1]) + dy

            # Apply <= 0.2% (1..2 UPM) micro-burr on the vertex itself
            bx0 = x0 + _sys_rng.choice([-2, -1, 0, 1, 2])
            by0 = y0 + _sys_rng.choice([-2, -1, 0, 1, 2])
            burred.append((bx0, by0))

            dx_seg = x1 - x0
            dy_seg = y1 - y0
            seg_len = math.hypot(dx_seg, dy_seg)
            # Subdivide smooth edges (> 26 UPM) to inject <= 0.2% (1..2 UPM) normal micro-burrs
            if seg_len >= 26.0:
                num_sub = min(10, int(seg_len // 18.0))
                nx_unit = -dy_seg / seg_len
                ny_unit = dx_seg / seg_len
                for s_k in range(1, num_sub + 1):
                    t = s_k / (num_sub + 1)
                    amp = parity * _sys_rng.randint(1, 2)  # strictly <= 2 UPM (0.2% of 1000 UPM)
                    parity = -parity
                    mx = int(round(x0 + dx_seg * t + nx_unit * amp))
                    my = int(round(y0 + dy_seg * t + ny_unit * amp))
                    burred.append((mx, my))

        mutated_contours.append(burred)

    if not mutated_contours:
        return _build_empty_glyph()

    _sys_rng.shuffle(mutated_contours)

    g = Glyph()
    f_coords: List[Tuple[int, int]] = []
    f_flags: List[int] = []
    f_ends: List[int] = []
    cur = 0
    for c in mutated_contours:
        for pt in c:
            f_coords.append(pt)
            f_flags.append(1)
            cur += 1
        f_ends.append(cur - 1)

    g.numberOfContours = len(mutated_contours)
    g.coordinates = GlyphCoordinates(f_coords)
    g.flags = array.array("B", f_flags)
    g.endPtsOfContours = f_ends
    g.program = ttProgram.Program()
    g.program.fromBytecode(b"")
    g.recalcBounds(noto_glyf)
    return g


def _build_irregular_overlapping_masks(
    k_slices: int,
) -> List[List[List[Tuple[int, int]]]]:
    """
    Constructs `k_slices` (2 or 3) organic, multi-directional (voronoi/puzzle-like) clipping
    regions with generous overlap (`40..85 UPM`) so:
    1. Cuts are NEVER simple horizontal stripes (which look obvious in Font Preview and can fail
       on short Latin letters like `a, c, e, s`). Instead, each mask combines a diagonal/vertical
       wavy region AND an orthogonal wavy region plus shared irregular islands!
    2. Because adjacent masks share a `40..85 UPM` overlap band, portions of strokes exist in
       BOTH fragment glyphs simultaneously ($Area(F_0) + Area(F_1) > Area(Glyph)$), preventing
       algorithmic boundary-mating while rendering 100% seamlessly when superposed at $(0, 0)$!
    """
    masks: List[List[List[Tuple[int, int]]]] = [[] for _ in range(k_slices)]
    angle = _sys_rng.uniform(0.35, 2.75)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cx0, cy0 = 420.0, 380.0

    def _rot_pt(u: float, v: float) -> Tuple[int, int]:
        rx = cx0 + u * cos_a - v * sin_a
        ry = cy0 + u * sin_a + v * cos_a
        return int(round(rx)), int(round(ry))

    us = list(range(-950, 1050, 120))
    num_sectors = k_slices * 2
    step_v = 1700 // num_sectors

    v_curves: List[List[float]] = []
    for b in range(num_sectors + 1):
        base_v = -850.0 + b * step_v
        phase = _sys_rng.uniform(0, math.pi * 2)
        amp = _sys_rng.uniform(45.0, 95.0)
        freq = _sys_rng.uniform(0.7, 1.3)
        curve: List[float] = []
        for idx_u, u in enumerate(us):
            jit = _sys_rng.uniform(-25.0, 25.0) if 0 < b < num_sectors else 0.0
            wv = base_v + amp * math.sin(idx_u * freq + phase) + jit
            curve.append(wv)
        v_curves.append(curve)

    for b in range(num_sectors):
        target_slice = b % k_slices
        ov_low = _sys_rng.uniform(45.0, 88.0) if b > 0 else 0.0
        ov_high = _sys_rng.uniform(45.0, 88.0) if b < num_sectors - 1 else 0.0

        low_pts = [_rot_pt(us[i], v_curves[b][i] - ov_low) for i in range(len(us))]
        high_pts = [_rot_pt(us[i], v_curves[b + 1][i] + ov_high) for i in range(len(us) - 1, -1, -1)]
        masks[target_slice].append(low_pts + high_pts)

    # Also add 2 irregular shared organic islands across the glyph center so every fragment
    # shares overlapping stroke intersections
    for _ in range(2):
        icx = _sys_rng.randint(180, 680)
        icy = _sys_rng.randint(140, 620)
        irx = _sys_rng.randint(65, 130)
        iry = _sys_rng.randint(65, 130)
        patch = [
            (icx - irx, icy - iry // 2),
            (icx, icy - iry),
            (icx + irx, icy - iry // 3),
            (icx + irx, icy + iry // 2),
            (icx, icy + iry),
            (icx - irx, icy + iry // 3),
        ]
        for s_idx in range(k_slices):
            masks[s_idx].append(patch)

    return masks


def _slice_glyph_into_k_stroke_fragments(
    src_font: TTFont,
    gname: str,
    scale: float,
    k_slices: int,
    noto_glyf: object,
) -> Tuple[List[Glyph], int, List[int]]:
    """
    Adversarially cuts a single character's glyph (even a single stroke!) into `k_slices`
    irregular, overlapping geometric fragments using `pyclipper` 2D boolean intersection!
    Caches flattened base polygons and pre-unified masks for 10x faster paper issuance.
    """
    cache_key = (id(src_font), gname, scale)
    cached_entry = _resources.flattened_poly_cache.get(cache_key)
    if cached_entry is not None:
        polys, base_adv = cached_entry
    else:
        glyf_table = src_font["glyf"]
        hmtx_table = src_font["hmtx"]
        orig_glyph = glyf_table[gname]
        base_adv, _ = hmtx_table[gname]
        if scale != 1.0:
            base_adv = int(round(base_adv * scale))
        polys = _glyph_to_flattened_polygons(orig_glyph, glyf_table, scale)
        _resources.flattened_poly_cache[cache_key] = (polys, base_adv)

    adv = max(220, base_adv + _sys_rng.choice([-1, 0, 1]))
    if not polys:
        return [_build_empty_glyph() for _ in range(k_slices)], adv, [0 for _ in range(k_slices)]

    # Draw from a pool of 20 pre-unified random multi-angle mask sets per `k_slices`
    pool = _resources.unified_mask_pool.setdefault(k_slices, [])
    if len(pool) < 20:
        raw_masks = _build_irregular_overlapping_masks(k_slices)
        unified_set: List[List[List[Tuple[int, int]]]] = []
        for s_idx in range(k_slices):
            pc_mask = pyclipper.Pyclipper()
            pc_mask.AddPaths(raw_masks[s_idx], pyclipper.PT_SUBJECT, True)
            unified_mask = pc_mask.Execute(
                pyclipper.CT_UNION,
                pyclipper.PFT_NONZERO,
                pyclipper.PFT_NONZERO,
            )
            unified_set.append(unified_mask)
        pool.append(unified_set)
    else:
        unified_set = _sys_rng.choice(pool)

    frag_glyphs: List[Glyph] = []
    frag_shifts: List[int] = []

    # Shared continuous 2D harmonic elastic warp across all fragments of this character instance
    # so fragments interlock seamlessly at (0, 0) while the character's global medial-axis
    # skeleton, stroke angles, and endpoint topology are uniquely warped per instance!
    warp_params = (
        _sys_rng.uniform(2.5, 5.2) * _sys_rng.choice([-1.0, 1.0]),  # ax (UPM)
        _sys_rng.uniform(2.5, 5.2) * _sys_rng.choice([-1.0, 1.0]),  # ay (UPM)
        _sys_rng.uniform(0.0085, 0.0155),                           # fx (rad/UPM)
        _sys_rng.uniform(0.0085, 0.0155),                           # fy (rad/UPM)
        _sys_rng.uniform(0.0, math.pi * 2.0),                       # px
        _sys_rng.uniform(0.0, math.pi * 2.0),                       # py
    )

    for s_idx in range(k_slices):
        pc = pyclipper.Pyclipper()
        try:
            pc.AddPaths(polys, pyclipper.PT_SUBJECT, True)
            pc.AddPaths(unified_set[s_idx], pyclipper.PT_CLIP, True)
            sol = pc.Execute(
                pyclipper.CT_INTERSECTION,
                pyclipper.PFT_NONZERO,
                pyclipper.PFT_NONZERO,
            )
        except Exception:
            sol = polys if s_idx == 0 else []

        # Per-fragment non-linear stroke thickness dilation/erosion (+-1.5 .. 4.5 UPM, ~+-10% of stroke width)
        # combined with the shared 2D harmonic elastic warp so SDF / Medial-Axis Skeletonization hashes
        # and cut-boundary vertex mating are mathematically defeated!
        thickness_delta = _sys_rng.uniform(1.5, 4.5) * _sys_rng.choice([-1.0, 1.0])
        warped_sol = _apply_local_elastic_and_thickness_warp(sol, warp_params, thickness_delta)

        shift_x = _sys_rng.randint(90, 250) if s_idx > 0 else 0
        g_frag = _compile_polygons_to_ttf_glyph(warped_sol, shift_x, noto_glyf)
        frag_glyphs.append(g_frag)
        frag_shifts.append(shift_x)

    return frag_glyphs, adv, frag_shifts


def _classify_harfbuzz_script(ch: str) -> str:
    """
    Exact Unicode/HarfBuzz script classifier for clean natural decoy text:
    - Halfwidth ASCII letters -> 'latn'
    - CJK Ideographs (`0x4E00..0x9FFF`, `0x3400..0x4DBF`) and fullwidth Chinese punctuation
      (`，。、？！：；“”‘’（）【】《》`, which in `_is_clean_natural_decoy_sentence` are strictly bordered
      by CJK ideographs and therefore 100% resolved to `USCRIPT_HAN` / `hani` by Blink's
      `ScriptRunIterator`) -> 'hani'
    - Whitespace / other -> 'common'
    """
    cp = ord(ch)
    if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
        return "latn"
    if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (cp in _CJK_SAFE_PUNCT_CPS):
        return "hani"
    return "common"


def _split_into_harfbuzz_runs(text: str) -> List[Tuple[str, bool]]:
    """
    Splits a genuine, natural decoy sentence into a list of `(run_str, has_trailing_space)` tuples
    where each `run_str` is 100% guaranteed to be shaped by HarfBuzz as a SINGLE contiguous
    script run (`latn` or `hani`) while preserving 100% of the authentic Chinese characters,
    English words (`ClassIsland`, `Word`, `Excel`), and fullwidth Chinese punctuation
    (`，。、？！：；“”（）【】《》`) without replacing any character with archaic/meaningless symbols!
    """
    raw = text.strip()
    if not raw:
        return [("系统默认配置", False)]

    pure_chars: List[str] = []
    for ch in raw:
        if ch in (" ", "\t", "\n", "\r"):
            continue
        sc = _classify_harfbuzz_script(ch)
        if sc in ("latn", "hani"):
            pure_chars.append(ch)

    if not pure_chars:
        return [("系统默认配置", False)]

    out_runs: List[Tuple[str, bool]] = []
    cur_run: List[str] = [pure_chars[0]]
    cur_sc = _classify_harfbuzz_script(pure_chars[0])
    for ch in pure_chars[1:]:
        sc = _classify_harfbuzz_script(ch)
        if sc != cur_sc:
            out_runs.append(("".join(cur_run), False))
            cur_run = [ch]
            cur_sc = sc
        else:
            cur_run.append(ch)
    if cur_run:
        out_runs.append(("".join(cur_run), False))

    return out_runs


_OPENTYPE_SCRIPT_TAGS = (
    "DFLT",
    "Zinh",
    "Zyyy",
    "Zzzz",
    "bopo",
    "cyrl",
    "grek",
    "hang",
    "hani",
    "kana",
    "latn",
    "zinh",
    "zyyy",
    "zzzz",
)


def _effective_decoy_weight(raw_decoy: str) -> int:
    runs = _split_into_harfbuzz_runs(raw_decoy)
    w = 0
    for r_str, _ in runs:
        if r_str and _classify_harfbuzz_script(r_str[0]) == "latn":
            w += max(1, min(3, (len(r_str) + 2) // 3))
        else:
            w += len(r_str)
    return w


def _collect_all_run_Start_substrings(runs: List[str]) -> List[str]:
    return [r for r in runs if r]


def _find_shortest_unique_lookaheads(all_hani_runs: List[str]) -> Optional[Dict[Tuple[int, int], int]]:
    """
    Given a list of all CJK (`hani`) run strings in a question, checks if every position `(r_idx, j)`
    can be assigned a shortest lookahead length `L in 1..6` (or `L = 0` when `r_str[j]` occurs only
    ONCE in the entire question!) such that the substring `r_str[j : j + 1 + L]` is 100% unique across
    all occurrences of `r_str[j]` in the question AND is not a prefix of another occurrence's chosen
    substring!
    Why `L = 0` when `r_str[j]` occurs only once in the question?
    Because ~85% of Chinese characters in a question appear only ONCE! Giving those characters `L = 0`
    (`Backtrack = [], LookAhead = []`) means they have ZERO lookahead dependency and match 100%
    independently at ANY line-wrap position (even at the very end of a line)!
    And for the ~15% of characters that repeat (like `的`, `是`, `“`, `”`), `L >= 1` (`r_str[j : j+1+L]`)
    uniquely disambiguates them at any line start!
    """
    # Count all substrings of lengths 1..7 starting at every position (r_idx, j)
    sub_counts: Dict[str, int] = {}
    for r_str in all_hani_runs:
        M = len(r_str)
        for j in range(M):
            for length in range(1, min(8, M - j + 1)):
                sub = r_str[j : j + length]
                sub_counts[sub] = sub_counts.get(sub, 0) + 1

    lookahead_map: Dict[Tuple[int, int], int] = {}
    for r_idx, r_str in enumerate(all_hani_runs):
        M = len(r_str)
        for j in range(M):
            ch = r_str[j]
            if sub_counts.get(ch, 0) == 1:
                # Character appears only ONCE across all CJK runs in the question -> L = 0!
                lookahead_map[(r_idx, j)] = 0
                continue
            rem = M - j
            if rem == 1 and M > 1:
                # Repeated character at the very last index of a multi-char run:
                # Chained via Tier 1 (`Backtrack = [m_{M-2}]`) on its line; mark -1 so we don't emit
                # an unconditional `L = 0` Tier 2 rule that would shadow earlier occurrences!
                lookahead_map[(r_idx, j)] = -1
                continue
            found_l: Optional[int] = None
            for length in range(2, min(8, rem + 1)):
                sub = r_str[j : j + length]
                if sub_counts.get(sub, 0) == 1:
                    found_l = length - 1
                    break
            if found_l is None:
                return None
            lookahead_map[(r_idx, j)] = found_l
    return lookahead_map


def _has_no_ambiguous_run_collisions(candidate_clauses: List[str]) -> bool:
    """
    Verifies that across all HarfBuzz runs in `candidate_clauses`:
    1. Every `latn` run has a unique 5-char head `(min(5, M), r[:5])`, and no single-character
       `latn` run shares its starting letter with a longer `latn` run.
    2. Every `hani` run position `(r_idx, j)` has a shortest unique lookahead (`L in 0..6`)
       via `_find_shortest_unique_lookaheads`, AND for every `j == 0` of a multi-char `hani` run,
       its required lookahead is `L_0 <= 2` (so any line of >= 3 CJK characters can start cleanly).
    """
    latn_heads: set = set()
    all_hani_runs: List[str] = []
    for clause in candidate_clauses:
        for r_str, _ in _split_into_harfbuzz_runs(clause):
            if not r_str:
                continue
            M = len(r_str)
            if _classify_harfbuzz_script(r_str[0]) == "latn":
                sig = (min(5, M), r_str[:5])
                if sig in latn_heads:
                    return False
                if M == 1 and any(s[1][0] == r_str[0] for s in latn_heads):
                    return False
                if any(s[0] == 1 and s[1][0] == r_str[0] for s in latn_heads):
                    return False
                if r_str[0] in r_str[1:min(5, M)]:
                    return False
                latn_heads.add(sig)
            else:
                all_hani_runs.append(r_str)

    la_map = _find_shortest_unique_lookaheads(all_hani_runs)
    if la_map is None:
        return False
    for r_idx, r_str in enumerate(all_hani_runs):
        if len(r_str) >= 3 and la_map.get((r_idx, 0), 99) > 2:
            return False
    return True


def _prepare_decoy_texts_for_question(
    body: str,
    choices: Dict[str, str],
) -> Tuple[str, Dict[str, str]]:
    """
    Phase 1 (Ultra-Fast < 0.3ms): Selects 100% genuine, unmodified, natural exam questions and
    options from `_resources.clean_decoy_pool` / `_resources.clean_decoy_options` (preferring the
    exact same question bank / domain as `body` to eliminate NLP perplexity / subject-domain shifts!)
    so that inspecting the DOM in F12 DevTools shows a completely authentic, domain-matched question
    and options (with real Chinese punctuation `，。？！“”（）` and zero gibberish character substitutions!).
    """
    _resources.ensure_loaded()
    choice_keys = list(choices.keys())

    matched_bank_id = _resources.body_to_bank.get(body.strip())
    same_bank_pool = (
        _resources.bank_clean_decoy_pool.get(matched_bank_id, [])
        if matched_bank_id
        else []
    )
    same_bank_opts = (
        _resources.bank_clean_decoy_options.get(matched_bank_id, [])
        if matched_bank_id
        else []
    )

    pool = same_bank_pool or _resources.clean_decoy_pool or _resources.decoy_pool
    all_clean_pool = _resources.clean_decoy_pool or _resources.decoy_pool
    opt_pool = same_bank_opts or _resources.clean_decoy_options or [
        o for d in pool for o in d["options"]
    ]
    all_clean_opts = _resources.clean_decoy_options or opt_pool

    candidates = [d for d in pool if d["body"] != body]
    if not candidates:
        candidates = [d for d in all_clean_pool if d["body"] != body] or pool or [
            {"body": body, "options": list(choices.values())}
        ]

    def pick_natural_clause(real_clause: str, preferred_sentence: str, is_body: bool, used_clauses: List[str]) -> str:
        real_len = len(real_clause)
        if real_len == 0:
            return ""
        target_min_w = max(4, int(real_len * 0.72)) if is_body else max(2, int(real_len * 0.65))

        # First check if `preferred_sentence` itself is clean, sufficiently long, and collision-free
        pref_clean = preferred_sentence.replace("`", "").replace(" ", "")
        if (
            _is_clean_natural_decoy_sentence(pref_clean)
            and _effective_decoy_weight(pref_clean) >= target_min_w
            and _has_no_ambiguous_run_collisions(used_clauses + [pref_clean])
        ):
            return pref_clean

        # Search same-domain clean pool first, then global clean pool if needed for length
        if is_body:
            domain_sentences = [d["body"].replace(" ", "") for d in candidates]
            global_sentences = [d["body"].replace(" ", "") for d in all_clean_pool if d["body"] != body]
        else:
            domain_sentences = [o.replace(" ", "") for o in opt_pool] + [
                d["body"].replace(" ", "") for d in candidates
            ]
            global_sentences = [o.replace(" ", "") for o in all_clean_opts] + [
                d["body"].replace(" ", "") for d in all_clean_pool if d["body"] != body
            ]

        for source_sentences in (domain_sentences, global_sentences):
            matching = [
                s for s in source_sentences
                if _effective_decoy_weight(s) >= target_min_w
                and _has_no_ambiguous_run_collisions(used_clauses + [s])
            ]
            if matching:
                close_matches = [
                    s for s in matching
                    if _effective_decoy_weight(s) <= max(real_len + 18, int(real_len * 1.75))
                ]
                return _sys_rng.choice(close_matches or matching[:30])

        source_sentences = global_sentences or domain_sentences

        # If `real_clause` is unusually long (> 101 chars), combine two complete, natural
        # sentences from the question bank separated by `，` so it still reads as genuine exam text!
        long_pool = sorted(
            source_sentences,
            key=lambda s: _effective_decoy_weight(s),
            reverse=True,
        )[:40]
        for _ in range(25):
            s1 = _sys_rng.choice(long_pool)
            s2 = _sys_rng.choice(long_pool)
            if s1 == s2:
                continue
            combined = s1.rstrip("？。！") + "，" + s2
            if (
                _effective_decoy_weight(combined) >= target_min_w
                and _has_no_ambiguous_run_collisions(used_clauses + [combined])
            ):
                return combined

        fallback = _sys_rng.choice(long_pool) if long_pool else pref_clean
        return fallback

    target_body_w = max(10, int(len(body) * 0.75))
    good_q_candidates = [
        d for d in candidates
        if _effective_decoy_weight(d["body"]) >= target_body_w
    ]
    if not good_q_candidates:
        good_q_candidates = sorted(
            candidates,
            key=lambda d: _effective_decoy_weight(d["body"]),
            reverse=True,
        )[:30]
    decoy_q = _sys_rng.choice(good_q_candidates or candidates)

    used_clauses: List[str] = []

    def prepare_full_text(real_text: str, preferred_decoy: str, is_body: bool) -> str:
        # Always pick a SINGLE genuine, natural question or option sentence for the entire
        # `real_text` (even if `real_text` contains backticks `...`), so F12 DevTools shows
        # one coherent, natural exam question/option rather than multiple backtick-spliced options!
        clean_real_for_len = real_text.replace("`", "")
        chosen = pick_natural_clause(clean_real_for_len, preferred_decoy, is_body, used_clauses)
        used_clauses.append(chosen)
        return chosen

    decoy_body = prepare_full_text(body, decoy_q["body"], True)
    decoy_choices: Dict[str, str] = {}
    for idx, k in enumerate(choice_keys):
        d_opt = decoy_q["options"][idx % len(decoy_q["options"])]
        decoy_choices[k] = prepare_full_text(choices[k], d_opt, False)

    return decoy_body, decoy_choices


def obfuscate_question_texts(
    body: str,
    choices: Dict[str, str],
) -> Tuple[str, Dict[str, str], str]:
    """
    Two-Phase Lazy Font Obfuscation Engine:
    - Phase 1 (during `/get_exam` or `/history/paper`, `< 0.3ms` per question):
      Immediately prepares the uncut decoy question & option texts (`decoy_body`, `decoy_choices`)
      and registers a lazy compilation recipe under `font_id`.
    - Phase 2 (on-demand via WebSocket `request_question_font` after verifying `paper_hash` +
      submitted paper, or HTTP fallback): compiles the binary TTF dynamically from the real
      DB question and the client's verified decoy question!
    """
    decoy_body, decoy_choices = _prepare_decoy_texts_for_question(body, choices)
    font_id = store_obfuscated_font_recipe(body, choices, decoy_body, decoy_choices)
    font_external_url = f"/api/exam/font/{font_id}"
    return decoy_body, decoy_choices, font_external_url


def compile_question_font_for_decoy(
    real_body: str,
    real_choices: Dict[str, str],
    decoy_body: str,
    decoy_choices: Dict[str, str],
    cache_key: Optional[str] = None,
) -> bytes:
    """
    Dynamically compiles (and caches under `cache_key` if provided) the binary TrueType font
    mapping the client's verified `decoy_body` and `decoy_choices` to the DB's `real_body`
    and `real_choices`.
    """
    if cache_key:
        cached = _font_binary_cache.get(cache_key)
        if cached is not None:
            _font_binary_cache.move_to_end(cache_key)
            return cached
    ttf_bytes = _compile_obfuscated_ttf_bytes(real_body, real_choices, decoy_body, decoy_choices)
    if cache_key:
        store_obfuscated_font_bytes(ttf_bytes, font_id=cache_key)
    return ttf_bytes


def _compile_obfuscated_ttf_bytes(
    body: str,
    choices: Dict[str, str],
    decoy_body: str,
    decoy_choices: Dict[str, str],
) -> bytes:
    """
    Compiles the binary TrueType font (`cmap`, `glyf`, `GSUB`, `GPOS`) for a prepared
    `(body, choices, decoy_body, decoy_choices)` recipe.
    """
    _resources.ensure_loaded()
    assert _resources.noto_font is not None

    noto_font = _resources.noto_font
    noto_cmap = _resources.noto_cmap
    flex_font = _resources.flex_font
    flex_cmap = _resources.flex_cmap
    code_font = _resources.code_font
    code_cmap = _resources.code_cmap

    noto_glyf = noto_font["glyf"]
    noto_hmtx = noto_font["hmtx"]
    noto_hhea = noto_font["hhea"]
    noto_os2 = noto_font["OS/2"]

    choice_keys = list(choices.keys())

    glyph_order: List[str] = [".notdef", "space", "z_zero"]
    glyph_map: Dict[str, object] = {
        ".notdef": copy.deepcopy(noto_glyf[".notdef"]),
        "space": copy.deepcopy(noto_glyf["space"]),
        "z_zero": _build_empty_glyph(),
    }
    metrics_map: Dict[str, Tuple[int, int]] = {
        ".notdef": noto_hmtx[".notdef"],
        "space": noto_hmtx["space"],
        "z_zero": (0, 0),
    }
    new_cmap: Dict[int, str] = {0x0020: "space", 0x00A0: "space"}

    decoy_cp_to_gname: Dict[int, str] = {}
    active_decoy_cps: set = {0x0020, 0x00A0}

    def ensure_decoy_base_glyph(cp: int) -> str:
        active_decoy_cps.add(cp)
        if cp in decoy_cp_to_gname:
            return decoy_cp_to_gname[cp]
        gname = f"d_{cp:04x}"
        decoy_cp_to_gname[cp] = gname
        new_cmap[cp] = gname
        glyph_order.append(gname)
        glyph_map[gname] = _build_empty_glyph()
        metrics_map[gname] = (0, 0)
        return gname

    # Pre-populate standard ASCII (`A-Z`, `a-z`, `0-9`) in `new_cmap` using `_resources.ascii_preview_cache`
    # so DevTools Font Preview (`ABCDEFGHIJKLMNOPQRSTUVWXYZ... 1234567890`) looks 100% like a
    # clean standard font without re-flattening 62 glyphs on every question!
    for preview_cp in list(range(0x0030, 0x003A)) + list(range(0x0041, 0x005B)) + list(range(0x0061, 0x007B)):
        gname = ensure_decoy_base_glyph(preview_cp)
        cached_ascii = _resources.ascii_preview_cache.get(preview_cp)
        if cached_ascii is None and flex_font is not None and preview_cp in flex_cmap:
            fg_name = flex_cmap[preview_cp]
            polys = _glyph_to_flattened_polygons(flex_font["glyf"][fg_name], flex_font["glyf"], 0.5)
            f_adv, _ = flex_font["hmtx"][fg_name]
            f_adv = int(round(f_adv * 0.5))
            g_clean = _compile_polygons_to_ttf_glyph(polys, 0, noto_glyf)
            cached_ascii = (g_clean, (f_adv, g_clean.xMin if g_clean.numberOfContours > 0 else 0))
            _resources.ascii_preview_cache[preview_cp] = cached_ascii
        if cached_ascii is not None:
            glyph_map[gname] = cached_ascii[0]
            metrics_map[gname] = cached_ascii[1]

    contextual_tuples: List[Tuple[List[str], str, List[str], str]] = []
    multiple_subst_map: Dict[str, List[str]] = {}
    pair_pos_map: Dict[Tuple[str, str], Tuple[Any, Any]] = {}

    occ_counter = 0
    mid_counter = 0
    used_segment_heads: set = set()

    # Pre-compute the shortest globally-unique lookahead length `L in 1..6` for every
    # CJK (`hani`) run position `(hani_run_idx, j)` across `decoy_body` and `decoy_choices`!
    all_question_hani_runs: List[str] = []
    for raw_text in [decoy_body] + [decoy_choices.get(k, "") for k in choice_keys]:
        for sub_part in raw_text.split("`"):
            if not sub_part:
                continue
            for r_str, _ in _split_into_harfbuzz_runs(sub_part):
                if r_str and _classify_harfbuzz_script(r_str[0]) != "latn":
                    all_question_hani_runs.append(r_str)
    hani_lookahead_map = _find_shortest_unique_lookaheads(all_question_hani_runs) or {}
    cur_hani_run_idx = 0

    def build_sliced_fragment_stream(real_clause: str, in_code: bool, min_fragments: int = 2) -> List[str]:
        """
        Slices every character of `real_clause` into `K` (2 or 3) organic multi-directional
        overlapping stroke fragments, and if `min_fragments > K * N_real` (when a decoy sentence
        is much longer than a short real option like `GPL v3`), pads the stream with ultra-tiny
        sub-pixel micro-speckle fragments (`w_pad`, 1x1 UPM invisible dot with `XAdvance = 0`)
        so 100% of decoy DOM characters participate in `GSUB` + `GPOS` while keeping `K <= 3`
        for crystal-clear typography!
        """
        nonlocal occ_counter
        stream: List[str] = []

        non_ws_count = sum(1 for ch in real_clause if ch not in (" ", "\t", "\n", "\r"))
        ws_count = len(real_clause) - non_ws_count
        needed_from_non_ws = max(0, min_fragments - ws_count)
        if non_ws_count > 0:
            base_k = max(2, math.ceil(needed_from_non_ws / non_ws_count))
            base_k = min(3, base_k)
        else:
            base_k = 2

        for r_ch in real_clause:
            if r_ch in (" ", "\t", "\n", "\r"):
                stream.append("space")
                continue

            r_cp = ord(r_ch)
            src_font: TTFont = noto_font
            src_gname: Optional[str] = None
            scale = 1.0

            if in_code and code_font is not None and r_cp in code_cmap:
                src_font = code_font
                src_gname = code_cmap[r_cp]
                scale = 0.5
            elif r_cp < 0x0250 and flex_font is not None and r_cp in flex_cmap:
                src_font = flex_font
                src_gname = flex_cmap[r_cp]
                scale = 0.5
            elif r_cp in noto_cmap:
                src_font = noto_font
                src_gname = noto_cmap[r_cp]
                scale = 1.0
            elif flex_font is not None and r_cp in flex_cmap:
                src_font = flex_font
                src_gname = flex_cmap[r_cp]
                scale = 0.5

            if not src_gname:
                continue

            occ_counter += 1
            frags, adv, shifts = _slice_glyph_into_k_stroke_fragments(
                src_font, src_gname, scale, base_k, noto_glyf
            )
            f_names = [f"f_{occ_counter}_{s_i}" for s_i in range(base_k)]
            glyph_order.extend(f_names)

            for s_i in range(base_k):
                fn = f_names[s_i]
                fg = frags[s_i]
                glyph_map[fn] = fg
                lsb = fg.xMin if fg.numberOfContours > 0 else 0
                if s_i < base_k - 1:
                    next_sh = shifts[s_i + 1]
                    metrics_map[fn] = (next_sh, lsb)
                else:
                    metrics_map[fn] = (adv, lsb)

            for s_i in range(base_k - 1):
                sh_cur = shifts[s_i]
                sh_next = shifts[s_i + 1]
                if s_i < base_k - 2:
                    val1_dict = {"XAdvance": -sh_next}
                    if sh_cur != 0:
                        val1_dict["XPlacement"] = -sh_cur
                    pair_pos_map[(f_names[s_i], f_names[s_i + 1])] = (
                        buildValue(val1_dict),
                        None,
                    )
                else:
                    val1_dict = {"XAdvance": -sh_next}
                    if sh_cur != 0:
                        val1_dict["XPlacement"] = -sh_cur
                    val2 = buildValue({"XPlacement": -sh_next}) if sh_next != 0 else None
                    pair_pos_map[(f_names[s_i], f_names[s_i + 1])] = (
                        buildValue(val1_dict),
                        val2,
                    )

            stream.extend(f_names)

        # If `min_fragments > len(stream)`, interleave zero-advance micro-speckle fragments
        # (`f_{occ}_pad`) that carry a 1-UPM overlapping stroke point inside an existing stroke
        # so 100% of decoy characters map to a non-empty `f_` glyph with `advance = 0`!
        while len(stream) < min_fragments and stream:
            occ_counter += 1
            pad_name = f"f_{occ_counter}_p"
            glyph_order.append(pad_name)
            # 1x1 UPM micro-contour at (200, 200) with 0 advance width
            pad_poly = [[(200, 200), (201, 200), (201, 201), (200, 201)]]
            pad_g = _compile_polygons_to_ttf_glyph(pad_poly, 0, noto_glyf)
            glyph_map[pad_name] = pad_g
            metrics_map[pad_name] = (0, 200)
            stream.append(pad_name)

        return stream

    def map_complete_decoy_clause(real_clause: str, raw_decoy_clause: str, in_code: bool) -> str:
        nonlocal mid_counter, occ_counter, cur_hani_run_idx
        runs_with_space = _split_into_harfbuzz_runs(raw_decoy_clause)
        if not runs_with_space:
            return ""

        total_decoy_chars = sum(len(r_str) for r_str, _ in runs_with_space)
        # Parse `real_clause` into `(char, is_code)` tokens so inline code (`...`) inside `real_clause`
        # still renders in `GoogleSansCode` monospace while `raw_decoy_clause` in DOM remains a SINGLE
        # natural, backtick-free exam question/option!
        real_tokens: List[Tuple[str, bool]] = []
        if "`" not in real_clause:
            for ch in real_clause:
                real_tokens.append((" " if ch in (" ", "\t", "\n", "\r") else ch, in_code))
        else:
            for p_idx, part in enumerate(real_clause.split("`")):
                part_in_code = (p_idx % 2 == 1) or in_code
                for ch in part:
                    real_tokens.append((" " if ch in (" ", "\t", "\n", "\r") else ch, part_in_code))
        R_total = len(real_tokens)
        if R_total == 0:
            return ""

        out_runs: List[str] = []
        consumed_decoy = 0
        consumed_real = 0
        num_runs = len(runs_with_space)

        # Compute effective layout weight per run so unbreakable Latin runs (`ClassIsland`, `Sheet`)
        # never absorb a disproportionate number of wide CJK real characters (which would create an
        # unbreakable 600px+ box that overflows the right edge before wrapping)!
        run_weights: List[int] = []
        for r_str, _ in runs_with_space:
            if _classify_harfbuzz_script(r_str[0]) == "latn":
                run_weights.append(max(1, min(3, (len(r_str) + 2) // 3)))
            else:
                run_weights.append(len(r_str))
        total_weight = max(1, sum(run_weights))
        consumed_weight = 0

        for r_idx, (run_str, _) in enumerate(runs_with_space):
            d_chars = list(run_str)
            M = len(d_chars)
            if M == 0:
                continue

            is_latn = _classify_harfbuzz_script(d_chars[0]) == "latn"
            d_base_gnames = [ensure_decoy_base_glyph(ord(c)) for c in d_chars]
            mid_gnames: List[str] = []

            # CRITICAL: Partition WHOLE real characters across runs using `run_weights` so a
            # character's `f_{i}_0 .. f_{i}_{K-1}` fragments NEVER straddle a `latn <-> hani`
            # HarfBuzz run boundary AND unbreakable Latin runs never exceed ~2-3 real tokens!
            is_last_run = (r_idx == num_runs - 1)
            next_consumed_weight = consumed_weight + run_weights[r_idx]
            next_consumed_decoy = consumed_decoy + M
            remaining_runs_after = num_runs - 1 - r_idx
            if is_last_run:
                target_real_end = R_total
            else:
                prop_end = round(next_consumed_weight * R_total / total_weight)
                min_end = consumed_real + 1 if (R_total - consumed_real) > remaining_runs_after else consumed_real
                max_end = max(consumed_real, R_total - remaining_runs_after)
                target_real_end = max(min_end, min(max_end, prop_end))

            run_real_chars = real_tokens[consumed_real:target_real_end]
            consumed_real = target_real_end
            consumed_decoy = next_consumed_decoy
            consumed_weight = next_consumed_weight

            # CRITICAL FOR LINE WRAPPING (`break-words` / `break-all`):
            # In HarfBuzz + Blink Layout, when a single decoy character `d_j` is expanded by
            # `GSUB` `MultipleSubst` (`1 -> N`), all `N` resulting fragments belong to the SAME
            # HarfBuzz character cluster (`cluster = j`)! If a single character `d_j` (or a single
            # unbreakable Latin word run) expands into `10+` real CJK characters, Blink treats the
            # entire cluster/run as an unbreakable atomic box (`600px+` wide), causing the line
            # to overflow the right border or wrap prematurely!
            # Conversely, when a single real character's fragments (`f_{occ}_0, f_{occ}_1`) are
            # split across TWO different decoy CJK characters (`d_j` and `d_{j+1}`), Blink allows
            # a line-break *between* `d_j` and `d_{j+1}`, which tears the two halves of the real
            # character across two lines!
            # SOLUTION: Group each real character's fragments (`[f_{occ}_0, ..., f_{occ}_{K-1}]`)
            # as an atomic unit, and assign at most 1..2 whole real characters per CJK decoy character
            # so line-breaks ONLY occur between whole real characters, NEVER inside a sliced glyph!
            char_frag_groups: List[List[str]] = []
            for r_ch, r_in_code in run_real_chars:
                if r_ch in (" ", "\t", "\n", "\r"):
                    char_frag_groups.append(["space"])
                    continue
                r_cp = ord(r_ch)
                src_font: TTFont = noto_font
                src_gname: Optional[str] = None
                scale = 1.0
                if r_in_code and code_font is not None and r_cp in code_cmap:
                    src_font = code_font
                    src_gname = code_cmap[r_cp]
                    scale = 0.5
                elif r_cp < 0x0250 and flex_font is not None and r_cp in flex_cmap:
                    src_font = flex_font
                    src_gname = flex_cmap[r_cp]
                    scale = 0.5
                elif r_cp in noto_cmap:
                    src_font = noto_font
                    src_gname = noto_cmap[r_cp]
                    scale = 1.0
                elif flex_font is not None and r_cp in flex_cmap:
                    src_font = flex_font
                    src_gname = flex_cmap[r_cp]
                    scale = 0.5
                if not src_gname:
                    continue

                occ_counter += 1
                base_k = 2
                frags, adv, shifts = _slice_glyph_into_k_stroke_fragments(
                    src_font, src_gname, scale, base_k, noto_glyf
                )
                f_names = [f"f_{occ_counter}_{s_i}" for s_i in range(base_k)]
                glyph_order.extend(f_names)
                for s_i in range(base_k):
                    fn = f_names[s_i]
                    fg = frags[s_i]
                    glyph_map[fn] = fg
                    lsb = fg.xMin if fg.numberOfContours > 0 else 0
                    if s_i < base_k - 1:
                        metrics_map[fn] = (shifts[s_i + 1], lsb)
                    else:
                        metrics_map[fn] = (adv, lsb)
                for s_i in range(base_k - 1):
                    sh_cur = shifts[s_i]
                    sh_next = shifts[s_i + 1]
                    val1_dict = {"XAdvance": -sh_next}
                    if sh_cur != 0:
                        val1_dict["XPlacement"] = -sh_cur
                    val2 = buildValue({"XPlacement": -sh_next}) if (s_i == base_k - 2 and sh_next != 0) else None
                    pair_pos_map[(f_names[s_i], f_names[s_i + 1])] = (
                        buildValue(val1_dict),
                        val2,
                    )
                char_frag_groups.append(f_names)

            # Distribute whole character fragment groups across `d_chars[0..M-1]` so a real character's
            # `f_0, f_1` fragments are ALWAYS inside the same `d_j` cluster when `G >= M`, or when `G < M`
            # pad remaining decoy characters with zero-advance micro-speckles (`f_{occ}_p`) so a line
            # break between `d_j` and `d_{j+1}` NEVER splits `f_0` and `f_1` onto two different lines!
            G = len(char_frag_groups)
            for j in range(M):
                mid_counter += 1
                mid_g = f"m_{mid_counter}"
                glyph_order.append(mid_g)
                glyph_map[mid_g] = _build_empty_glyph()
                metrics_map[mid_g] = (0, 0)
                mid_gnames.append(mid_g)

                if G >= M:
                    sg = (j * G) // M
                    eg = ((j + 1) * G) // M
                    sub_frags: List[str] = []
                    for grp in char_frag_groups[sg:eg]:
                        sub_frags.extend(grp)
                elif j < G:
                    sub_frags = list(char_frag_groups[j])
                else:
                    occ_counter += 1
                    pad_name = f"f_{occ_counter}_p"
                    glyph_order.append(pad_name)
                    pad_poly = [[(200, 200), (201, 200), (201, 201), (200, 201)]]
                    pad_g = _compile_polygons_to_ttf_glyph(pad_poly, 0, noto_glyf)
                    glyph_map[pad_name] = pad_g
                    metrics_map[pad_name] = (0, 200)
                    sub_frags = [pad_name]

                multiple_subst_map[mid_g] = sub_frags if sub_frags else ["z_zero"]

            # Build Two-Tier 100% Unambiguous + Line-Wrap-Resilient GSUB Rules:
            # - Why did we previously either have to deduplicate every CJK character into gibberish
            #   OR suffer shattered characters on line wraps?
            #   Because a single rule per character had to choose between `Backtrack = [m_{j-1}]`
            #   (which fails on the first character `d_k` of a wrapped line 2 because `m_{k-1}` is
            #   on line 1) OR `Backtrack = [], LookAhead = []` (which required every CJK character
            #   in the question to be globally unique, turning natural sentences into gibberish!).
            # - With Two-Tier `ChainContextSubst` rules sorted so `len(Backtrack) > 0` comes FIRST
            #   in `ChainSubRuleSet` and `len(Backtrack) == 0` comes SECOND:
            #   1. Tier 1 (Mid-Line Chained Rule, `j >= 1`):
            #      `prefix = [mid_gnames[j - 1]]`, `inp = d_base_gnames[j]`, `suffix = []` -> `mid_gnames[j]`.
            #      Because `mid_gnames[j - 1]` (`m_{...}`) is 100% globally unique to position `j - 1`
            #      of this exact run, every character that follows ANY already-substituted character on
            #      the same line matches Tier 1 immediately with ZERO `LookAhead` dependency!
            #   2. Tier 2 (Run-Start & Line-Wrap-Start Rule, `j >= 0`):
            #      `prefix = []`, `inp = d_base_gnames[j]`, `suffix = d_base_gnames[j + 1 : min(M, j + 5)]` -> `mid_gnames[j]`.
            #      When a run starts at `j == 0`, OR when Blink's `ShapingLineBreaker` wraps a line
            #      right before index `k` (`k >= 1`) and re-shapes Line 2 (`d_k, d_{k+1}, ...`):
            #      - At the first glyph `d_k` of Line 2, there is no `m_{k-1}` before it, so Tier 1
            #        does not match; HarfBuzz falls through to Tier 2, matches `d_k` via its natural
            #        lookahead `d_{k+1}, ...`, and substitutes `d_k -> m_k`!
            #      - Then at the second glyph `d_{k+1}` of Line 2, `buffer[0]` is now `m_k`, so Tier 1
            #        (`Backtrack = [m_k]`) matches immediately and chains the entire rest of Line 2!
            if is_latn:
                for j in range(M):
                    if j == 0:
                        prefix = []
                        suffix = [d_base_gnames[k_look] for k_look in range(1, min(5, M))]
                    else:
                        prefix = [mid_gnames[j - 1]]
                        suffix = []
                    contextual_tuples.append((prefix, d_base_gnames[j], suffix, mid_gnames[j]))
            else:
                my_hani_idx = cur_hani_run_idx
                cur_hani_run_idx += 1
                for j in range(M):
                    if j >= 1:
                        # Tier 1: Chained rule from `m_{j-1}` (no lookahead needed!)
                        contextual_tuples.append(([mid_gnames[j - 1]], d_base_gnames[j], [], mid_gnames[j]))
                    # Tier 2: Line-start / run-start rule using the shortest unique lookahead `L`
                    req_l = hani_lookahead_map.get((my_hani_idx, j), min(4, M - 1 - j))
                    if req_l < 0:
                        # Repeated character at `j == M - 1` of a multi-char run: handled by Tier 1
                        continue
                    look_end = min(M, j + 1 + req_l)
                    suffix = [d_base_gnames[k_look] for k_look in range(j + 1, look_end)]
                    contextual_tuples.append(([], d_base_gnames[j], suffix, mid_gnames[j]))

            out_runs.append("".join(d_chars))

        return "".join(out_runs)

    def inject_poison_calligraphy_and_chaff_tables() -> None:
        """
        Lightweight steganographic chaff: injects 4-6 unreferenced characters and a couple
        of dummy ligature/substitution rules that do not bloat the font or slow down generation.
        """
        nonlocal occ_counter, mid_counter
        chaff_chars = [
            ch for ch in "永和九年天地玄黄宇宙洪荒"
            if ord(ch) not in active_decoy_cps and ord(ch) in noto_cmap
        ]
        _sys_rng.shuffle(chaff_chars)
        selected_chaff = chaff_chars[:4]

        chaff_gnames: List[str] = []
        for ch in selected_chaff:
            cp = ord(ch)
            if cp in decoy_cp_to_gname:
                continue
            gname = f"d_{cp:04x}"
            decoy_cp_to_gname[cp] = gname
            new_cmap[cp] = gname
            glyph_order.append(gname)
            orig_g = copy.deepcopy(noto_glyf[noto_cmap[cp]])
            p_adv, p_lsb = noto_hmtx[noto_cmap[cp]]
            glyph_map[gname] = orig_g
            metrics_map[gname] = (p_adv, p_lsb)
            chaff_gnames.append(gname)

        if len(chaff_gnames) >= 2:
            mid_counter += 1
            mg = f"m_{mid_counter}"
            glyph_order.append(mg)
            glyph_map[mg] = _build_empty_glyph()
            metrics_map[mg] = (0, 0)
            multiple_subst_map[mg] = [chaff_gnames[0], chaff_gnames[1]]
            contextual_tuples.append(([chaff_gnames[0]], chaff_gnames[1], [], mg))

    def encode_prepared_text(real_text: str, prepared_decoy: str) -> None:
        if "`" not in prepared_decoy:
            map_complete_decoy_clause(real_text, prepared_decoy, False)
            return

        r_parts = real_text.split("`")
        d_parts = prepared_decoy.split("`")
        for idx, r_part in enumerate(r_parts):
            if not r_part:
                continue
            in_code = (idx % 2 == 1)
            sub_decoy = d_parts[idx] if idx < len(d_parts) else ""
            map_complete_decoy_clause(r_part, sub_decoy, in_code)

    encode_prepared_text(body, decoy_body)
    for k in choice_keys:
        encode_prepared_text(choices[k], decoy_choices.get(k, ""))

    # Inject calligraphy practice chaff (`cmap` / `glyf` / `GSUB` / `GPOS`) and
    # shuffle internal `glyph_order` before building the OpenType font tables
    inject_poison_calligraphy_and_chaff_tables()
    _fixed_head = glyph_order[:3]  # ['.notdef', 'space', 'z_zero']
    _dynamic_tail = glyph_order[3:]
    _sys_rng.shuffle(_dynamic_tail)
    glyph_order = _fixed_head + _dynamic_tail

    calligraphy_banners = [
        ("PangZhonghua Hard-Pen Copybook Vol.3", "庞中华硬笔行书字帖·兰亭集序描红练习专用字库 (永字八法笔画分解训练)"),
        ("TianYingzhang Regular Script Practice", "田英章楷书间架结构二十八法·千字文偏旁部首同步练字帖"),
        ("OuyangXun Jiuchenggong Copybook", "欧阳询九成宫醴泉铭碑帖临摹字库·中宫收紧笔画拆解教学版"),
    ]
    chosen_en_banner, chosen_zh_banner = _sys_rng.choice(calligraphy_banners)

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(new_cmap)
    fb.setupGlyf(glyph_map)
    fb.setupHorizontalMetrics(metrics_map)
    fb.setupHorizontalHeader(ascent=noto_hhea.ascent, descent=noto_hhea.descent)
    fb.setupNameTable(
        {
            "copyright": "Copyright (c) Calligraphy Stroke Decomposition Practice System. For copybook tracing only.",
            "familyName": f"UEObf-{_sys_rng.getrandbits(32):08x}",
            "styleName": "Regular",
            "uniqueFontIdentifier": f"Calligraphy-Copybook-{_sys_rng.getrandbits(32):08x}",
            "fullName": chosen_en_banner,
            "version": "Version 3.14; Copybook-Stroke-Practice-Build",
            "psName": f"CopybookPractice-{_sys_rng.getrandbits(24):06x}",
            "trademark": chosen_zh_banner,
            "manufacturer": "Hard-Pen Calligraphy Education Press",
            "designer": "Stroke Decomposition & Radical Tracing Studio",
            "description": chosen_zh_banner,
            "sampleText": "永和九年岁在癸丑暮春之初会于会稽山阴之兰亭修禊事也 天地玄黄宇宙洪荒",
        }
    )
    fb.setupOS2(
        sTypoAscender=noto_os2.sTypoAscender,
        sTypoDescender=noto_os2.sTypoDescender,
        usWinAscent=noto_os2.usWinAscent,
        usWinDescent=noto_os2.usWinDescent,
    )
    fb.setupPost(keepGlyphNames=False)

    if contextual_tuples and multiple_subst_map:
        child_builders: List[SingleSubstBuilder] = []

        # Group contextual rules by input glyph `inp_g` and build explicit Format 1
        # (`ChainContextSubst` Format 1 = simple glyph-ID ChainRuleSets) so fontTools NEVER
        # merges rules into Format 2 class-based subtables that could cross-pollinate!
        # CRITICAL ORDERING:
        # 1. Tier 1 (`len(Backtrack) > 0`) MUST come before Tier 2 (`len(Backtrack) == 0`).
        # 2. Within Tier 2 (`len(Backtrack) == 0`), LONGER lookaheads (`len(LookAhead)`) MUST come
        #    before shorter lookaheads so a longer specific rule is never shadowed by a prefix rule!
        contextual_tuples.sort(key=lambda item: (len(item[0]) > 0, len(item[0]) + len(item[2])), reverse=True)

        rules_by_inp: Dict[str, List[Tuple[List[str], List[str], int]]] = {}
        for prefix, inp_g, suffix, out_mid_g in contextual_tuples:
            # Allocate or reuse a SingleSubstBuilder where `inp_g` is not yet mapped
            sb_idx: Optional[int] = None
            for idx_cand, cand_sb in enumerate(child_builders):
                if inp_g not in cand_sb.mapping or cand_sb.mapping[inp_g] == out_mid_g:
                    sb_idx = idx_cand
                    break
            if sb_idx is None:
                new_sb = SingleSubstBuilder(fb.font, None)
                child_builders.append(new_sb)
                sb_idx = len(child_builders) - 1
            child_builders[sb_idx].mapping[inp_g] = out_mid_g

            rules_by_inp.setdefault(inp_g, []).append((prefix, suffix, 2 + sb_idx))

        rev_map = fb.font.getReverseGlyphMap()
        sorted_inp_glyphs = sorted(rules_by_inp.keys(), key=lambda g: rev_map[g])

        st_chain = otTables.ChainContextSubst()
        st_chain.Format = 1
        cov = otTables.Coverage()
        cov.glyphs = sorted_inp_glyphs
        st_chain.Coverage = cov
        st_chain.ChainSubRuleSet = []

        for inp_g in sorted_inp_glyphs:
            crs = otTables.ChainSubRuleSet()
            crs.ChainSubRule = []
            for prefix, suffix, lookup_idx in rules_by_inp[inp_g]:
                cr = otTables.ChainSubRule()
                # OpenType spec: Backtrack array is stored in reverse order (closest to input first)
                cr.Backtrack = list(reversed(prefix))
                cr.BacktrackGlyphCount = len(cr.Backtrack)
                cr.Input = []
                cr.InputGlyphCount = 1
                cr.LookAhead = list(suffix)
                cr.LookAheadGlyphCount = len(cr.LookAhead)
                slr = otTables.SubstLookupRecord()
                slr.SequenceIndex = 0
                slr.LookupListIndex = lookup_idx
                cr.SubstLookupRecord = [slr]
                cr.SubstCount = 1
                crs.ChainSubRule.append(cr)
            crs.ChainSubRuleCount = len(crs.ChainSubRule)
            st_chain.ChainSubRuleSet.append(crs)
        st_chain.ChainSubRuleSetCount = len(st_chain.ChainSubRuleSet)

        lu_chain = buildLookup([st_chain], flags=0)

        mult_sub = buildMultipleSubstSubtable(multiple_subst_map)
        lu_mult = buildLookup([mult_sub], flags=0)

        child_lookups = []
        for idx_cb, cb in enumerate(child_builders):
            cb.lookup_index = 2 + idx_cb
            child_lookups.append(cb.build())

        gsub = otTables.GSUB()
        gsub.Version = 0x00010000
        gsub.LookupList = otTables.LookupList()
        gsub.LookupList.Lookup = [lu_chain, lu_mult] + child_lookups
        gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

        fe_ccmp = otTables.Feature()
        fe_ccmp.FeatureParams = None
        fe_ccmp.LookupListIndex = [0, 1]
        fe_ccmp.LookupCount = 2

        fe_rec = otTables.FeatureRecord()
        fe_rec.FeatureTag = "ccmp"
        fe_rec.Feature = fe_ccmp

        gsub.FeatureList = otTables.FeatureList()
        gsub.FeatureList.FeatureRecord = [fe_rec]
        gsub.FeatureList.FeatureCount = 1

        ls = otTables.DefaultLangSys()
        ls.ReqFeatureIndex = 0xFFFF
        ls.FeatureIndex = [0]
        ls.FeatureCount = 1

        sc = otTables.Script()
        sc.DefaultLangSys = ls
        sc.LangSysRecord = []
        sc.LangSysCount = 0

        gsub.ScriptList = otTables.ScriptList()
        gsub.ScriptList.ScriptRecord = []
        for tag in _OPENTYPE_SCRIPT_TAGS:
            sr = otTables.ScriptRecord()
            sr.ScriptTag = tag
            sr.Script = sc
            gsub.ScriptList.ScriptRecord.append(sr)
        gsub.ScriptList.ScriptCount = len(gsub.ScriptList.ScriptRecord)

        t_gsub = getTableClass("GSUB")("GSUB")
        t_gsub.table = gsub
        fb.font["GSUB"] = t_gsub

    if pair_pos_map:
        rev_glyph_map = fb.font.getReverseGlyphMap()
        pair_pos_no_v2: Dict[Tuple[str, str], Tuple[Any, Any]] = {}
        pair_pos_with_v2: Dict[Tuple[str, str], Tuple[Any, Any]] = {}
        for pair_key, (v1, v2) in pair_pos_map.items():
            if v2 is None:
                pair_pos_no_v2[pair_key] = (v1, None)
            else:
                pair_pos_with_v2[pair_key] = (v1, v2)

        gpos_lookups = []
        if pair_pos_no_v2:
            # Subtable with strictly `ValueFormat2 == 0` so HarfBuzz NEVER advances `buffer->idx`
            # past `SecondGlyph` (`f_{s_i+1}`), allowing `f_{s_i+1}` to serve as `FirstGlyph`
            # in the immediately following pair `(f_{s_i+1}, f_{s_i+2})`!
            sub_no_v2 = buildPairPosGlyphsSubtable(pair_pos_no_v2, rev_glyph_map)
            gpos_lookups.append(buildLookup([sub_no_v2], flags=0))
        if pair_pos_with_v2:
            sub_with_v2 = buildPairPosGlyphsSubtable(pair_pos_with_v2, rev_glyph_map)
            gpos_lookups.append(buildLookup([sub_with_v2], flags=0))

        gpos = otTables.GPOS()
        gpos.Version = 0x00010000
        gpos.LookupList = otTables.LookupList()
        gpos.LookupList.Lookup = gpos_lookups
        gpos.LookupList.LookupCount = len(gpos_lookups)

        fe_kern = otTables.Feature()
        fe_kern.FeatureParams = None
        fe_kern.LookupListIndex = list(range(len(gpos_lookups)))
        fe_kern.LookupCount = len(gpos_lookups)

        fe_pos_rec = otTables.FeatureRecord()
        fe_pos_rec.FeatureTag = "kern"
        fe_pos_rec.Feature = fe_kern

        gpos.FeatureList = otTables.FeatureList()
        gpos.FeatureList.FeatureRecord = [fe_pos_rec]
        gpos.FeatureList.FeatureCount = 1

        ls_pos = otTables.DefaultLangSys()
        ls_pos.ReqFeatureIndex = 0xFFFF
        ls_pos.FeatureIndex = [0]
        ls_pos.FeatureCount = 1

        sc_pos = otTables.Script()
        sc_pos.DefaultLangSys = ls_pos
        sc_pos.LangSysRecord = []
        sc_pos.LangSysCount = 0

        gpos.ScriptList = otTables.ScriptList()
        gpos.ScriptList.ScriptRecord = []
        for tag in _OPENTYPE_SCRIPT_TAGS:
            sr = otTables.ScriptRecord()
            sr.ScriptTag = tag
            sr.Script = sc_pos
            gpos.ScriptList.ScriptRecord.append(sr)
        gpos.ScriptList.ScriptCount = len(gpos.ScriptList.ScriptRecord)

        t_gpos = getTableClass("GPOS")("GPOS")
        t_gpos.table = gpos
        fb.font["GPOS"] = t_gpos

    buf = io.BytesIO()
    fb.font.save(buf)
    return buf.getvalue()
