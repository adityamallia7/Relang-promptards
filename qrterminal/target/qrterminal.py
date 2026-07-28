"""qrterminal - generate QR codes for the terminal.

Python port of the Go package github.com/mdp/qrterminal.
Renders a QR code as ANSI color blocks, compact Unicode half-blocks,
or Sixel graphics (Unix terminals that support it).

Dependency: segno  ->  pip install segno
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from io import StringIO
from typing import Optional, TextIO

import segno

# --- ANSI full-block cells (two spaces wide so each module looks square) ---
WHITE = "\033[47m  \033[0m"   # white background
BLACK = "\033[40m  \033[0m"   # black background

# --- Unicode half-block glyphs. Naming is <TOP><BOTTOM> = which half is "lit". ---
BLACK_WHITE = "\u2584"   # ▄  top dark, bottom lit
BLACK_BLACK = " "        #    both dark (terminal background shows through)
WHITE_BLACK = "\u2580"   # ▀  top lit, bottom dark
WHITE_WHITE = "\u2588"   # █  both lit

# --- Error-correction levels (segno strings) ---
L = "l"
M = "m"
H = "h"

# --- Default quiet-zone (border) width in modules ---
QUIET_ZONE = 4

# --- Sixel palette: color 0 = black, color 1 = white ---
SIXEL_BEGIN = "\x1bPq\n#0;2;0;0;0#1;2;100;100;100\n"
SIXEL_END = "\x1b\\"
SIXEL_BLOCK_SIZE = 12  # pixels per module; must be > 6


@dataclass
class Config:
    """Options for rendering a QR code."""
    level: str = M
    writer: Optional[TextIO] = None
    half_blocks: bool = False
    black_char: str = ""
    black_white_char: str = ""
    white_char: str = ""
    white_black_char: str = ""
    quiet_zone: int = QUIET_ZONE
    with_sixel: bool = False


# --------------------------------------------------------------------------- #
# Matrix helpers
# --------------------------------------------------------------------------- #
def _matrix(text: str, level: str):
    """Encode text and return (matrix, size). matrix[y][x] == 1 means dark."""
    qr = segno.make(text, error=level)
    rows = [list(row) for row in qr.matrix_iter(border=0)]
    return rows, len(rows)


def _black(m, size: int, x: int, y: int) -> bool:
    """True if module (x, y) is dark. Out-of-range reads as light (like the Go qr lib)."""
    if 0 <= y < size and 0 <= x < len(m[y]):
        return m[y][x] == 1
    return False


# --------------------------------------------------------------------------- #
# Sixel capability probe (Unix only)
# --------------------------------------------------------------------------- #
def is_sixel_supported(w) -> bool:
    """Ask the terminal (via a device-attributes query) whether it speaks Sixel."""
    if w is not sys.stdout:
        return False
    try:
        import select
        import termios
        import tty
    except ImportError:
        return False  # not a Unix terminal
    if not sys.stdout.isatty():
        return False

    fd = sys.stdout.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[c")   # Primary Device Attributes request
        sys.stdout.flush()
        buf = ""
        # Reply arrives fast; poll briefly so we never hang.
        while select.select([fd], [], [], 0.1)[0]:
            chunk = os.read(fd, 1024).decode("latin-1", "ignore")
            if not chunk:
                break
            buf += chunk
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Reply looks like "\x1b[?62;1;4;6c"; capability "4" means Sixel.
    caps = buf.replace("\x1b[?", "").rstrip("c").split(";")
    return "4" in caps


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def _write_full_blocks(c: Config, w: TextIO, m, size: int) -> None:
    white, black = c.white_char, c.black_char
    qz = c.quiet_zone
    line_w = size + qz * 2

    for _ in range(qz):                      # top border
        w.write(white * line_w + "\n")
    for i in range(size + 1):
        w.write(white * qz)                  # left border
        for j in range(size + 1):
            w.write(black if _black(m, size, j, i) else white)
        w.write(white * (qz - 1) + "\n")     # right border
    for _ in range(qz - 1):                   # bottom border
        w.write(white * line_w + "\n")


def _write_half_blocks(c: Config, w: TextIO, m, size: int) -> None:
    ww, bb = c.white_char, c.black_char
    wb, bw = c.white_black_char, c.black_white_char
    qz = c.quiet_zone
    line_w = size + qz * 2

    # top border
    if qz % 2 != 0:
        w.write(bw * line_w + "\n")
    for _ in range(qz // 2):
        w.write(ww * line_w + "\n")

    # two module-rows are packed into one text row
    for i in range(0, size + 1, 2):
        w.write(ww * qz)                     # left border
        for j in range(size + 1):
            curr = _black(m, size, j, i)
            nxt = _black(m, size, j, i + 1) if (i + 1 < size) else False
            if curr and nxt:
                w.write(bb)
            elif curr and not nxt:
                w.write(bw)
            elif not curr and not nxt:
                w.write(ww)
            else:
                w.write(wb)
        w.write(ww * (qz - 1) + "\n")        # right border

    # bottom border
    if qz % 2 == 0:
        for _ in range(qz // 2 - 1):
            w.write(ww * line_w + "\n")
        w.write(wb * line_w + "\n")
    else:
        for _ in range(qz // 2):
            w.write(ww * line_w + "\n")


def _write_sixel(c: Config, w: TextIO, m, size: int) -> None:
    block = SIXEL_BLOCK_SIZE
    if size > 50:
        block //= 2
    line = block // 6                        # sixel rows needed per module row
    qz = c.quiet_zone
    full = block * (size + qz * 2)

    w.write(SIXEL_BEGIN)
    w.write((f"#1!{full}~-\n") * (qz * line))          # top border

    for i in range(size + 1):
        flag = -1          # color of the run currently being built
        repeat = 0
        content = StringIO()
        if qz > 0:
            content.write(f"#1!{block * qz}~")         # left border
        for j in range(size + 1):
            if _black(m, size, j, i):
                if flag == 1:                          # flush pending white run
                    content.write(f"#1!{block * repeat}~")
                    repeat = 0
                flag = 0
                repeat += 1
            else:
                if flag == 0:                          # flush pending black run
                    content.write(f"#0!{block * repeat}~")
                    repeat = 0
                flag = 1
                repeat += 1
        if repeat > 0:
            content.write(f"#{flag}!{block * repeat}~")
        if qz > 1:
            content.write(f"#1!{block * (qz - 1)}~")   # right border
        content.write("-\n")
        row = content.getvalue()
        for _ in range(line):                          # repeat to make module square
            w.write(row)

    w.write((f"#1!{full}~-\n") * ((qz - 1) * line))    # bottom border
    if qz > 1:
        w.write(f"#1!{full}~-")                        # last line (iTerm2 fix)
    w.write(SIXEL_END)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_with_config(text: str, config: Config) -> None:
    """Render `text` using an explicit Config."""
    if config.quiet_zone < 1:
        config.quiet_zone = 1
    w = config.writer if config.writer is not None else sys.stdout
    m, size = _matrix(text, config.level)

    if not config.black_char:
        config.black_char = BLACK_BLACK
    if not config.white_black_char:
        config.white_black_char = WHITE_BLACK
    if not config.white_char:
        config.white_char = WHITE_WHITE
    if not config.black_white_char:
        config.black_white_char = BLACK_WHITE

    if config.half_blocks:
        _write_half_blocks(config, w, m, size)
    elif config.with_sixel:
        _write_sixel(config, w, m, size)
    else:
        _write_full_blocks(config, w, m, size)


def generate(text: str, level: str = M, writer: Optional[TextIO] = None) -> None:
    """Render `text` with ANSI color blocks (auto-uses Sixel if the terminal supports it)."""
    w = writer if writer is not None else sys.stdout
    config = Config(
        level=level, writer=w,
        black_char=BLACK, white_char=WHITE,
        quiet_zone=QUIET_ZONE,
    )
    config.with_sixel = is_sixel_supported(w)
    generate_with_config(text, config)


def generate_half_block(text: str, level: str = M, writer: Optional[TextIO] = None) -> None:
    """Render `text` with compact Unicode half-blocks (half the height)."""
    w = writer if writer is not None else sys.stdout
    config = Config(
        level=level, writer=w, half_blocks=True,
        black_char=BLACK_BLACK, white_black_char=WHITE_BLACK,
        white_char=WHITE_WHITE, black_white_char=BLACK_WHITE,
        quiet_zone=QUIET_ZONE,
    )
    generate_with_config(text, config)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Generate a QR code in the terminal.")
    p.add_argument("text", help="text or URL to encode")
    p.add_argument("-l", "--level", choices=["l", "m", "h"], default="m",
                   help="error-correction level (default: m)")
    p.add_argument("--half", action="store_true",
                   help="use compact half-block rendering")
    args = p.parse_args()

    if args.half:
        generate_half_block(args.text, args.level)
    else:
        generate(args.text, args.level)
