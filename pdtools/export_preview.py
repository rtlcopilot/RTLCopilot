

import os
import sys
import glob

import pya

IMAGE_SIZE = 2048
BG_COLOR = (26, 26, 46)          # dark navy background
DIE_COLOR = (139, 92, 246)       # purple die boundary

# api.py invokes this script with capture_output=True and discards stdout,
# so debug output is also teed to '<output>.log' next to the PNG, which is
# visible on the host under pd_work/<run_id>/.
_LOG_FH = None


def _log(msg):
    print(msg, flush=True)
    if _LOG_FH:
        try:
            _LOG_FH.write(msg + "\n")
            _LOG_FH.flush()
        except Exception:
            pass

LAYER_COLORS = [
    (100, 180, 100), (180, 100, 100), (100, 100, 180), (180, 180, 100),
    (100, 180, 180), (180, 100, 180), (200, 150,  80), ( 80, 200, 150),
    (220, 120, 120), (120, 220, 120), (120, 120, 220), (220, 220, 120),
]
MIN_PX = 0.5                     # cull shapes smaller than this in pixels


def _load_lyp():
    """Load a KLayout .lyp layer-properties palette (colors + stack order).

    Source: -rd lyp=<path>, else the sky130hd palette shipped with ORFS if
    present. Returns {(layer, datatype): {fill, frame, visible, order, name}}.
    Empty dict -> fall back to the built-in color cycle.
    """
    import re as _re
    import xml.etree.ElementTree as _ET
    path = str(globals().get("lyp", "") or "")
    if not path:
        cands = sorted(glob.glob(
            "/OpenROAD-flow-scripts/flow/platforms/*/*.lyp"))
        sky = [p for p in cands if "sky130hd" in p]
        path = (sky or cands or [""])[0]
    if not path or not os.path.exists(path):
        return {}
    try:
        root = _ET.parse(path).getroot()
    except Exception as e:
        _log("[WARN] could not parse lyp palette: " + str(e))
        return {}

    def _hex(s):
        s = (s or "").lstrip("#")
        if len(s) >= 6:
            try:
                return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
        return None

    m = {}
    order = 0
    for pr in root.iter("properties"):
        srcs = pr.findtext("source") or ""
        mt = _re.match(r"\s*(\d+)/(\d+)", srcs)
        if not mt:
            continue
        key = (int(mt.group(1)), int(mt.group(2)))
        if key in m:
            continue
        vis = (pr.findtext("visible") or "true").strip().lower() != "false"
        fill = _hex(pr.findtext("fill-color")) or _hex(pr.findtext("frame-color"))
        frame = _hex(pr.findtext("frame-color")) or fill
        name = (pr.findtext("name") or "").strip().lower()
        m[key] = {"fill": fill, "frame": frame, "visible": vis,
                  "order": order, "name": name}
        order += 1
    _log("[DEBUG] lyp palette: %s (%d layers)" % (path, len(m)))
    return m


def _fail(msg):
    print("[ERROR] " + msg, file=sys.stderr)
    _log("[ERROR] " + msg)
    sys.exit(1)


# PIL import 

def _pymods_candidates(start_path):
    """Yield '<ancestor>/.pymods' dirs for every ancestor of start_path.

    The input file lives under the persistent work volume, so a package dir
    installed at e.g. <work>/.pymods survives container recreation (the
    container is run with --rm, so docker-exec pip installs do not persist
    anywhere else).
    """
    d = os.path.dirname(os.path.abspath(start_path))
    while True:
        yield os.path.join(d, ".pymods")
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent


def _import_pil(input_hint):
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except ImportError:
        pass

    # KLayout may run an embedded Python whose sys.path does not include the
    # system site-packages where `pip3 install Pillow` installed PIL.
    _log("[DEBUG] PIL not on default sys.path; executable=" + str(sys.executable))
    _log("[DEBUG] python " + sys.version.replace("\n", " "))

    candidates = list(_pymods_candidates(input_hint))
    for pat in (
        "/usr/lib/python3*/dist-packages",
        "/usr/lib/python3*/site-packages",
        "/usr/lib/python3/dist-packages",
        "/usr/local/lib/python3*/dist-packages",
        "/usr/local/lib/python3*/site-packages",
        os.path.expanduser("~/.local/lib/python3*/site-packages"),
    ):
        candidates.extend(glob.glob(pat))

    added = []
    for d in candidates:
        if os.path.isdir(os.path.join(d, "PIL")) and d not in sys.path:
            sys.path.append(d)
            added.append(d)

    if added:
        _log("[DEBUG] appended to sys.path: " + repr(added))

    try:
        from PIL import Image, ImageDraw
        _log("[DEBUG] PIL imported after sys.path fix")
        return Image, ImageDraw
    except ImportError as e:
        print("[ERROR] PIL is not importable inside KLayout's Python.",
              file=sys.stderr)
        print("[ERROR] import error: " + str(e), file=sys.stderr)
        print("[ERROR] sys.executable: " + str(sys.executable), file=sys.stderr)
        print("[ERROR] sys.path: " + repr(sys.path), file=sys.stderr)
        print("[ERROR] Fix (persists across container restarts): "
              "docker exec rtlcopilot-pd pip3 install --target /work/.pymods "
              "--python-version 3.10 --only-binary=:all: Pillow",
              file=sys.stderr)
        print("[ERROR] Or bake it into the Docker image (RUN pip3 install "
              "--target /usr/local/lib/python3.10/dist-packages Pillow).",
              file=sys.stderr)
        sys.exit(2)


# inputs 

input_path = globals().get("input", "")
output_path = globals().get("output", "")

if not input_path:
    _fail("input required (klayout -rd input=...)")
if not output_path:
    _fail("output required (klayout -rd output=...)")
if not os.path.exists(input_path):
    _fail("input not found: " + input_path)

try:
    _LOG_FH = open(output_path + ".log", "w")
except Exception:
    _LOG_FH = None

Image, ImageDraw = _import_pil(input_path)

# loading layout

layout = pya.Layout()
layout.read(input_path)

top_cells = layout.top_cells()
if not top_cells:
    _fail("no top-level cell found in " + input_path)

# Prefer the top cell with the largest bbox 
top_cell = max(top_cells, key=lambda c: c.bbox().area())
_log("[DEBUG] top_cells: " + repr([c.name for c in top_cells])
      + " -> using '" + top_cell.name + "'")

bbox = top_cell.bbox()          # includes sub-cell instances
if bbox.empty():
    _fail("empty bounding box for cell '" + top_cell.name + "'")

dbu = layout.dbu                # micrometers per database unit
x1 = bbox.left * dbu
y1 = bbox.bottom * dbu
x2 = bbox.right * dbu
y2 = bbox.top * dbu
W = x2 - x1
H = y2 - y1

_log("[DEBUG] dbu=%g um/DBU" % dbu)
_log("[DEBUG] bbox (um): x1=%g y1=%g x2=%g y2=%g  W=%g H=%g"
      % (x1, y1, x2, y2, W, H))

if W <= 0 or H <= 0:
    _fail("degenerate bbox: W=%g H=%g" % (W, H))

# coordinate mapping 

margin = 0.05
scale = min(IMAGE_SIZE * (1 - 2 * margin) / W,
            IMAGE_SIZE * (1 - 2 * margin) / H)
ox = (IMAGE_SIZE - W * scale) / 2.0
oy = (IMAGE_SIZE - H * scale) / 2.0

_log("[DEBUG] scale=%g px/um  ox=%g oy=%g" % (scale, ox, oy))


def to_px(x_um, y_um):
    """Map layout micron coordinates to image pixels (y flipped)."""
    px = ox + (x_um - x1) * scale
    py = IMAGE_SIZE - (oy + (y_um - y1) * scale)
    return px, py


# Draw

img = Image.new("RGBA", (IMAGE_SIZE, IMAGE_SIZE), color=BG_COLOR + (255,))

_LYP = _load_lyp()


def _ld(li_idx):
    info = layout.get_info(li_idx)
    return (info.layer, info.datatype)


layer_indexes = list(layout.layer_indexes())
if _LYP:
    # Draw in palette (stack) order: lower layers first, unmapped last.
    layer_indexes.sort(key=lambda li_idx: _LYP.get(_ld(li_idx), {})
                       .get("order", 10**6))
_log("[DEBUG] layer_indexes: " + repr(layer_indexes))

FILL_ALPHA = 150                 # translucent fills so overlapping layers show
die_area_dbu = float(bbox.area())
HUGE_FRAC = 0.90                 # shapes covering >=90% of die: outline only

total_shapes = 0
drawn = 0
culled = 0

for order, li in enumerate(layer_indexes):
    info = layout.get_info(li)
    props = _LYP.get(_ld(li)) if _LYP else None
    alpha = FILL_ALPHA
    if props is not None:
        # Palette-driven rendering: skip hidden and annotation layers, use
        # the PDK's colors, and keep large area layers (wells) faint so
        # they don't wash out the drawing layers above them.
        nm = props["name"]
        if not props["visible"] or ".label" in nm or nm.endswith("label"):
            _log("[DEBUG] layer %s skipped (palette: hidden/label)"
                 % str(info))
            continue
        color = props["fill"] or LAYER_COLORS[order % len(LAYER_COLORS)]
        if "well" in nm or _ld(li)[0] in (64, 122):
            alpha = 55
        elif ".pin" in nm:
            alpha = 90
    elif _LYP:
        # Palette present but layer unknown to it -> annotation/aux, skip.
        _log("[DEBUG] layer %s skipped (not in palette)" % str(info))
        continue
    else:
        color = LAYER_COLORS[order % len(LAYER_COLORS)]
    fill = color + (alpha,)
    line = color + (255,)
    layer_count = 0

    # Draw each layer on its own transparent overlay, then alpha-composite,
    # so stacked layers blend instead of the last fill hiding everything.
    overlay = Image.new("RGBA", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # RecursiveShapeIterator walks the whole hierarchy under top_cell and
    # provides trans() to map each shape into top-cell coordinates. This is
    # what makes sub-cell (standard-cell) geometry visible.
    it = pya.RecursiveShapeIterator(layout, top_cell, li)
    while not it.at_end():
        shape = it.shape()
        trans = it.trans()      # ICplxTrans: shape coords -> top cell coords
        layer_count += 1
        total_shapes += 1

        if shape.is_box():
            b = shape.box.transformed(trans)
            huge = float(b.area()) >= HUGE_FRAC * die_area_dbu
            p1x, p1y = to_px(b.left * dbu, b.bottom * dbu)
            p2x, p2y = to_px(b.right * dbu, b.top * dbu)
            xl, xh = min(p1x, p2x), max(p1x, p2x)
            yl, yh = min(p1y, p2y), max(p1y, p2y)
            if (xh - xl) >= MIN_PX and (yh - yl) >= MIN_PX:
                if huge:
                    draw.rectangle([xl, yl, xh, yh], fill=None,
                                   outline=line, width=2)
                else:
                    draw.rectangle([xl, yl, xh, yh], fill=fill)
                drawn += 1
            else:
                culled += 1
        else:
            # Polygons and paths (paths expose a polygon representation too).
            poly = shape.polygon
            if poly is None:
                # e.g. text shapes — nothing to draw
                it.next()
                continue
            poly = poly.transformed(trans)
            pbb = poly.bbox()
            if (pbb.width() * dbu * scale) < MIN_PX and \
               (pbb.height() * dbu * scale) < MIN_PX:
                culled += 1
                it.next()
                continue
            huge = float(pbb.area()) >= HUGE_FRAC * die_area_dbu
            pts = [to_px(pt.x * dbu, pt.y * dbu) for pt in poly.each_point_hull()]
            if len(pts) >= 3:
                if huge:
                    draw.polygon(pts, fill=None, outline=line)
                else:
                    draw.polygon(pts, fill=fill)
                    # Punch out holes (rare in previews, cheap to handle).
                    for h in range(poly.holes()):
                        hpts = [to_px(pt.x * dbu, pt.y * dbu)
                                for pt in poly.each_point_hole(h)]
                        if len(hpts) >= 3:
                            draw.polygon(hpts, fill=(0, 0, 0, 0))
                drawn += 1
            else:
                culled += 1
        it.next()

    if layer_count:
        img = Image.alpha_composite(img, overlay)

    _log("[DEBUG] layer %s (index %d): %d shapes"
          % (str(info), li, layer_count))

_log("[DEBUG] total shapes: %d  drawn: %d  culled(sub-pixel): %d"
      % (total_shapes, drawn, culled))

if drawn == 0:
    _log("[WARN] no shapes drawn - GDS may contain no geometry "
         "(e.g. DEF converted without LEF). Rendering die outline only.")

# Die boundary outline (always drawn, on top).
draw = ImageDraw.Draw(img)
bx1, by1 = to_px(x1, y1)
bx2, by2 = to_px(x2, y2)
draw.rectangle([min(bx1, bx2), min(by1, by2), max(bx1, bx2), max(by1, by2)],
               fill=None, outline=DIE_COLOR, width=3)

img.convert("RGB").save(output_path, "PNG")
_log("[INFO] wrote " + output_path)