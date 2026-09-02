"""Chart styling.

One place decides how every chart looks, so a new chart cannot quietly
arrive in a different visual language than the rest.

Charts are rendered dark because they are read inside a Telegram chat that
is dark for most people, and a white rectangle in a dark thread is the one
thing that always looks wrong.
"""

from __future__ import annotations

import matplotlib

# Agg before pyplot: the process has no display, and importing an
# interactive backend on a server fails in ways that are tedious to read.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

BACKGROUND = "#161B1C"
SURFACE = "#1E2425"
INK = "#E7EDEB"
MUTED = "#96A2A1"
GRID = "#2A3231"

ACCENT = "#E3AC33"
POSITIVE = "#59B07C"
NEGATIVE = "#DE7264"
NEUTRAL = "#7FA8C9"

# Muscle groups get stable colours: the same group must not change colour
# between two charts a user reads one after the other.
GROUP_COLOURS = (
    "#E3AC33",
    "#59B07C",
    "#7FA8C9",
    "#DE7264",
    "#B99BD1",
    "#7FC7C0",
    "#D9A06B",
    "#9FB86A",
    "#C98FA8",
    "#8A9BB8",
    "#CBBF7A",
    "#6FA9A0",
)

DPI = 160
FIGSIZE = (7.2, 4.2)

# Bundled with matplotlib and covers Cyrillic; naming it explicitly means a
# missing system font cannot silently turn every label into boxes.
FONT_FAMILY = "DejaVu Sans"


def apply_theme() -> None:
    plt.rcParams.update(
        {
            "font.family": FONT_FAMILY,
            "font.size": 11,
            "figure.facecolor": BACKGROUND,
            "figure.dpi": DPI,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": MUTED,
            "axes.titlecolor": INK,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "legend.frameon": False,
            "legend.labelcolor": MUTED,
            "figure.autolayout": True,
        }
    )


def new_figure(title: str) -> tuple[Figure, Axes]:
    apply_theme()
    figure, axes = plt.subplots(figsize=FIGSIZE)
    axes.set_title(title, pad=14)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    return figure, axes
