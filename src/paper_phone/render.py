"""Turn gathered data into imposed HTML, then print it to PDF with headless Chrome."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

from jinja2 import ChainableUndefined, Environment, FileSystemLoader
from markupsafe import Markup

from paper_phone import imposition
from paper_phone.build import Data
from paper_phone.config import Mode
from paper_phone.icons import icon, icon_paths
from paper_phone.layout import back_boxes
from paper_phone.maps.render import POI_LABELS, POI_STYLE, MapRenderer
from paper_phone.modules import REGISTRY, PageCtx
from paper_phone.modules.core import MONTH_NAME, d_long, d_short, duration, edition_meta, t_hm, temp
from paper_phone.sources import astro

PACKAGE = resources.files("paper_phone")
TEMPLATES = Path(str(PACKAGE / "templates"))
ASSETS = Path(str(PACKAGE / "assets"))


def _fill(kind: str, pitch: float) -> Markup:
    """Writing space (dots, ruled lines, checkbox rows) drawn at print time.

    templates/fill.js measures the container and draws whole rows only, as real
    vector shapes: Chrome rasterises SVG <pattern> fills when printing to PDF.
    """
    return Markup(f'<span class="gen" data-kind="{kind}" data-pitch="{pitch}"></span>')


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def icon_markup(name: str) -> Markup:
        return Markup(icon(name))

    def moon_markup(m: astro.Moon, size: float) -> Markup:
        return Markup(astro.moon_svg(m, size))

    def month_name(d: dt.date) -> str:
        return MONTH_NAME[d.month - 1]

    def dots(pitch: float = 4) -> Markup:
        return _fill("dots", pitch)

    def ruled(pitch: float = 5) -> Markup:
        return _fill("lines", pitch)

    def checklist(pitch: float = 4.6) -> Markup:
        return _fill("checks", pitch)

    # jinja2 types `globals` from its defaults; widen it to what it really holds
    namespace = cast(dict[str, Any], env.globals)
    namespace.update(
        icon=icon_markup,
        temp=temp,
        t_hm=t_hm,
        d_short=d_short,
        duration=duration,
        moon=astro.moon,
        moon_svg=moon_markup,
        month_name=month_name,
        dots=dots,
        ruled=ruled,
        checklist=checklist,
    )
    namespace["macros"] = env.get_template("macros.html.j2").module
    return env


@dataclass
class Rendered:
    html: str
    map_results: list[Any]


def _wrap(value: Any) -> Any:
    """Mark pre-rendered SVG strings in a module context as safe."""
    if isinstance(value, str) and value.startswith("<svg"):
        return Markup(value)
    return value


def render_page(env: Environment, data: Data, number: int, mode: Mode) -> str:
    spec = data.pages[number - 1]
    keys = [spec] if isinstance(spec, str) else list(spec)
    footer = f"Paper Phone · {edition_meta(data)}"
    if len(keys) == 1:
        m = REGISTRY[keys[0]]
        page = PageCtx(number, "full", mode)
        c = {k: _wrap(v) for k, v in m.prepare(data, page).items()}
        return env.get_template("page.html.j2").render(
            m=m, c=c, n=number, page=page, data=data, footer=footer
        )
    parts = []
    for position, key in enumerate(keys[:2]):
        m = REGISTRY[key]
        page = PageCtx(number, "half", mode, position)
        c = {k: _wrap(v) for k, v in m.prepare(data, page).items()}
        parts.append({"m": m, "c": c, "page": page})
    return env.get_template("split.html.j2").render(parts=parts, n=number, data=data, footer=footer)


def render_maps(data: Data, mode: Mode) -> list[Any]:
    results = []
    for rm in data.maps:
        if rm.data is None:
            continue
        number = len(results) + 1
        renderer = MapRenderer(
            rm.data,
            rm.frame,
            mode=mode,
            detail=rm.detail,
            prefix=f"{rm.key}{mode[0]}",
            title=rm.title,
            markers=rm.markers,
            focus=rm.focus,
            number=number if len(data.maps) > 1 else None,
        )
        result = renderer.render()
        result.box = rm.box
        results.append(result)
    return results


def render_back(env: Environment, data: Data, mode: Mode, map_results: list[Any]) -> str:
    boxes = back_boxes(data.sheet, data.cfg.back)
    scissors = Markup(icon_paths("scissors"))
    used = {p.kind for r in map_results for p in r.pois}
    legend = []
    for kind, (ic, color, _, _) in POI_STYLE.items():
        if kind in used:
            legend.append((kind, ic, color if mode == "color" else "#1a1a1a", POI_LABELS[kind]))
    legend = legend[:14]
    return env.get_template("back.html.j2").render(
        maps=[{"box": r.box, "svg": Markup(r.svg)} for r in map_results],
        info=boxes.info,
        fold_svg=Markup(env.get_template("fold.svg.j2").render(scissors=scissors)),
        legend=legend,
        solution=data.extras.get("sudoku_solution"),
        rates=data.rate is not None,
        printed=d_long(data.generated.date()) + f" {t_hm(data.generated)}",
        edition_label=f"{data.edition.capitalize()} · {edition_meta(data)}",
    )


def render_html(data: Data, mode: Mode, *, front: bool = True, back: bool = True) -> Rendered:
    env = environment()
    map_results = render_maps(data, mode)
    data.extras["map_results"] = map_results
    data.extras.pop("sudoku_solution", None)
    sheet = data.sheet
    slots = []
    for slot in imposition.slots():
        slots.append(
            {
                "x": round(slot.col * sheet.panel_w, 3),
                "y": round(slot.row * sheet.panel_h, 3),
                "rotated": slot.rotated,
                "html": Markup(render_page(env, data, slot.page, mode)),
            }
        )
    back_html = None
    if back and data.cfg.back != "blank":
        back_html = Markup(render_back(env, data, mode, map_results))
    html = env.get_template("sheet.html.j2").render(
        mode=mode,
        data=data,
        sheet=sheet,
        slots=slots,
        front=front,
        back=back_html,
        css=Markup((TEMPLATES / "style.css").read_text(encoding="utf-8")),
        fonts_css=Markup((ASSETS / "fonts" / "fonts.css").read_text(encoding="utf-8")),
        asset_base=(ASSETS / "fonts").as_uri() + "/",
        scissors=Markup(icon_paths("scissors")),
        fill_js=Markup((TEMPLATES / "fill.js").read_text(encoding="utf-8")),
    )
    return Rendered(html=html, map_results=map_results)


def reading_order_html(data: Data, mode: Mode, sheet_html: str) -> str:
    """A screen preview: the booklet as spreads (1 | 2-3 | 4-5 | 6-7 | 8)."""
    env = environment()
    sheet = data.sheet
    pages = {n: Markup(render_page(env, data, n, mode)) for n in range(1, 9)}
    spreads = [(None, 1), (2, 3), (4, 5), (6, 7), (8, None)]
    head, _, _ = sheet_html.partition("<body>")
    head = head.replace(
        f"@page {{ size: {sheet.width}mm {sheet.height}mm;",
        f"@page {{ size: {sheet.panel_w * 2 + 12}mm {sheet.panel_h + 12}mm;",
    )
    body = []
    for left, right in spreads:
        cells = []
        for n in (left, right):
            if n is None:
                cells.append('<div class="pv-slot empty"></div>')
            else:
                cells.append(f'<div class="pv-slot">{pages[n]}</div>')
        body.append(f'<section class="pv-spread">{"".join(cells)}</section>')
    script = (TEMPLATES / "fill.js").read_text(encoding="utf-8")
    return (
        head + '<body class="preview">' + "".join(body) + f"<script>{script}</script></body></html>"
    )


def print_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    channel: str = "chrome",
    png_path: Path | None = None,
) -> None:
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        except Error:
            browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(html_path.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        if png_path is not None:
            page.emulate_media(media="print")
            page.screenshot(path=str(png_path), full_page=True)
        browser.close()
