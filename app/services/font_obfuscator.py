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

# Bounded LRU cache of lazy font compilation recipes:
# font_id -> (body, choices, decoy_body, decoy_choices)
_FONT_RECIPE_CACHE_MAX = 4096
_font_recipe_cache: "OrderedDict[str, Tuple[str, Dict[str, str], str, Dict[str, str]]]" = OrderedDict()


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
        for fname in ("easy.json", "hybrid.json", "hard.json"):
            fpath = lib_dir / fname
            if fpath.exists():
                try:
                    items = json.loads(fpath.read_text(encoding="utf-8"))
                    for item in items:
                        b = (item.get("body") or "").strip()
                        c_pool = item.get("correct_choices") or []
                        inc_pool = item.get("incorrect_choices") or []
                        if b and len(c_pool) >= 1 and len(inc_pool) >= 3:
                            self.decoy_pool.append({
                                "body": b,
                                "options": [c_pool[0]] + inc_pool[:3],
                            })
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

        shift_x = _sys_rng.randint(90, 250) if s_idx > 0 else 0
        g_frag = _compile_polygons_to_ttf_glyph(sol, shift_x, noto_glyf)
        frag_glyphs.append(g_frag)
        frag_shifts.append(shift_x)

    return frag_glyphs, adv, frag_shifts


def _classify_harfbuzz_script(ch: str) -> str:
    """
    Exact Unicode/HarfBuzz script classifier:
    - Halfwidth ASCII letters -> 'latn'
    - CJK Ideographs (`0x4E00..0x9FFF`, `0x3400..0x4DBF`) -> 'hani'
    - Everything else (digits `0-9`, quotes `“”`, parentheses `（）`, commas `，`, question marks `？`,
      hyphens `-`, dots `.`) -> 'common'!
      In HarfBuzz, 'common' characters inherit the script of adjacent characters, so keeping
      only pure 'latn' vs pure 'hani' as script-split triggers prevents false run-splitting on
      punctuation like `“` or `，`!
    """
    cp = ord(ch)
    if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
        return "latn"
    if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF):
        return "hani"
    return "common"


def _split_into_harfbuzz_runs(text: str) -> List[Tuple[str, bool]]:
    """
    Splits a natural decoy string into a list of `(run_str, has_trailing_space)` tuples
    where each `run_str` is 100% guaranteed to be shaped by HarfBuzz as a SINGLE contiguous
    script run (`latn` or `hani`) AND preserves natural English words (`ClassIsland`, `.NET`)
    without corrupting their letters!
    - Why did letters previously cause subsequent characters to shatter?
      Because `Common` characters (like `.`, `-`, `:`, `/`, `0-9`, `“`, `”`, `（`, `）`) have
      Unicode `Script=Common`. When a `Common` character sits inside or adjacent to a `latn` run
      (e.g. `.NET`, `v2.0`, `https://`), or between `latn` and `hani` (e.g. `ClassIsland的“`),
      HarfBuzz's script itemizer or paired-punctuation resolver can split or re-assign the
      `Common` character to a different run than our Python classifier predicted!
    - By keeping each run 100% pure (`latn` = ONLY `A-Za-z`, `hani` = ONLY CJK ideographs `0x4E00..0x9FFF`)
      and replacing any `Common` punctuation/digits in the decoy text with natural CJK characters
      (while preserving spaces between words if needed, or joining cleanly), HarfBuzz's script
      boundaries are 100% deterministic (`A-Za-z` = `latn`, CJK = `hani`) with ZERO `Common`
      boundary ambiguity and ZERO corrupted English words!
    """
    raw = text.strip()
    if not raw:
        return [("系统默认配置", False)]

    _CJK_PUNCT_MAP = {
        "，": "且",
        "。": "也",
        "、": "与",
        "“": "之",
        "”": "乎",
        "‘": "其",
        "’": "者",
        "（": "于",
        "）": "以",
        "(": "于",
        ")": "以",
        "？": "哉",
        "?": "哉",
        "！": "矣",
        "!": "矣",
        "：": "乃",
        ":": "乃",
        "；": "则",
        ";": "则",
        "—": "至",
        "-": "至",
        ".": "点",
        "/": "斜",
        "0": "零",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    }

    pure_chars: List[str] = []
    for ch in raw:
        if ch in (" ", "\t", "\n", "\r"):
            continue
        sc = _classify_harfbuzz_script(ch)
        if sc in ("latn", "hani"):
            pure_chars.append(ch)
        elif ch in _CJK_PUNCT_MAP:
            pure_chars.append(_CJK_PUNCT_MAP[ch])
        else:
            pure_chars.append("的")

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


_DISAMBIG_POOL = (
    "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动"
    "同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自"
    "二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日"
    "那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变"
    "条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总"
    "次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指"
    "几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器"
    "压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安"
    "场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集"
    "温传土许步群广石记需段研界拉林律叫且究支识病象蓝春假非久风독"
)
_LATN_DISAMBIG_POOL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_OPENTYPE_SCRIPT_TAGS = ("DFLT", "bopo", "cyrl", "grek", "hang", "hani", "kana", "latn", "zyyy")


def _extract_disambig_runs(
    raw_decoy_clause: str,
    used_segment_heads: set,
    used_cjk_chars: Optional[set] = None,
) -> List[str]:
    runs_with_space = _split_into_harfbuzz_runs(raw_decoy_clause)
    if not runs_with_space:
        return []
    if used_cjk_chars is None:
        used_cjk_chars = set()

    cjk_pool_idx = 0
    pool_len = len(_DISAMBIG_POOL)

    out_runs: List[str] = []
    for run_str, _ in runs_with_space:
        d_chars = list(run_str)
        M = len(d_chars)
        if M == 0:
            continue

        is_latn = _classify_harfbuzz_script(d_chars[0]) == "latn"
        if is_latn:
            head_len = min(5, M)

            def _is_valid_head(chars_list: List[str]) -> bool:
                sig = (M if M < 5 else 5, tuple(chars_list[:head_len]))
                if sig in used_segment_heads:
                    return False
                if M == 1 and any(s[1][0] == chars_list[0] for s in used_segment_heads):
                    return False
                if any(s[0] == 1 and s[1][0] == chars_list[0] for s in used_segment_heads):
                    return False
                if chars_list[0] in chars_list[1:head_len]:
                    return False
                return True

            attempt = 0
            while not _is_valid_head(d_chars) and attempt < 52:
                if attempt == 0 and d_chars[0].swapcase() != d_chars[0]:
                    d_chars[0] = d_chars[0].swapcase()
                else:
                    d_chars[0] = _LATN_DISAMBIG_POOL[attempt % len(_LATN_DISAMBIG_POOL)]
                attempt += 1
            used_segment_heads.add((M if M < 5 else 5, tuple(d_chars[:head_len])))
        else:
            # Deduplicate every CJK character across the question so each CJK character `d_chars[j]`
            # can use a context-free rule (`prefix = []`, `suffix = []`), making line-wrapping
            # 100% invariant to Blink `ShapingLineBreaker` re-shaping at any character boundary!
            for j in range(M):
                ch = d_chars[j]
                if ch in used_cjk_chars:
                    for _ in range(pool_len):
                        cand = _DISAMBIG_POOL[cjk_pool_idx % pool_len]
                        cjk_pool_idx += 1
                        if cand not in used_cjk_chars and _classify_harfbuzz_script(cand) == "hani":
                            ch = cand
                            break
                    else:
                        # Fallback to any unused CJK ideograph in `0x4E00..0x9FA5` present in `noto_cmap`
                        for cp_iter in range(0x4E00, 0x9FA5):
                            cand = chr(cp_iter)
                            if cand not in used_cjk_chars and cp_iter in _resources.noto_cmap:
                                ch = cand
                                break
                    d_chars[j] = ch
                used_cjk_chars.add(ch)

        out_runs.append("".join(d_chars))
    return out_runs


def _prepare_decoy_texts_for_question(
    body: str,
    choices: Dict[str, str],
) -> Tuple[str, Dict[str, str]]:
    """
    Phase 1 (Ultra-Fast < 0.3ms): Picks a decoy question from `_resources.decoy_pool`
    whose CJK character count closely matches `body` (so no single decoy character ever
    expands into a huge unbreakable multi-character cluster that breaks CSS line wrapping!)
    and applies deterministic HarfBuzz run & CJK character deduplication across `body` and `choices`.
    """
    _resources.ensure_loaded()
    choice_keys = list(choices.keys())

    candidates = [d for d in _resources.decoy_pool if d["body"] != body]
    if not candidates:
        candidates = _resources.decoy_pool or [{"body": body, "options": list(choices.values())}]

    target_cjk_min = max(12, int(len(body) * 0.85))
    good_candidates = [
        d for d in candidates
        if sum(1 for ch in d["body"] if _classify_harfbuzz_script(ch) != "latn") >= target_cjk_min
    ]
    if not good_candidates:
        good_candidates = sorted(
            candidates,
            key=lambda d: sum(1 for ch in d["body"] if _classify_harfbuzz_script(ch) != "latn"),
            reverse=True,
        )[:25]
    decoy_q = _sys_rng.choice(good_candidates or candidates)

    used_segment_heads: set = set()
    used_cjk_chars: set = set()

    def _effective_clause_weight(raw_decoy: str) -> int:
        runs = _split_into_harfbuzz_runs(raw_decoy)
        w = 0
        for r_str, _ in runs:
            if r_str and _classify_harfbuzz_script(r_str[0]) == "latn":
                w += max(1, min(3, (len(r_str) + 2) // 3))
            else:
                w += len(r_str)
        return w

    def disambiguate_clause(real_clause: str, raw_decoy_clause: str) -> str:
        real_tokens = [
            (" " if ch in (" ", "\t", "\n", "\r") else ch)
            for ch in real_clause
        ]
        if not real_tokens:
            return ""
        expanded_decoy = raw_decoy_clause
        guard = 0
        while _effective_clause_weight(expanded_decoy) < len(real_tokens) and guard < 6:
            extra = _sys_rng.choice(_resources.decoy_pool)["body"].replace("`", "")
            expanded_decoy = f"{expanded_decoy}，{extra}"
            guard += 1
        return "".join(_extract_disambig_runs(expanded_decoy, used_segment_heads, used_cjk_chars))

    def prepare_full_text(real_text: str, decoy_sentence: str) -> str:
        clean_decoy = decoy_sentence.replace("`", "")
        if "`" not in real_text:
            return disambiguate_clause(real_text, clean_decoy)

        r_parts = real_text.split("`")
        out_parts: List[str] = []
        for idx, r_part in enumerate(r_parts):
            if not r_part:
                out_parts.append("")
                continue
            sub_decoy = (
                clean_decoy
                if idx == 0
                else _sys_rng.choice(_resources.decoy_pool)["options"][idx % 4].replace("`", "")
            )
            out_parts.append(disambiguate_clause(r_part, sub_decoy))
        return "`".join(out_parts)

    decoy_body = prepare_full_text(body, decoy_q["body"])
    decoy_choices: Dict[str, str] = {}
    for idx, k in enumerate(choice_keys):
        d_opt = decoy_q["options"][idx % len(decoy_q["options"])]
        decoy_choices[k] = prepare_full_text(choices[k], d_opt)

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
    - Phase 2 (on-demand when `/api/exam/font/{font_id}` is requested by the browser):
      `get_obfuscated_font_bytes(font_id)` compiles and caches the binary TTF on the fly!
    """
    decoy_body, decoy_choices = _prepare_decoy_texts_for_question(body, choices)
    font_id = store_obfuscated_font_recipe(body, choices, decoy_body, decoy_choices)
    font_external_url = f"/api/exam/font/{font_id}"
    return decoy_body, decoy_choices, font_external_url


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
        nonlocal mid_counter, occ_counter
        runs_with_space = _split_into_harfbuzz_runs(raw_decoy_clause)
        if not runs_with_space:
            return ""

        total_decoy_chars = sum(len(r_str) for r_str, _ in runs_with_space)
        # Keep whitespace inside `real_tokens` so spaces in English phrases (`Apache License 2.0`)
        # are preserved 100% intact!
        real_tokens = [
            (" " if ch in (" ", "\t", "\n", "\r") else ch)
            for ch in real_clause
        ]
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
            for r_ch in run_real_chars:
                if r_ch in (" ", "\t", "\n", "\r"):
                    char_frag_groups.append(["space"])
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

            # Build 100% unambiguous Substitution rules:
            # - For Latin (`latn`) runs:
            #   * j == 0: `prefix = []`, `suffix = d_base_gnames[1:min(5, M)]`
            #   * j >= 1: `prefix = [mid_gnames[j - 1]]`, `suffix = []`
            # - For CJK (`hani`) runs (where every CJK character across the question is unique):
            #   * Every j in 0..M-1 uses `prefix = []`, `suffix = []` so `HB_GLYPH_FLAG_UNSAFE_TO_BREAK == 0`
            #     at every CJK boundary! When Blink's `ShapingLineBreaker` wraps a line at ANY CJK
            #     character `k` and re-shapes Line 1 (`0..k-1`) and Line 2 (`k..M-1`), every CJK
            #     character on BOTH lines matches its GSUB rule 100% independently!
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
                for j in range(M):
                    contextual_tuples.append(([], d_base_gnames[j], [], mid_gnames[j]))

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
        if "`" not in real_text:
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
