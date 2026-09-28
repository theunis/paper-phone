"""End to end without network: every edition still renders (with gaps) offline."""

from __future__ import annotations

import datetime as dt
import re

import pytest
from click.testing import CliRunner

from paper_phone.build import gather
from paper_phone.cli import cli
from paper_phone.config import Config, TripConfig
from paper_phone.http import Http
from paper_phone.render import reading_order_html, render_html


def _config() -> Config:
    return Config(
        trip=TripConfig(
            destination="Lisbon, Portugal", start=dt.date(2026, 10, 12), end=dt.date(2026, 10, 16)
        )
    )


@pytest.mark.parametrize("edition", ["daily", "weekly", "monthly", "travel"])
@pytest.mark.parametrize("mode", ["color", "bw"])
def test_offline_render(tmp_path, edition, mode) -> None:
    http = Http(tmp_path, offline=True)
    data = gather(_config(), edition, dt.date(2026, 9, 28), http)
    assert data.warnings  # nothing cached, so the network parts report gaps
    html = render_html(data, mode).html
    assert html.count('<div class="slot') == 8
    assert html.count('<div class="slot rot"') == 4
    assert f'data-mode="{mode}"' in html
    assert "cutline" in html and "<script>" in html
    assert not re.search(r"\bUndefined\b|\{\{|\{%", html)
    booklet = reading_order_html(data, mode, html)
    assert booklet.count('class="pv-spread"') == 5


def test_cli_help_and_fold() -> None:
    runner = CliRunner()
    assert runner.invoke(cli, ["--help"]).exit_code == 0
    result = runner.invoke(cli, ["fold"])
    assert result.exit_code == 0 and "cut" in result.output


def test_cli_init(tmp_path) -> None:
    target = tmp_path / "paperphone.yaml"
    result = CliRunner().invoke(cli, ["init", str(target)])
    assert result.exit_code == 0
    assert (
        target.exists()
        and (tmp_path / "tasks.md").exists()
        and (tmp_path / "calendar.ics").exists()
    )
    from paper_phone.config import load_config

    cfg = load_config(target)
    assert cfg.trip is not None and cfg.training is not None
