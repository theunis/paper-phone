"""Command-line interface: `paper-phone build daily`, `paper-phone all`, `paper-phone init`."""

from __future__ import annotations

import datetime as dt
from importlib import resources
from pathlib import Path

import click

from paper_phone import __version__
from paper_phone.config import EDITIONS, Config, Edition, Mode, get_settings, load_config
from paper_phone.http import Http

DEFAULT_CONFIG = Path("paperphone.yaml")


def _config(path: Path | None) -> Config:
    if path is None and DEFAULT_CONFIG.exists():
        path = DEFAULT_CONFIG
    return load_config(path)


def _date(value: str | None) -> dt.date:
    if not value or value == "today":
        return dt.date.today()
    if value == "tomorrow":
        return dt.date.today() + dt.timedelta(days=1)
    return dt.date.fromisoformat(value)


def build_edition(
    cfg: Config,
    edition: Edition,
    date: dt.date,
    *,
    modes: list[Mode],
    out: Path,
    offline: bool,
    maps: bool,
    preview: bool,
    keep_html: bool,
) -> list[Path]:
    from paper_phone.build import gather
    from paper_phone.render import print_pdf, reading_order_html, render_html

    settings = get_settings()
    http = Http(settings.cache_dir, offline=offline, contact=cfg.contact_email)
    click.echo(f"· {edition}: gathering data for {date.isoformat()} …")
    data = gather(cfg, edition, date, http, maps=maps)
    for warning in data.warnings:
        click.secho(f"  ! {warning}", fg="yellow")
    out.mkdir(parents=True, exist_ok=True)
    tag = data.start.isoformat() if edition != "daily" else date.isoformat()
    written = []
    for mode in modes:
        stem = f"paper-phone_{edition}_{tag}_{mode}"
        rendered = render_html(data, mode)
        html_path = out / f"{stem}.html"
        html_path.write_text(rendered.html, encoding="utf-8")
        pdf_path = out / f"{stem}.pdf"
        png_path = out / f"{stem}.png" if preview else None
        print_pdf(html_path, pdf_path, channel=settings.browser_channel, png_path=png_path)
        written.append(pdf_path)
        if png_path is not None:
            written.append(png_path)
            reading = out / f"{stem}_booklet.html"
            reading.write_text(reading_order_html(data, mode, rendered.html), encoding="utf-8")
            print_pdf(reading, out / f"{stem}_booklet.pdf", channel=settings.browser_channel)
            written.append(out / f"{stem}_booklet.pdf")
            if not keep_html:
                reading.unlink()
        if not keep_html:
            html_path.unlink()
        click.echo(f"  ✓ {pdf_path}")
    return written


def _common(fn):
    options = [
        click.option(
            "--config",
            "-c",
            "config",
            type=click.Path(path_type=Path, exists=True),
            help="YAML config (default: ./paperphone.yaml).",
        ),
        click.option(
            "--date",
            "-d",
            "date",
            default=None,
            help="Anchor date: YYYY-MM-DD, 'today' or 'tomorrow'.",
        ),
        click.option(
            "--mode",
            "-m",
            type=click.Choice(["color", "bw", "both"]),
            default="both",
            show_default=True,
            help="Colour, black & white, or both.",
        ),
        click.option(
            "--paper",
            type=click.Choice(["a4", "letter"]),
            default=None,
            help="Override the paper size.",
        ),
        click.option(
            "--back",
            type=click.Choice(["maps", "poster", "blank"]),
            default=None,
            help="What to print on the back of the sheet.",
        ),
        click.option(
            "--out",
            "-o",
            type=click.Path(path_type=Path),
            default=None,
            help="Output directory (default: ./output).",
        ),
        click.option("--offline", is_flag=True, help="Use cached data only."),
        click.option("--no-maps", is_flag=True, help="Skip map downloads."),
        click.option(
            "--preview/--no-preview",
            default=True,
            show_default=True,
            help="Also write a PNG and a booklet-order PDF.",
        ),
        click.option("--keep-html", is_flag=True, help="Keep the intermediate HTML."),
    ]
    for option in reversed(options):
        fn = option(fn)
    return fn


def _run(editions, config, date, mode, paper, back, out, offline, no_maps, preview, keep_html):
    cfg = _config(config)
    if paper:
        cfg.paper = paper
    if back:
        cfg.back = back
    modes: list[Mode] = ["color", "bw"] if mode == "both" else [mode]
    out = out or get_settings().output_dir
    for edition in editions:
        build_edition(
            cfg,
            edition,
            _date(date),
            modes=modes,
            out=out,
            offline=offline,
            maps=not no_maps,
            preview=preview,
            keep_html=keep_html,
        )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="paper-phone")
def cli() -> None:
    """Print a foldable eight-page pocket booklet that stands in for your phone."""


@cli.command()
@click.argument("edition", type=click.Choice(EDITIONS), default="daily")
@_common
def build(edition, **kwargs) -> None:
    """Build one edition: daily, weekly, monthly or travel."""
    _run([edition], **kwargs)


@cli.command(name="all")
@_common
def build_all(**kwargs) -> None:
    """Build every edition (travel only when a trip is configured)."""
    cfg = _config(kwargs["config"])
    editions = [e for e in EDITIONS if e != "travel" or cfg.trip]
    _run(editions, **kwargs)


@cli.command()
@click.argument("path", type=click.Path(path_type=Path), default=DEFAULT_CONFIG)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(path: Path, force: bool) -> None:
    """Write an example config (and tasks.md) to start from."""
    examples = resources.files("paper_phone") / "examples"
    targets = {
        path: examples / "paperphone.yaml",
        path.parent / "tasks.md": examples / "tasks.md",
        path.parent / "calendar.ics": examples / "calendar.ics",
    }
    for target, source in targets.items():
        if target.exists() and not force:
            click.echo(f"· {target} exists, skipped (use --force)")
            continue
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo(f"✓ wrote {target}")


@cli.command()
def fold() -> None:
    """How to fold the printed sheet."""
    click.echo(
        """
  Print the PDF at 100 % (actual size). Page 2 of the PDF is the map side:
  print double-sided, or feed the sheet back in, whichever way round.

   +-----+-----+-----+-----+
   |  5  |  4  |  3  |  2  |   top row prints upside down
   +-----+- - -+- - -+-----+   <- cut the middle half of this line
   |  6  |  7  |  8  |  1  |
   +-----+-----+-----+-----+

  1. Fold in half, short edges together (print outside). Crease well.
  2. From the folded edge, cut along the middle line up to the next crease.
  3. Open up. Fold in half the long way, print outside.
  4. Push both ends towards the middle: the cut opens into a diamond.
     Keep pushing until the four wings meet, then flatten with page 1 on top.

  Unfold completely to read the maps on the back.
"""
    )


@cli.command()
@click.option("--config", "-c", "config", type=click.Path(path_type=Path, exists=True))
def info(config: Path | None) -> None:
    """Show settings and bundled content."""
    from paper_phone.modules import REGISTRY
    from paper_phone.sources import content

    settings = get_settings()
    cfg = _config(config)
    click.echo(f"cache:      {settings.cache_dir}")
    click.echo(f"output:     {settings.output_dir}")
    click.echo(f"home:       {cfg.home.query or (cfg.home.lat, cfg.home.lon)}")
    click.echo(f"paper:      {cfg.paper} · back: {cfg.back}")
    click.echo(f"modules:    {', '.join(sorted(REGISTRY))}")
    click.echo(f"words:      {', '.join(content.available('words'))}")
    click.echo(f"phrases:    {', '.join(content.available('phrases'))}")
    click.echo(f"recipes:    {len(content.recipes())}")
    click.echo(f"countries:  {len(content.countries())}")


if __name__ == "__main__":
    cli()
