"""Renders the profile SVG slices into assets/ and writes README.md.

Run fetch.py first to refresh data/*.json. This script only reads profile.json
and data/, and it draws. The same data gives byte-identical files, so a second
run on the same day makes no commit.

Every slice is W wide, a multiple of 40 px tall (so the grid lines up across
slices), and draws the same side rails. Only the first slice has the top edge
and the title bar. Only the last slice closes the frame. The stacked <img>s
then read as one console.

Every slice also has a phone variant in assets/phone/: half as wide, so its
text is twice as large on a narrow screen. The README swaps it in with
<picture> below 600 px. The image widths in a row stay the same.

The console frame, the slices and the contribution city are ported from
Giorgi Kobaidze's render.py (github.com/georgekobaidze/georgekobaidze, MIT;
see NOTICE). The colours are Xcode's "Default (Dark)" theme with Swift orange.
"""
import base64
import contextlib
import datetime
import hashlib
import html
import io
import json
import math
import pathlib
import re
import textwrap

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
OUT = ROOT / "assets"
FONT_DIR = HERE / "fonts"
PROFILE = json.loads((HERE / "profile.json").read_text())
USER = PROFILE["login"]

# Xcode "Default (Dark)" colours. The accent is Swift orange.
BG = "#1f1f24"
ACCENT = "#f05138"
PINK = "#ff7ab2"
CYAN = "#6bdfff"
PURPLE = "#dabaff"
GREEN = "#67b7a4"
YELLOW = "#d9c97c"
FG = "#dfdfe0"
DIM = "#7f8c98"
FAINT = "#5f6a75"
FAINTER = "#454b53"
BRIGHT = "#ffffff"
WELL = "#2a2b31"
COLORS = {"accent": ACCENT, "pink": PINK, "cyan": CYAN, "purple": PURPLE, "green": GREEN, "yellow": YELLOW}

W, M = 880, 16            # slice width, transparent side margin (room for the glow)
FL, FR = M, W - M         # frame left / right
X = 52                    # text left edge
XR = FR - 36              # text right edge
HW = W // 2               # half-slice width (440, a multiple of 40 so the grid stays aligned)
ADV = 0.6                 # JetBrains Mono advance, in em
PHONE = False             # True while the phone variants draw
e = html.escape


@contextlib.contextmanager
def phone():
    """Draws the phone variants: the slice is 440 wide, with narrower margins.
    The helpers read this geometry when they run, so most slices need no other change."""
    global W, M, FL, FR, X, XR, HW, PHONE
    saved = W, M, FL, FR, X, XR, HW, PHONE
    W, M, X, HW, PHONE = 440, 12, 32, 220, True
    FL, FR = M, W - M
    XR = FR - 20
    try:
        yield
    finally:
        W, M, FL, FR, X, XR, HW, PHONE = saved


def both(build, *args, **kw):
    """The desktop slice and its phone variant."""
    svg = build(*args, **kw)
    with phone():
        return svg, build(*args, **kw)


def wrap_cmd(s, width):
    """Wraps a command after a space, a slash or a hyphen, so a path breaks where it reads well."""
    lines, cur = [], ""
    for part in re.findall(r"[^ /-]*[ /-]?", s):
        if cur and len(cur) + len(part.rstrip()) > width:
            lines.append(cur.rstrip())
            cur = ""
        cur += part
    return lines + ([cur.rstrip()] if cur.strip() else [])


def wrap_segments(segments, width):
    """Wraps styled segments ([text] or [text, style]) into lines of at most `width` characters."""
    lines, cur, n = [], [], 0
    for seg in segments:
        for word in re.findall(r"\S+|\s+", seg[0]):
            if not word.isspace() and cur and n + len(word) > width:
                cur[-1][0] = cur[-1][0].rstrip()
                lines.append([s for s in cur if s[0]])
                cur, n = [], 0
            if word.isspace() and not cur:
                continue
            if cur and cur[-1][1:] == seg[1:]:
                cur[-1] = [cur[-1][0] + word, *seg[1:]]
            else:
                cur.append([word, *seg[1:]])
            n += len(word)
    return lines + ([cur] if cur else [])


def tw(s, size, spacing=0):
    """The width of a monospace string at a font size, in px."""
    return len(s) * (size * ADV + spacing)


def visible(markup):
    """The characters that a piece of SVG markup shows, so the font subset never misses one."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def faces(text, weights=(400, 700)):
    text += "0123456789"
    out = []
    for w in weights:
        # A fixed timestamp keeps the output byte-identical between runs.
        f = TTFont(FONT_DIR / f"jetbrains-mono-latin-{w}-normal.woff2", recalcTimestamp=False)
        o = subset.Options()
        o.flavor = "woff2"
        o.layout_features = []
        s = subset.Subsetter(o)
        s.populate(text=text)
        s.subset(f)
        b = io.BytesIO()
        f.flavor = "woff2"
        f.save(b)
        out.append(f"@font-face{{font-family:'JBM';font-weight:{w};src:url(data:font/woff2;base64,"
                   f"{base64.b64encode(b.getvalue()).decode()}) format('woff2')}}")
    return "".join(out)


BASE_CSS = f"""text{{font-family:'JBM',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:15px}}
.dim{{fill:{DIM}}}.ac{{fill:{ACCENT}}}.fg{{fill:{FG}}}.gr{{fill:{GREEN}}}.wh{{fill:{BRIGHT}}}.pk{{fill:{PINK}}}
@keyframes fadein{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.ln{{animation:fadein .35s ease-out both}}
.cursor{{animation:blink 1.05s step-end infinite}}
.dot{{animation:pulse 2s ease-in-out infinite}}"""


def defs(w, h, grid_x=0):
    # The glow region is the whole slice. A region relative to the bounding box would be empty
    # for a single rail (zero width), and that slice would lose its glow.
    return f"""<pattern id="grid" x="{grid_x}" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{ACCENT}" stroke-opacity=".07"/></pattern>
<filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}"><feGaussianBlur stdDeviation="6"/></filter>
<filter id="g" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="4"/></filter>"""


def svg_doc(w, h, body, *, title, desc, text, css="", extra_defs="", weights=(400, 700), grid_x=0):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">
<title id="t">{e(title)}</title>
<desc id="d">{e(desc)}</desc>
<style>
{faces(text + visible(body), weights)}
{BASE_CSS}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
{defs(w, h, grid_x)}
{extra_defs}
</defs>
{body}
</svg>
'''


def slice_svg(h, body, *, title, desc, text, top=False, bottom=False, css="", extra_defs="", weights=(400, 700)):
    assert h % 40 == 0, h
    y0 = M if top else 0
    y1 = h - M if bottom else h
    rails = f"M{FL} {y0}V{y1}M{FR} {y0}V{y1}"
    rails += f"M{FL} {y0}H{FR}" if top else ""
    rails += f"M{FL} {y1}H{FR}" if bottom else ""
    gy0 = y0 if top else -40
    gy1 = y1 if bottom else h + 40
    glow = f"M{FL} {gy0}V{gy1}M{FR} {gy0}V{gy1}" + (f"M{FL} {y0}H{FR}" if top else "") + (f"M{FL} {y1}H{FR}" if bottom else "")
    corners = ""
    if top:
        corners += f'<path d="M{FL-7} {y0+18}V{y0-7}H{FL+18}"/><path d="M{FR-18} {y0-7}H{FR+7}V{y0+18}"/>'
    if bottom:
        corners += f'<path d="M{FL-7} {y1-18}V{y1+7}H{FL+18}"/><path d="M{FR-18} {y1+7}H{FR+7}V{y1-18}"/>'
    frame = f'''<path d="{glow}" fill="none" stroke="{ACCENT}" stroke-width="3" opacity=".5" filter="url(#glow)"/>
<rect x="{FL}" y="{y0}" width="{FR-FL}" height="{y1-y0}" fill="{BG}"/>
<rect x="{FL}" y="{y0}" width="{FR-FL}" height="{y1-y0}" fill="url(#grid)"/>
{body}
<path d="{rails}" fill="none" stroke="{ACCENT}" stroke-width="1.2"/>
<g fill="none" stroke="{ACCENT}" stroke-width="2">{corners}</g>'''
    return svg_doc(W, h, frame, title=title, desc=desc, text=text, css=css, extra_defs=extra_defs, weights=weights)


def half_slice(h, side, body, *, title, desc, text):
    """The left or right half of a full-width row. Only its outer side has a rail."""
    assert h % 40 == 0
    rx = FL if side == "L" else HW - M
    bx0, bx1 = (FL, HW) if side == "L" else (0, HW - M)
    frame = f'''<path d="M{rx} -40V{h+40}" fill="none" stroke="{ACCENT}" stroke-width="3" opacity=".5" filter="url(#glow)"/>
<rect x="{bx0}" y="0" width="{bx1-bx0}" height="{h}" fill="{BG}"/>
<rect x="{bx0}" y="0" width="{bx1-bx0}" height="{h}" fill="url(#grid)"/>
{body}
<path d="M{rx} 0V{h}" fill="none" stroke="{ACCENT}" stroke-width="1.2"/>'''
    return svg_doc(HW, h, frame, title=title, desc=desc, text=text, grid_x=(-HW) % 40 if side == "R" else 0)


def cell_slice(k, n, h, body, *, title, desc, text):
    """Cell k of n equal cells in a full-width row. The first and the last cell draw the rails."""
    seg = W // n
    x0 = seg * k
    first, last = k == 0, k == n - 1
    bg0 = FL - x0 if first else 0
    bg1 = FR - x0 if last else seg
    rails = (f"M{FL - x0} 0V{h}" if first else "") + (f"M{FR - x0} 0V{h}" if last else "")
    glow = (f"M{FL - x0} -40V{h+40}" if first else "") + (f"M{FR - x0} -40V{h+40}" if last else "")
    frame = (f'<path d="{glow}" fill="none" stroke="{ACCENT}" stroke-width="3" opacity=".5" filter="url(#glow)"/>' if glow else "") + f'''
<rect x="{bg0}" y="0" width="{bg1-bg0}" height="{h}" fill="{BG}"/>
<rect x="{bg0}" y="0" width="{bg1-bg0}" height="{h}" fill="url(#grid)"/>
{body}
''' + (f'<path d="{rails}" fill="none" stroke="{ACCENT}" stroke-width="1.2"/>' if rails else "")
    return svg_doc(seg, h, frame, title=title, desc=desc, text=text, grid_x=(-x0) % 40)


def cell_box(k, n, bw):
    """The left edge of box k (bw wide) inside its cell, so that n boxes span X … XR evenly."""
    if PHONE:   # Too narrow to spread: each box sits in the middle of its cell, inside the frame.
        seg = W // n
        lo, hi = max(seg * k, FL + 4), min(seg * (k + 1), FR - 4)
        return (lo + hi - bw) / 2 - seg * k
    gap = ((XR - X) - n * bw) / (n - 1)
    return X + k * (bw + gap) - (W // n) * k


def heading(y, name, counter):
    return f'''<text x="{X}" y="{y}" font-weight="700" fill="{ACCENT}" filter="url(#g)" opacity=".8" style="font-size:20px">~/</text>
<text x="{X}" y="{y}" font-weight="700" style="font-size:20px"><tspan class="ac">~/</tspan><tspan class="wh">{e(name)}</tspan></text>
<text x="{XR}" y="{y}" text-anchor="end" letter-spacing="2" fill="{FAINT}" style="font-size:12px">{e(counter)}</text>
<line x1="{X}" y1="{y+14}" x2="{XR}" y2="{y+14}" stroke="{ACCENT}" stroke-opacity=".4"/>
<line x1="{X}" y1="{y+14}" x2="{X+120}" y2="{y+14}" stroke="{ACCENT}" stroke-width="2"/>
<line x1="{X}" y1="{y+14}" x2="{X+120}" y2="{y+14}" stroke="{ACCENT}" stroke-width="3" filter="url(#g)"/>'''


def prompt(y, cmd, comment="", delay=.15):
    tail = f' <tspan fill="{FAINTER}"># {e(comment)}</tspan>' if comment else ""
    # A long command on a phone gets a smaller font, not a broken line.
    size = min(15, (XR - X) / (len(f"$ {cmd} # {comment}" if comment else f"$ {cmd}") * ADV))
    style = f' style="font-size:{size:.1f}px"' if size < 15 else ""
    return f'<g class="ln" style="animation-delay:{delay:.2f}s"><text x="{X}" y="{y}" class="dim"{style}><tspan class="gr">$</tspan> {e(cmd)}{tail}</text></g>'


def section_head(name, counter, cmd, comment="", title=None, desc=None):
    body = heading(44, name, counter) + "\n" + prompt(96, cmd, comment)
    return slice_svg(120, body, title=title or name, desc=desc or name,
                     text=f"~/{name}{counter}$ {cmd} # {comment}")


def stagger(rows, y0, lh, delay0=0.15, step=0.12):
    """rows: markup strings with {y}. Returns (markup, next_y)."""
    out, y = [], y0
    for i, r in enumerate(rows, 1):
        out.append(f'<g class="ln" style="animation-delay:{delay0 + i*step:.2f}s">' + r.replace("{y}", str(y)) + "</g>")
        y += lh
    return "\n".join(out), y


def up40(v):
    return int(math.ceil(v / 40) * 40)


def fmt(n):
    return "—" if n is None else f"{n:,}"


def arrow(x, y, color=ACCENT):
    return f'<path d="M{x} {y}l8-8M{x+2} {y-8}h6v6" fill="none" stroke="{color}" stroke-width="1.5"/>'


STAR = "M10 0l2.9 6.6 7.1.6-5.4 4.7 1.6 7L10 15.2 3.8 18.9l1.6-7L0 7.2l7.1-.6z"


def star_count(x_right, y, n, size=12):
    """'★ n' right-aligned at x_right on baseline y."""
    sx = x_right - tw(str(n), size) - 14
    return (f'<path transform="translate({sx:.1f} {y-10}) scale(.55)" d="{STAR}" fill="{YELLOW}"/>'
            f'<text x="{x_right}" y="{y}" text-anchor="end" class="dim" style="font-size:{size}px">{n}</text>')


# ─────────────────────────────── header ───────────────────────────────
def build_header():
    bar_left, bar_right = PROFILE["bar"]
    name = PROFILE["name"]
    text = bar_left + bar_right + name + "$ whoami>>" + "".join(s[0] for line in PROFILE["about"] for s in line)
    h = 360
    css = """@keyframes type{from{width:0}}
@keyframes flicker{0%{opacity:0}10%{opacity:1}14%{opacity:.2}22%{opacity:1}30%{opacity:.4}40%,100%{opacity:1}}
@keyframes gm{0%,92%,100%{transform:translate(0,0)}93%{transform:translate(5px,-1px)}95%{transform:translate(-3px,1px)}97%{transform:translate(2px,0)}}
@keyframes gc{0%,92%,100%{transform:translate(0,0)}93%{transform:translate(-5px,1px)}95%{transform:translate(4px,-1px)}97%{transform:translate(-2px,0)}}
.typing{animation:type .7s steps(8) .3s both}
.name{animation:flicker .9s linear 1.1s both}
.gm{animation:gm 6s linear 2s infinite}.gc{animation:gc 6s linear 2s infinite}"""
    extra = f"""<pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" fill-opacity=".2"/></pattern>
<filter id="tglow" x="-5%" y="-40%" width="110%" height="180%"><feGaussianBlur stdDeviation="9"/></filter>
<filter id="sglow" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="3"/></filter>
<clipPath id="typeclip"><rect class="typing" x="{X}" y="80" width="140" height="30"/></clipPath>"""
    bs, bls = (10, .5) if PHONE else (12, 1)        # title bar font size, letter spacing
    ns, nls, ny = (34, 1, 152) if PHONE else (56, 2, 172)
    size = 14 if PHONE else 15
    dotx = FR - 20 - tw(bar_right, bs, bls) - 14
    cls = {"accent": "ac", "pink": "pk"}

    def line(segments, lead=True):
        spans = "".join(f'<tspan class="{cls[s[1]]}" font-weight="700">{e(s[0])}</tspan>' if len(s) > 1 else e(s[0])
                        for s in segments)
        x = X if lead else X + tw(">> ", size)
        head = '<tspan class="ac">&gt;&gt;</tspan> ' if lead else ""
        style = f' style="font-size:{size}px"' if PHONE else ""
        return f'<text class="fg" x="{x:g}" y="{{y}}"{style}>{head}{spans}</text>'

    if PHONE:
        width = int((XR - X) / (size * ADV)) - 3
        rows = [line(l, i == 0) for segs in PROFILE["about"] for i, l in enumerate(wrap_segments(segs, width))]
        about, end = stagger(rows, 196, 22, delay0=1.75, step=0.2)
        h = up40(end + 38)
    else:
        about, end = stagger([line(s) for s in PROFILE["about"]], 218, 24, delay0=1.75, step=0.25)
    body = f'''<rect x="{FL}" y="{M}" width="{FR-FL}" height="34" fill="{ACCENT}" fill-opacity=".08"/>
<line x1="{FL}" y1="{M+34}" x2="{FR}" y2="{M+34}" stroke="{ACCENT}" stroke-opacity=".5"/>
<text x="{FL+16}" y="{M+22}" letter-spacing="{bls}" class="ac" style="font-size:{bs}px">{e(bar_left)}</text>
<text x="{FR-20}" y="{M+22}" letter-spacing="{bls}" class="dim" text-anchor="end" style="font-size:{bs}px">{e(bar_right)}</text>
<circle class="dot" cx="{dotx:.1f}" cy="{M+18}" r="4" fill="{GREEN}"/>
<circle class="dot" cx="{dotx:.1f}" cy="{M+18}" r="4" fill="{GREEN}" filter="url(#sglow)"/>
<g clip-path="url(#typeclip)"><text x="{X}" y="102" class="dim"><tspan class="gr">$</tspan> whoami</text></g>
<g class="name" font-weight="800" letter-spacing="{nls}" style="font-size:{ns}px">
<text x="{X}" y="{ny}" fill="{ACCENT}" opacity=".55" filter="url(#tglow)" style="font-size:{ns}px">{e(name)}</text>
<g class="gm"><text x="{X+3}" y="{ny}" fill="{PINK}" opacity=".75" style="font-size:{ns}px">{e(name)}</text></g>
<g class="gc"><text x="{X-3}" y="{ny}" fill="{ACCENT}" opacity=".85" style="font-size:{ns}px">{e(name)}</text></g>
<text x="{X}" y="{ny}" fill="{BRIGHT}" style="font-size:{ns}px">{e(name)}</text>
</g>
{about}
<g class="ln" style="animation-delay:2.8s">
<text x="{X}" y="{end+14}" class="gr">$</text>
<rect class="cursor" x="{X+18}" y="{end+1}" width="10" height="17" fill="{ACCENT}"/>
<rect class="cursor" x="{X+18}" y="{end+1}" width="10" height="17" fill="{ACCENT}" filter="url(#sglow)"/>
</g>
<rect x="{FL}" y="{M+35}" width="{FR-FL}" height="{h-M-35}" fill="url(#scan)"/>'''
    return slice_svg(h, body, title=PROFILE["name"].title(), desc=PROFILE["summary"], text=text, top=True,
                     css=css, extra_defs=extra, weights=(400, 700, 800))


def build_footer():
    text = "$ exit Program ended with exit code: 0 // EOF"
    body = f'''<text x="{X}" y="30" class="dim"><tspan class="gr">$</tspan> exit</text>
<text x="{X}" y="52" class="dim">Program ended with exit code: <tspan class="ac">0</tspan> <tspan fill="{FAINTER}">// EOF</tspan></text>'''
    return slice_svg(80, body, title="End of profile", desc="Program ended with exit code: 0", text=text, bottom=True)


# ──────────────────────────────── links ───────────────────────────────
ICONS = json.loads((HERE / "icons.json").read_text())


def icon_markup(key, x, y, size=18):
    if key == "linkedin":   # A plain "in" glyph: LinkedIn is not in Simple Icons.
        return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="{ACCENT}"/>'
                f'<text x="{x + size/2}" y="{y + size - 4.5}" text-anchor="middle" font-weight="700" fill="{BG}" style="font-size:12px">in</text>')
    ic = ICONS[key]
    if ic.get("stroke"):
        return (f'<path transform="translate({x} {y}) scale({size/24})" d="{ic["d"]}" fill="none" stroke="{ACCENT}" '
                f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
    return f'<path transform="translate({x} {y}) scale({size/24})" d="{ic["d"]}" fill="{ACCENT}"/>'


def build_link_button(k, link):
    n = len(PROFILE["links"])
    bw = W // n - (22 if PHONE else 56)       # as wide as the cell allows, with a gap
    lx = cell_box(k, n, bw)
    by, bh, cut = 12, 56, 10 if PHONE else 12
    box = f"M{lx:.1f} {by}H{lx+bw-cut:.1f}L{lx+bw:.1f} {by+cut}V{by+bh}H{lx:.1f}Z"
    if PHONE:   # No room for the handle: the icon above the label.
        ix, iy = lx + bw / 2 - 9, by + 9
        inner = f'''<g filter="url(#g)" opacity=".5">{icon_markup(link["icon"], ix, iy)}</g>
{icon_markup(link["icon"], ix, iy)}
<text x="{lx+bw/2:.1f}" y="{by+45}" text-anchor="middle" font-weight="700" class="ac" style="font-size:12px">{e(link["label"])}</text>'''
    else:
        inner = f'''<g filter="url(#g)" opacity=".5">{icon_markup(link["icon"], lx+12, by+11)}</g>
{icon_markup(link["icon"], lx+12, by+11)}
<text x="{lx+38:.1f}" y="{by+25}" font-weight="700" class="ac" style="font-size:13px">{e(link["label"])}</text>
<text x="{lx+12:.1f}" y="{by+46}" class="dim" style="font-size:10px">{e(link["handle"])}</text>'''
    body = f'''<g class="ln" style="animation-delay:{.25 + k*.08:.2f}s">
<path d="{box}" fill="{ACCENT}" fill-opacity=".05"/>
<path d="{box}" fill="none" stroke="{ACCENT}" stroke-opacity=".55"/>
<path d="M{lx+bw-cut:.1f} {by}L{lx+bw:.1f} {by+cut}" stroke="{ACCENT}" stroke-width="2"/>
{inner}
</g>'''
    return cell_slice(k, n, 80, body, title=link["label"], desc=f'{link["label"]}: {link["url"]}',
                      text=link["label"] + link["handle"] + "in")


# ─────────────────────────────── stats ────────────────────────────────
def tile(x, y, w, h, label, value, sub, delay):
    return f'''<g class="ln" style="animation-delay:{delay:.2f}s">
<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{ACCENT}" fill-opacity=".035" stroke="{ACCENT}" stroke-opacity=".35"/>
<path d="M{x} {y+12}V{y}H{x+12}" fill="none" stroke="{ACCENT}" stroke-width="2"/>
<text x="{x+16}" y="{y+22}" letter-spacing="1.5" class="dim" style="font-size:10.5px">{e(label)}</text>
<text x="{x+16}" y="{y+50}" font-weight="700" fill="{ACCENT}" filter="url(#g)" opacity=".55" style="font-size:30px">{e(value)}</text>
<text x="{x+16}" y="{y+50}" font-weight="700" fill="{ACCENT}" style="font-size:30px">{e(value)}</text>
<text x="{x+16}" y="{y+h-12}" fill="{FAINT}" style="font-size:12px">{e(sub)}</text>
</g>'''


def build_stats(d, counter):
    updated = datetime.date.fromisoformat(d["updated"])
    since = datetime.date.fromisoformat(d["created_at"][:10])
    yrs = (updated - since).days // 365
    parts = [heading(44, "stats", counter), prompt(96, f"gh stats --user {USER}")]
    tiles = [("TOTAL STARS", fmt(d["stars"]), f"across {d['repo_count']} repos"),
             (f"CONTRIBUTIONS {d['year']}", fmt(d["contributions_year"]), f"{fmt(d['contributions_all'])} all time"),
             ("PULL REQUESTS", fmt(d["prs"]), f"{fmt(d['prs_merged'])} merged"),
             ("CURRENT STREAK", f"{d['streak_current']}d", f"longest: {d['streak_longest']} days")]
    # Four tiles in a row on a desktop, two by two on a phone. There the two boxes below stack too.
    cols, gap, ty, th = 2 if PHONE else 4, 16, 118, 92
    tw_ = (XR - X - (cols - 1) * gap) // cols
    for i, (lab, val, sub) in enumerate(tiles):
        parts.append(tile(X + i % cols * (tw_ + gap), ty + i // cols * (th + gap), tw_, th, lab, val, sub, .25 + i * .08))
    rows_ = math.ceil(len(tiles) / cols)
    ry, rh, lw = ty + rows_ * (th + gap), 150, XR - X if PHONE else 300
    hl = d.get("highlight")
    kv = [("followers", fmt(d["followers"])),
          ("member since", f"{since:%b %Y} ({yrs}y)"),
          ("location", PROFILE["location"])]
    if hl:
        kv.append((PROFILE["highlight"]["label"], f"#{hl['rank']} · {hl['commits']} commits"))
    rows = "\n".join(
        f'<text x="{X+16}" y="{ry+38+i*28}" xml:space="preserve"><tspan class="ac">{e(k)}</tspan>'
        f'<tspan class="dim">{"." * (14 - len(k))}</tspan> <tspan class="fg">{e(v)}</tspan></text>'
        for i, (k, v) in enumerate(kv))
    parts.append(f'''<g class="ln" style="animation-delay:.6s">
<rect x="{X}" y="{ry}" width="{lw}" height="{rh}" fill="{ACCENT}" fill-opacity=".035" stroke="{ACCENT}" stroke-opacity=".35"/>
<path d="M{X} {ry+12}V{ry}H{X+12}" fill="none" stroke="{ACCENT}" stroke-width="2"/>
{rows}
</g>''')
    lx, ly = (X, ry + rh + gap) if PHONE else (X + lw + gap, ry)
    lwid = XR - lx
    langs = sorted(d["languages"].items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in langs)
    top = langs[:5]
    other = total - sum(v for _, v in top)
    items = [(k, v / total) for k, v in top] + ([("Other", other / total)] if other else [])
    cols = [ACCENT, CYAN, PINK, YELLOW, PURPLE, FAINT]
    bx, by, bw = lx + 16, ly + 42, lwid - 32
    segs, cx = [], bx
    for (k, p), c in zip(items, cols):
        w = bw * p
        segs.append(f'<rect x="{cx:.1f}" y="{by}" width="{max(w-2, 1):.1f}" height="8" fill="{c}"/>')
        cx += w
    legend = []
    for i, ((k, p), c) in enumerate(zip(items, cols)):
        lxx = bx + (i % 2) * (bw / 2)
        lyy = by + 36 + (i // 2) * 26
        legend.append(f'<rect x="{lxx:.1f}" y="{lyy-9}" width="9" height="9" fill="{c}"/>'
                      f'<text x="{lxx+18:.1f}" y="{lyy}" class="fg" style="font-size:13px">{e(k)}</text>'
                      f'<text x="{lxx + bw/2 - 24:.1f}" y="{lyy}" text-anchor="end" class="dim" style="font-size:13px">{p*100:.1f}%</text>')
    parts.append(f'''<g class="ln" style="animation-delay:.7s">
<rect x="{lx}" y="{ly}" width="{lwid}" height="{rh}" fill="{ACCENT}" fill-opacity=".035" stroke="{ACCENT}" stroke-opacity=".35"/>
<path d="M{lx} {ly+12}V{ly}H{lx+12}" fill="none" stroke="{ACCENT}" stroke-width="2"/>
<text x="{lx+16}" y="{ly+24}" letter-spacing="1.5" class="dim" style="font-size:10.5px">TOP LANGUAGES</text>
<rect x="{bx}" y="{by}" width="{bw}" height="8" fill="{WELL}"/>
{"".join(segs)}
{"".join(legend)}
</g>''')
    fy = ly + rh + 30
    parts.append(f'<text x="{XR}" y="{fy}" text-anchor="end" fill="{FAINTER}" style="font-size:11px">// last sync {d["updated"]}</text>')
    body = "\n".join(parts)
    desc = (f"GitHub stats: {d['stars']} stars across {d['repo_count']} public repos; "
            f"{d['contributions_year']:,} contributions in {d['year']}, {d['contributions_all']:,} all time; "
            f"{d['prs']:,} pull requests ({d['prs_merged']:,} merged); "
            f"current streak {d['streak_current']} days, longest {d['streak_longest']}; "
            f"{d['followers']} followers; member since {since:%B %Y}."
            + (f" {PROFILE['highlight']['label']}: contributor #{hl['rank']} with {hl['commits']} commits." if hl else "")
            + " Top languages: " + ", ".join(f"{k} {p*100:.1f}%" for k, p in items) + ".")
    return slice_svg(up40(fy + 16), body, title="Stats", desc=desc, text=visible(body) + "—%.()d#·")


# ─────────────────────────── contribution city ────────────────────────
CITY_TW, CITY_TH = 25, 12.5                  # iso tile width / height
CITY_OX, CITY_OY = 152.5, 262                # grid origin inside the 880-wide slice
CITY_HMAX = 118                              # the tallest building, px
SCENE_L, SCENE_R = 16, 864                   # the desktop frame: the phone scales the whole scene down from it
ROOFS = ["#5c2a20", "#a33a24", "#f05138", "#ffa07a"]   # ember → Swift orange → glow
FACE_L, FACE_R = "#303139", "#27282f"
WIN_ON, WIN_ON_SIDE, WIN_OFF = "#ffd9a8", "#f5a873", "#2e2f36"
EMPTY, EMPTY_STROKE = "#2a2b31", BG


def _p(x, y):
    return f"{x:.1f},{y:.1f}"


def _rng(seed):
    """A tiny deterministic PRNG, so the same data always draws the same windows."""
    state = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        yield (state >> 11) / 2**53


def _levels(counts):
    """Quartile thresholds over the non-zero days, as on GitHub."""
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return [1, 1, 1]
    q = lambda f: nz[min(len(nz) - 1, int(len(nz) * f))]  # noqa: E731
    return [q(.25), q(.5), q(.75)]


def mountains():
    """The Trans-Ili Alatau behind the city: Almaty sits at its foot."""
    ridge = [(352, 372), (400, 322), (440, 296), (478, 256), (512, 266), (560, 210), (590, 226), (628, 188),
             (664, 212), (700, 194), (742, 228), (780, 206), (830, 238), (SCENE_R, 226)]
    base = [(SCENE_R, 600)]
    body = "M" + "L".join(_p(*q) for q in ridge + base) + "Z"
    snow = []
    for (x0, y0), (x1, y1), (x2, y2) in zip(ridge, ridge[1:], ridge[2:]):
        if y1 < y0 and y1 < y2 and y1 < 225:   # a peak high enough for snow
            a = ((x1 - x0) * .35, (y0 - y1) * .35)
            b = ((x2 - x1) * .35, (y2 - y1) * .35)
            snow.append(f"M{_p(x1 - a[0], y1 + a[1])}L{_p(x1, y1)}L{_p(x1 + b[0], y1 + b[1])}"
                        f"L{_p(x1 + b[0] * .4, y1 + b[1] * .75)}L{_p(x1, y1 + 6)}L{_p(x1 - a[0] * .4, y1 + a[1] * .8)}Z")
    return (f'<path d="{body}" fill="url(#ridge)"/>'
            f'<path d="{"".join(snow)}" fill="{FG}" opacity=".55"/>')


def build_city(calendar, updated, counter):
    days = [(datetime.date.fromisoformat(d), n) for d, n in calendar]
    counts = [n for _, n in days]
    total, peak = sum(counts), max(counts) if counts else 0
    lv = _levels(counts)
    rnd = _rng(f"{updated}-{total}")
    start = days[0][0]

    cells = sorted((((d - start).days // 7, (d.weekday() + 1) % 7, n) for d, n in days),
                   key=lambda c: (c[0] + c[1], c[0]))          # back to front; Sunday = 0
    shapes, flick = [], 0
    for w, dow, n in cells:
        cx = CITY_OX + (w - dow) * CITY_TW / 2
        cy = CITY_OY + (w + dow) * CITY_TH / 2
        L, R = (cx - CITY_TW / 2, cy), (cx + CITY_TW / 2, cy)
        T, B = (cx, cy - CITY_TH / 2), (cx, cy + CITY_TH / 2)
        if n == 0:
            shapes.append(f'<path d="M{_p(*T)}L{_p(*R)}L{_p(*B)}L{_p(*L)}Z" fill="{EMPTY}" stroke="{EMPTY_STROKE}" stroke-width=".6"/>')
            continue
        h = 8 + (CITY_HMAX - 8) * math.sqrt(n / peak)
        level = sum(n > t for t in lv)
        Tu, Ru, Bu, Lu = [(x, y - h) for x, y in (T, R, B, L)]
        shapes.append(f'<path d="M{_p(*L)}L{_p(*B)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="{FACE_L}"/>'
                      f'<path d="M{_p(*B)}L{_p(*R)}L{_p(*Ru)}L{_p(*Bu)}Z" fill="{FACE_R}"/>'
                      f'<path d="M{_p(*Tu)}L{_p(*Ru)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="{ROOFS[level]}"/>')
        on, side, off, fl = [], [], [], []
        for face, (a, b) in (("l", (L, B)), ("r", (B, R))):
            for r in range(int((h - 6) // 7)):
                v0 = 5 + r * 7
                for u0 in (.18, .58):
                    lit = next(rnd) < .55
                    if not lit and next(rnd) < .5:
                        continue
                    pts = [(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - v)
                           for u, v in ((u0, v0), (u0 + .26, v0), (u0 + .26, v0 + 3.2), (u0, v0 + 3.2))]
                    seg = "M" + "L".join(_p(*q) for q in pts) + "Z"
                    if not lit:
                        off.append(seg)
                    elif next(rnd) < .03:
                        fl.append((seg, face))
                    else:
                        (on if face == "l" else side).append(seg)
        if off:
            shapes.append(f'<path d="{"".join(off)}" fill="{WIN_OFF}"/>')
        if on:
            shapes.append(f'<path d="{"".join(on)}" fill="{WIN_ON}"/>')
        if side:
            shapes.append(f'<path d="{"".join(side)}" fill="{WIN_ON_SIDE}"/>')
        for seg, face in fl:
            flick += 1
            shapes.append(f'<path class="f{flick % 3}" d="{seg}" fill="{WIN_ON if face == "l" else WIN_ON_SIDE}"/>')

    # The night sky in the empty top-right corner: stars, the moon, a plane.
    stars = []
    for i in range(46):
        x, y = 440 + next(rnd) * 380, 112 + next(rnd) * 90
        if x > 700 and y < 200:           # keep the moon clear
            continue
        c = f' class="s{i % 3}"' if i % 3 == 0 else ""
        stars.append(f'<circle{c} cx="{x:.1f}" cy="{y:.1f}" r="{(.6, .8, 1.1)[i % 3]}" fill="{FG}" opacity="{.35 + next(rnd) * .5:.2f}"/>')
    busiest_d, busiest_n = max(days, key=lambda t: t[1]) if days else (None, 0)
    active = sum(1 for n in counts if n)
    sky = f'''<g>{"".join(stars)}</g>
<circle cx="{SCENE_R-80}" cy="150" r="40" fill="url(#moonglow)"/>
<circle cx="{SCENE_R-80}" cy="150" r="14" fill="#eae6df"/>
<circle cx="{SCENE_R-74}" cy="145" r="12.5" fill="{BG}"/>
<g class="plane"><g transform="translate(0 124)"><rect x="0" y="0" width="14" height="2" rx="1" fill="{FAINTER}"/><circle class="bl" cx="0" cy="1" r="1.6" fill="#ff8170"/><circle class="bl" cx="14" cy="1" r="1.6" fill="#f0f6fc" style="animation-delay:.7s"/></g></g>
{mountains()}'''
    if PHONE:
        # The whole scene shrinks into the phone frame. The numbers keep their size,
        # in shorter lines, in the empty corner under the city.
        s = (FR - FL) / (SCENE_R - SCENE_L)
        info = [f'<tspan class="ac" font-weight="700">{total:,}</tspan> contributions', "last 365 days",
                f'busiest <tspan class="fg">{busiest_d:%b} {busiest_d.day}</tspan> · {busiest_n}' if busiest_n else "",
                f'{active} active days']
        info_svg = "".join(f'<text x="{X}" y="{300 + i*18}" class="dim" style="font-size:12px">{t}</text>'
                           for i, t in enumerate(t for t in info if t))
        scene = (f'<g transform="translate({FL - SCENE_L * s:.2f} {112 - 104 * s:.2f}) scale({s:.4f})">\n'
                 f'{sky}\n{"".join(shapes)}\n</g>\n{info_svg}')
        ly, h = 400, 440
    else:
        info = [f'<tspan class="ac" font-weight="700">{total:,}</tspan> contributions · last 365 days',
                f'busiest day <tspan class="fg">{busiest_d:%b} {busiest_d.day}</tspan> · {busiest_n}' if busiest_n else "",
                f'{active} active days']
        info_svg = "".join(f'<text x="{XR}" y="{300 + i*20}" text-anchor="end" class="dim" style="font-size:12px">{t}</text>'
                           for i, t in enumerate(info) if t)
        scene = f'{sky}\n{info_svg}\n{"".join(shapes)}'
        ly, h = 652, 680
    legend = "".join(f'<rect x="{X + 52 + i*16}" y="{ly - 10}" width="11" height="11" fill="{c}"/>'
                     for i, c in enumerate([EMPTY] + ROOFS))
    body = heading(44, "contribution-city", counter) + f'''
{prompt(96, "render-city --last 365d", "one building per day")}
{scene}
<text x="{X}" y="{ly}" class="dim" style="font-size:11px">quiet</text>{legend}<text x="{X + 52 + 5*16 + 6}" y="{ly}" class="dim" style="font-size:11px">skyscraper</text>'''
    css = f"""@keyframes tw{{0%,100%{{opacity:.9}}50%{{opacity:.15}}}}
@keyframes fl{{0%,40%,100%{{opacity:1}}45%,60%{{opacity:.1}}}}
@keyframes blink{{0%,90%,100%{{opacity:0}}93%{{opacity:1}}}}
@keyframes fly{{from{{transform:translate({SCENE_L - 40}px,0)}}to{{transform:translate({SCENE_R + 40}px,-30px)}}}}
.s0{{animation:tw 3s infinite}}
.f0{{animation:fl 5s infinite}}.f1{{animation:fl 7s infinite 2s}}.f2{{animation:fl 9s infinite 4s}}
.plane{{animation:fly 26s linear infinite}}.bl{{animation:blink 1.4s infinite}}"""
    extra = (f'<radialGradient id="moonglow"><stop offset="0" stop-color="#f0f6fc" stop-opacity=".22"/>'
             f'<stop offset="1" stop-color="#f0f6fc" stop-opacity="0"/></radialGradient>'
             f'<linearGradient id="ridge" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a3b44"/>'
             f'<stop offset=".45" stop-color="{BG}"/></linearGradient>')
    desc = (f"Contribution city: an isometric night skyline at the foot of the mountains, with one building "
            f"per day of the last year, taller and brighter for busier days. {total:,} contributions"
            + (f", busiest day {busiest_d:%B} {busiest_d.day} with {busiest_n}" if busiest_n else "") + ".")
    return slice_svg(h, body, title="Contribution city", desc=desc,
                     text="~/contribution-city" + counter + "$ render-city --last 365d # one building per dayquietskyscraper" + visible(info_svg),
                     css=css, extra_defs=extra)


# ────────────────────────────── projects ──────────────────────────────
CARD_H = 240


def install_line(x, y, w, p):
    """The command that installs a project, in a dark well, as on jdx.dev."""
    get, is_cmd = p["get"], p.get("cmd", True)
    shown = ("$ " if is_cmd else "› ") + get
    size = min(12.0, (w - 20) / (len(shown) * ADV))
    lead = '<tspan class="gr">$</tspan>' if is_cmd else '<tspan class="ac">›</tspan>'
    return (f'<rect x="{x}" y="{y}" width="{w}" height="26" fill="{WELL}"/>'
            f'<text x="{x+10}" y="{y+17.5}" class="fg" style="font-size:{size:.2f}px">{lead} {e(get)}</text>')


PHONE_CW = 182                    # a phone card; 12 px gutter between two cards
PHONE_PAD = 12


def phone_card_lines(p):
    """A phone card wraps what a desktop card keeps on one line: name, description, install command."""
    iw = PHONE_CW - 2 * PHONE_PAD
    nw = iw - 18                                           # room for the ↗ after the name
    name = textwrap.wrap(p["name"], int(nw / (14 * ADV)), break_long_words=False)
    nsize = min(14, nw / (max(map(len, name)) * ADV))      # one long word shrinks instead
    desc = textwrap.wrap(p["desc"], int(iw / (12 * ADV)))
    get = wrap_cmd(("$ " if p.get("cmd", True) else "› ") + p["get"], int((iw - 16) / (10 * ADV)))
    return name, nsize, desc, get


def phone_card_height():
    """The two cards of a row must be as tall as each other, so every phone card gets the tallest height."""
    def need(p):
        name, _, desc, get = phone_card_lines(p)
        last_desc = 62 + 18 * len(name) + 15 * (len(desc) - 1)   # the baseline, as build_card_phone draws it
        return last_desc + 8 + (8 + 13 * len(get)) + 38
    return up40(max(need(p) for p in PROFILE["projects"]))


def build_card_phone(p, side, delay, stars):
    h = phone_card_height()
    cw, y0, ch, pad, cut = PHONE_CW, 8, h - 16, PHONE_PAD, 12
    x0 = X if side == "L" else XR - HW - cw
    tx = x0 + pad
    color = COLORS[p["color"]]
    box = f"M{x0} {y0}H{x0+cw-cut}L{x0+cw} {y0+cut}V{y0+ch}H{x0+cut}L{x0} {y0+ch-cut}Z"
    name, nsize, desc, get = phone_card_lines(p)
    names = "".join(f'<text x="{tx}" y="{y0 + 26 + i*18}" font-weight="700" class="ac" style="font-size:{nsize:g}px">{e(s)}</text>'
                    for i, s in enumerate(name))
    last_y = y0 + 26 + (len(name) - 1) * 18
    last_w = tw(name[-1], nsize)
    link = arrow(tx + last_w + 8, last_y - 3)
    ty = last_y + 10
    tag_w = tw(p["tag"], 10, 1) + 12
    descs = "".join(f'<text x="{tx}" y="{ty + 36 + i*15}" class="fg" style="font-size:12px">{e(s)}</text>'
                    for i, s in enumerate(desc))
    wh = 8 + 13 * len(get)                      # the install well sits on the bottom, level across a row
    wy = y0 + ch - 30 - wh
    lead = {"$": '<tspan class="gr">$</tspan>', "›": '<tspan class="ac">›</tspan>'}
    gets = "".join(f'<text x="{tx+8}" y="{wy + 14 + i*13}" class="fg" style="font-size:10px">'
                   + (lead[s[0]] + e(s[1:]) if i == 0 else e(s)) + "</text>" for i, s in enumerate(get))
    body = f'''<g class="ln" style="animation-delay:{delay:.2f}s">
<path d="{box}" fill="{ACCENT}" fill-opacity=".035"/>
<path d="{box}" fill="none" stroke="{ACCENT}" stroke-opacity=".4"/>
<path d="M{x0+cw-cut} {y0}L{x0+cw} {y0+cut}" stroke="{ACCENT}" stroke-width="2"/>
{names}
{link}
<rect x="{tx}" y="{ty}" width="{tag_w:.1f}" height="16" fill="none" stroke="{color}" stroke-opacity=".8"/>
<text x="{tx+6}" y="{ty+12}" letter-spacing="1" fill="{color}" style="font-size:10px">{e(p["tag"])}</text>
{descs}
<rect x="{tx}" y="{wy}" width="{cw - 2*pad}" height="{wh}" fill="{WELL}"/>
{gets}
{star_count(x0 + cw - pad, y0 + ch - 12, stars, 11) if stars is not None else ""}
</g>'''
    return half_slice(h, side, body, title=p["name"], desc=card_alt(p, stars), text=visible(body))


def build_card(p, side, delay, stars):
    if PHONE:
        return build_card_phone(p, side, delay, stars)
    x0 = 52 if side == "L" else 10          # card box, 378 wide; 20 px gutter between two cards
    cw, y0, ch = 378, 12, 216
    pad, cut = 18, 16
    tx = x0 + pad
    color = COLORS[p["color"]]
    box = f"M{x0} {y0}H{x0+cw-cut}L{x0+cw} {y0+cut}V{y0+ch}H{x0+cut}L{x0} {y0+ch-cut}Z"
    lines = textwrap.wrap(p["desc"], 43)
    assert len(lines) <= 3, (p["name"], lines)
    tag_w = tw(p["tag"], 11, 1) + 16
    title_w = tw(p["name"], 17)
    desc = "\n".join(f'<text x="{tx}" y="{y0 + 86 + i*20}" class="fg" style="font-size:13px">{e(s)}</text>'
                     for i, s in enumerate(lines))
    sx = x0 + cw - pad
    body = f'''<g class="ln" style="animation-delay:{delay:.2f}s">
<path d="{box}" fill="{ACCENT}" fill-opacity=".035"/>
<path d="{box}" fill="none" stroke="{ACCENT}" stroke-opacity=".4"/>
<path d="M{x0+cw-cut} {y0}L{x0+cw} {y0+cut}" stroke="{ACCENT}" stroke-width="2"/>
<text x="{tx}" y="{y0+34}" font-weight="700" fill="{ACCENT}" filter="url(#g)" opacity=".6" style="font-size:17px">{e(p["name"])}</text>
<text x="{tx}" y="{y0+34}" font-weight="700" class="ac" style="font-size:17px">{e(p["name"])}</text>
{arrow(tx + title_w + 11, y0 + 31)}
<rect x="{tx}" y="{y0+46}" width="{tag_w:.1f}" height="18" fill="none" stroke="{color}" stroke-opacity=".8"/>
<text x="{tx+8}" y="{y0+59}" letter-spacing="1" fill="{color}" style="font-size:11px">{e(p["tag"])}</text>
{desc}
{install_line(tx, y0 + 146, cw - 2 * pad, p)}
<text x="{tx}" y="{y0+196}" class="dim" style="font-size:12px">{e(p["stack"])}</text>
{star_count(sx, y0 + 196, stars) if stars is not None else ""}
</g>'''
    text = p["name"] + p["tag"] + p["desc"] + p["stack"] + p["get"] + str(stars) + "$›"
    alt = card_alt(p, stars)
    return half_slice(CARD_H, side, body, title=p["name"], desc=alt, text=text)


def card_alt(p, stars):
    how = f'Install: {p["get"]}' if p.get("cmd", True) else f'Get it: {p["get"]}'
    return f'{p["name"]} ({p["tag"].lower()}): {p["desc"]} {how}. Built with {p["stack"].replace(" · ", ", ")}.' + \
        (f" {stars} stars." if stars is not None else "")


def build_also(k, n, item, stars, delay):
    bw = 88 if PHONE else 166
    lx = cell_box(k, n, bw)
    by, bh, cut = 10, 96, 10
    box = f"M{lx:.1f} {by}H{lx+bw-cut:.1f}L{lx+bw:.1f} {by+cut}V{by+bh}H{lx:.1f}Z"
    if PHONE:   # Only the name fits, in up to three lines. The description stays in the alt text.
        names = textwrap.wrap(item["name"], int((bw - 16) / (11 * ADV)))
        assert len(names) <= 3, names
        name = "".join(f'<text x="{lx+8:.1f}" y="{by + 22 + i*15}" font-weight="700" class="ac" style="font-size:11px">{e(s)}</text>'
                       for i, s in enumerate(names))
        body = f'''<g class="ln" style="animation-delay:{delay:.2f}s">
<path d="{box}" fill="{ACCENT}" fill-opacity=".035"/>
<path d="{box}" fill="none" stroke="{ACCENT}" stroke-opacity=".35"/>
<path d="M{lx+bw-cut:.1f} {by}L{lx+bw:.1f} {by+cut}" stroke="{ACCENT}" stroke-width="2"/>
{name}
{star_count(lx + bw - 8, by + 84, stars, 11) if stars is not None else arrow(lx + 8, by + 84, FAINT)}
</g>'''
        alt = f'{item["name"]}: {item["desc"]}.' + (f" {stars} stars." if stars is not None else "")
        return cell_slice(k, n, 120, body, title=item["name"], desc=alt, text=visible(body)), alt
    lines = textwrap.wrap(item["desc"], 21)
    assert len(lines) <= 2, (item["name"], lines)
    desc = "".join(f'<text x="{lx+12:.1f}" y="{by + 46 + i*16}" class="fg" style="font-size:11px">{e(s)}</text>'
                   for i, s in enumerate(lines))
    body = f'''<g class="ln" style="animation-delay:{delay:.2f}s">
<path d="{box}" fill="{ACCENT}" fill-opacity=".035"/>
<path d="{box}" fill="none" stroke="{ACCENT}" stroke-opacity=".35"/>
<path d="M{lx+bw-cut:.1f} {by}L{lx+bw:.1f} {by+cut}" stroke="{ACCENT}" stroke-width="2"/>
<text x="{lx+12:.1f}" y="{by+24}" font-weight="700" class="ac" style="font-size:12px">{e(item["name"])}</text>
{desc}
{star_count(lx + bw - 12, by + 84, stars, 11) if stars is not None else ""}
{arrow(lx + 12, by + 84, FAINT) if stars is None else ""}
</g>'''
    alt = f'{item["name"]}: {item["desc"]}.' + (f" {stars} stars." if stars is not None else "")
    return cell_slice(k, n, 120, body, title=item["name"], desc=alt, text=item["name"] + item["desc"] + str(stars)), alt


# ─────────────────────────────── stack ────────────────────────────────
def build_stack(counter):
    stack = PROFILE["stack"]
    parts = [heading(44, "stack", counter), prompt(96, "swift package show-dependencies --depth 1")]
    if PHONE:
        return build_stack_phone(parts, stack)
    y, rowh = 126, 44
    for r, (cat, items) in enumerate(stack):
        parts.append(f'<g class="ln" style="animation-delay:{.25 + r*.1:.2f}s">')
        parts.append(f'<text x="{X}" y="{y+20}" class="dim" style="font-size:13px">{e(cat)}</text>')
        parts.append(f'<text x="{X+104}" y="{y+20}" class="ac" style="font-size:13px">›</text>')
        x = X + 124
        for it in items:
            w = tw(it, 13) + 26
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" fill="{ACCENT}" fill-opacity=".06" stroke="{ACCENT}" stroke-opacity=".55"/>')
            parts.append(f'<path d="M{x:.1f} {y+8}V{y}H{x+8:.1f}" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
            parts.append(f'<text x="{x+13:.1f}" y="{y+20}" font-weight="700" class="ac" style="font-size:13px">{e(it)}</text>')
            x += w + 10
        assert x <= XR + 10, (cat, x)
        parts.append("</g>")
        y += rowh
    body = "\n".join(parts)
    desc = "Tech stack. " + " ".join(f"{c}: {', '.join(i)}." for c, i in stack)
    return slice_svg(up40(y + 10), body, title="Tech stack", desc=desc, text=visible(body))


def build_stack_phone(parts, stack):
    y = 120
    for r, (cat, items) in enumerate(stack):
        parts.append(f'<g class="ln" style="animation-delay:{.25 + r*.1:.2f}s">')
        parts.append(f'<text x="{X}" y="{y+14}" class="dim" style="font-size:12px">{e(cat)} <tspan class="ac">›</tspan></text>')
        y += 24
        x = X
        for it in items:
            w = tw(it, 12) + 20
            if x + w > XR:
                x, y = X, y + 34
            parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="26" fill="{ACCENT}" fill-opacity=".06" stroke="{ACCENT}" stroke-opacity=".55"/>')
            parts.append(f'<path d="M{x:.1f} {y+7}V{y}H{x+7:.1f}" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
            parts.append(f'<text x="{x+10:.1f}" y="{y+17}" font-weight="700" class="ac" style="font-size:12px">{e(it)}</text>')
            x += w + 8
        parts.append("</g>")
        y += 26 + 18
    body = "\n".join(parts)
    desc = "Tech stack. " + " ".join(f"{c}: {', '.join(i)}." for c, i in stack)
    return slice_svg(up40(y), body, title="Tech stack", desc=desc, text=visible(body))


# ──────────────────────────── rows: writing, releases ────────────────────────────
def build_row(i, date, title, right, *, desc, stars=None):
    """One log line: date › title …… right ↗. With stars, the right side is ★ n."""
    if PHONE and stars is None:
        return build_post_phone(i, date, title, right, desc=desc)
    ds, ts, dx = (11, 12, 72) if PHONE else (13, 14, 94)     # date size, title size, › offset
    tx = X + dx + 18
    rx = XR
    if stars is not None:
        right = str(stars)
    rw = tw(right, 12) + (14 if stars is not None else 0)
    maxc = int((rx - 26 - rw - tx) / (ts * ADV))
    shown = title if len(title) <= maxc else title[:maxc - 1].rstrip(" .,:;") + "…"
    body = f'''<g class="ln" style="animation-delay:{.2 + i*.08:.2f}s">
<rect x="{X-10}" y="4" width="{rx - X + 20}" height="32" fill="{ACCENT}" fill-opacity="{'.04' if i % 2 == 0 else '0'}"/>
<text x="{X}" y="25" class="dim" style="font-size:{ds}px">{e(date)}</text>
<text x="{X+dx}" y="25" class="ac" style="font-size:{ds}px">›</text>
<text x="{tx}" y="25" class="fg" style="font-size:{ts}px">{e(shown)}</text>
{star_count(rx - 22, 25, stars) if stars is not None else f'<text x="{rx - 22}" y="25" text-anchor="end" class="dim" style="font-size:12px">{e(right)}</text>'}
{arrow(rx - 10, 25)}
</g>'''
    return slice_svg(40, body, title=title, desc=desc, text=date + "›" + shown + right)


def build_post_phone(i, date, title, source, *, desc):
    lines = textwrap.wrap(title, int((XR - X - 4) / (13 * ADV)))
    if len(lines) > 2:
        lines = [lines[0], lines[1][:-1].rstrip(" .,:;") + "…"]
    titles = "".join(f'<text x="{X}" y="{46 + k*18}" class="fg" style="font-size:13px">{e(s)}</text>' for k, s in enumerate(lines))
    body = f'''<g class="ln" style="animation-delay:{.2 + i*.08:.2f}s">
<rect x="{X-10}" y="4" width="{XR - X + 20}" height="72" fill="{ACCENT}" fill-opacity="{'.04' if i % 2 == 0 else '0'}"/>
<text x="{X}" y="24" class="dim" style="font-size:11px">{e(date)} <tspan class="ac">›</tspan> {e(source)}</text>
{arrow(XR - 10, 24)}
{titles}
</g>'''
    return slice_svg(80, body, title=title, desc=desc, text=visible(body))


def build_more(label):
    body = f'''<g class="ln" style="animation-delay:.7s">
<text x="{X}" y="26" style="font-size:13px"><tspan class="gr">&gt;&gt;</tspan><tspan class="ac"> {e(label)}</tspan></text>
{arrow(X + tw(">> " + label, 13) + 10, 26)}
</g>'''
    return slice_svg(40, body, title=label, desc=label, text=">> " + label)


def releases(repos):
    """The newest releases of the projects on this profile."""
    names = {p["repo"]: p["name"] for p in PROFILE["projects"] + PROFILE["also"] if p.get("repo")}
    rows = []
    for repo, r in repos.items():
        rel = r.get("release")
        if rel and (r.get("own") or repo in names) and not r.get("archived"):
            rows.append(dict(rel, repo=repo, name=names.get(repo, repo.split("/")[1])))
    rows.sort(key=lambda x: (x["date"], x["repo"]), reverse=True)
    return rows[:5]


# ─────────────────────────────── README ───────────────────────────────
# GitHub rewrites a relative src to the repository, but the phone srcset gets the full URL on main.
PHONE_URL = f"https://github.com/{USER}/{USER}/raw/main/assets/phone"


class Page:
    """The README is rows of images. Images in one row sit side by side with no
    whitespace between them, so their widths sum to 100%."""

    def __init__(self):
        self.files, self.rows = {}, []

    def add(self, file, svgs, width, alt, href=None, same_row=False):
        """svgs: the desktop slice and its phone variant, which a <picture> shows below 600 px."""
        self.files[file], self.files[f"phone/{file}"] = svgs
        text = e(re.sub(r"\s+", " ", alt).strip())   # a blank line in an alt would end the HTML block
        img = (f'<picture><source media="(max-width: 600px)" srcset="{PHONE_URL}/{file}">'
               f'<img src="./assets/{file}" width="{width}" align="top" alt="{text}"></picture>')
        cell = f'<a href="{e(href)}">{img}</a>' if href else img
        if same_row and self.rows:
            self.rows[-1].append(cell)
        else:
            self.rows.append([cell])

    def readme(self):
        rows = "\n".join("".join(r) for r in self.rows)
        return f"""<!-- Generated by `mise run readme` from profile/. Edit that, not this. -->
<p align="center">
{rows}
</p>

<p align="center"><sub>Regenerated every day by <code>mise run readme</code> (<a href="profile/">source</a>). Console design and contribution city by <a href="https://github.com/georgekobaidze/georgekobaidze">Giorgi Kobaidze</a> (<a href="https://dev.to/georgekobaidze/i-turned-my-github-profile-into-a-cyberpunk-console-with-a-city-built-from-my-contributions-h4c">how he built it</a>), used under MIT. Install lines and phone slices after <a href="https://github.com/jdx">@jdx</a>.</sub></p>
"""


def main():
    stats = json.loads((DATA / "stats.json").read_text())
    repos = json.loads((DATA / "repos.json").read_text())
    calendar = json.loads((DATA / "calendar.json").read_text()) if (DATA / "calendar.json").exists() else None
    stars = lambda repo: repos.get(repo, {}).get("stars")  # noqa: E731
    n = 0

    def counter():
        nonlocal n
        n += 1
        return f"// {n:02d}"

    desc_of = lambda svg: html.unescape(re.search(r'<desc id="d">(.*?)</desc>', svg, re.S).group(1))  # noqa: E731

    page = Page()
    page.add("header.svg", both(build_header), "100%", PROFILE["summary"])
    page.add("links.svg", both(section_head, "links", counter(), f"ping {USER} --all-channels", title="Links", desc="Where to find me"), "100%", "Links")
    for k, link in enumerate(PROFILE["links"]):
        page.add(f"links/{link['icon']}.svg", both(build_link_button, k, link), f"{100 // len(PROFILE['links'])}%",
                 f'{link["label"]}: {link["handle"]}', link["url"], same_row=k > 0)

    svgs = both(build_stats, stats, counter())
    page.add("stats.svg", svgs, "100%", desc_of(svgs[0]))
    if calendar:
        svgs = both(build_city, calendar, stats["updated"], counter())
        page.add("contribution-city.svg", svgs, "100%", desc_of(svgs[0]))

    page.add("projects.svg", both(section_head, "projects", counter(), "ls -l ~/projects", title="Projects", desc="Projects"), "100%", "Projects")
    for i, p in enumerate(PROFILE["projects"]):
        side = "L" if i % 2 == 0 else "R"
        s = stars(p["repo"])
        page.add(f"projects/{slug(p['name'])}.svg", both(build_card, p, side, 0.3 + i * 0.12, s), "50%",
                 card_alt(p, s), p.get("url") or f"https://github.com/{p['repo']}", same_row=side == "R")
    also = PROFILE["also"]
    cols = 4
    assert len(also) % cols == 0, "fill every row of the small projects"
    for i, item in enumerate(also):
        (svg, alt), (phone_svg, _) = both(build_also, i % cols, cols, item, stars(item["repo"]) if item.get("repo") else None,
                                          0.3 + (i % cols) * 0.08)
        page.add(f"projects/also-{slug(item['name'])}.svg", (svg, phone_svg), f"{100 // cols}%", alt,
                 item.get("url") or f"https://github.com/{item['repo']}", same_row=i % cols > 0)

    rel = releases(repos)
    if rel:
        page.add("releases.svg", both(section_head, "releases", counter(), "gh release list --latest", "auto-updated",
                                      title="Releases", desc="The newest releases"), "100%", "Releases: the newest releases")
        for i, r in enumerate(rel):
            alt = f'{r["name"]} {r["tag"]}, released {r["date"]}'
            page.add(f"releases/{i+1}.svg", both(build_row, i, r["date"], f'{r["name"]} {r["tag"]}', "", desc=alt, stars=stars(r["repo"])),
                     "100%", alt, r["url"])

    page.add("stack.svg", both(build_stack, counter()), "100%",
             "Tech stack. " + " ".join(f"{c}: {', '.join(i)}." for c, i in PROFILE["stack"]))

    w = PROFILE["writing"]
    page.add("writing.svg", both(section_head, "writing", counter(), "tail -n 5 ~/posts.log", title="Writing", desc="Latest posts"), "100%", "Writing: latest posts")
    for i, a in enumerate(w["posts"][:5]):
        alt = f'{a["title"]}, published {a["date"]} on {a["publication"]}'
        page.add(f"writing/post-{i+1}.svg", both(build_row, i, a["date"], a["title"], a["publication"], desc=alt), "100%", alt, a["url"])
    page.add("writing/all-posts.svg", both(build_more, w["all"]["label"]), "100%", w["all"]["label"], w["all"]["url"])
    page.add("footer.svg", both(build_footer), "100%", "Program ended with exit code: 0")

    # Remove the slices of an earlier run that this run does not draw.
    for old in OUT.rglob("*.svg"):
        if str(old.relative_to(OUT)) not in page.files:
            old.unlink()
    for rel_path, svg in page.files.items():
        path = OUT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg)
    (ROOT / "README.md").write_text(page.readme())
    print("rendered", len(page.files), "SVGs into", OUT.relative_to(ROOT))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


if __name__ == "__main__":
    main()
