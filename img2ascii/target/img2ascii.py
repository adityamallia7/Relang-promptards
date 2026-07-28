#!/usr/bin/env python3
"""img2ascii - convert images to ASCII art.

Python port of the C tool at https://github.com/JosefVesely/img2ascii

Dependencies:  pip install pillow numpy
Usage:         python img2ascii.py -i images/cat.png -w 80 -p
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Characters ordered from densest to lightest (same set as the C version).
DEFAULT_CHARS = (
    "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
)

# Image formats Pillow reads that the original tool supported, plus a few extras.
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}

# Terminal characters are roughly twice as tall as they are wide, so the
# pixel height is halved to keep the art from looking stretched.
CHAR_ASPECT_RATIO = 2


def load_image(input_path: Path, desired_width: int | None) -> np.ndarray:
    """Open an image, resize it, and return an (height, width, 3) uint8 array."""
    try:
        image = Image.open(input_path)
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {input_path}")
    except OSError as exc:
        sys.exit(f"Error: could not load image: {exc}")

    # Flatten transparency onto white, then force 3 channels.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image)
    image = image.convert("RGB")

    original_width, original_height = image.size

    if desired_width is None:
        desired_width = original_width
    elif desired_width <= 0:
        sys.exit("Error: --width must be greater than 0")

    # Scale height by the same factor as the width, then halve it for the
    # character aspect ratio.
    scale = desired_width / original_width
    desired_height = max(1, int(original_height * scale / CHAR_ASPECT_RATIO))

    image = image.resize((desired_width, desired_height), Image.LANCZOS)
    return np.asarray(image, dtype=np.uint8)


def get_intensity(pixels: np.ndarray) -> np.ndarray:
    """Convert RGB to perceived brightness (0-255) using the standard luma weights."""
    r = pixels[:, :, 0].astype(np.float32)
    g = pixels[:, :, 1].astype(np.float32)
    b = pixels[:, :, 2].astype(np.float32)
    return np.round(0.299 * r + 0.587 * g + 0.114 * b).astype(np.int32)


def get_char_indices(pixels: np.ndarray, characters: str) -> np.ndarray:
    """Map each pixel's brightness onto an index in the character string."""
    count = len(characters)
    if count == 1:
        return np.zeros(pixels.shape[:2], dtype=np.int32)

    intensity = get_intensity(pixels)
    indices = (intensity / (255 / (count - 1))).astype(np.int32)
    return np.clip(indices, 0, count - 1)


def get_output_grayscale(pixels: np.ndarray, characters: str) -> str:
    """Build plain-text ASCII art with no color codes."""
    indices = get_char_indices(pixels, characters)
    char_array = np.array(list(characters))
    rows = char_array[indices]
    return "\n".join("".join(row) for row in rows) + "\n"


def get_output_rgb(pixels: np.ndarray, characters: str) -> str:
    """Build ASCII art where each character carries the original pixel's color."""
    indices = get_char_indices(pixels, characters)
    height, width = indices.shape

    parts: list[str] = []
    previous_color: tuple[int, int, int] | None = None

    for y in range(height):
        for x in range(width):
            color = (int(pixels[y, x, 0]), int(pixels[y, x, 1]), int(pixels[y, x, 2]))
            # Only emit an escape code when the color actually changes.
            if color != previous_color:
                parts.append(f"\033[38;2;{color[0]};{color[1]};{color[2]}m")
                previous_color = color
            parts.append(characters[indices[y, x]])
        parts.append("\n")

    parts.append("\033[0m")  # reset the terminal color
    return "".join(parts)


def convert(
    input_path: Path,
    output_path: Path | None,
    characters: str,
    width: int | None,
    grayscale: bool,
    reverse: bool,
    print_output: bool,
    debug: bool,
) -> None:
    """Convert one image and print and/or save the result."""
    if reverse:
        characters = characters[::-1]

    pixels = load_image(input_path, width)
    height_out, width_out = pixels.shape[:2]

    if grayscale:
        output = get_output_grayscale(pixels, characters)
    else:
        output = get_output_rgb(pixels, characters)

    if debug:
        print(
            f"Input: {input_path}\n"
            f"Output: {output_path if output_path else 'stdout'}\n"
            f"Resolution: {width_out}x{height_out}\n"
            f"Characters ({len(characters)}): \"{characters}\""
        )

    if print_output:
        # errors="replace" stops old Windows consoles from crashing on odd glyphs.
        sys.stdout.write(output)
        sys.stdout.flush()

    if output_path is not None:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output, encoding="utf-8")
        except OSError as exc:
            sys.exit(f"Error: could not create an output file: {exc}")
        print(f"Saved: {output_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="img2ascii",
        description="A command-line tool for converting images to ASCII art",
    )
    parser.add_argument("-i", "--input", required=True,
                        help="path of the input image file, or a folder of images")
    parser.add_argument("-o", "--output",
                        help="path of the output file (or output folder, in batch mode)")
    parser.add_argument("-w", "--width", type=int,
                        help="width of the output in characters")
    parser.add_argument("-c", "--chars", default=DEFAULT_CHARS,
                        help="characters to be used for the ASCII image")
    parser.add_argument("-g", "--grayscale", action="store_true",
                        help="plain text output with no color")
    parser.add_argument("-p", "--print", dest="print_output", action="store_true",
                        help="print the output to the console")
    parser.add_argument("-r", "--reverse", action="store_true",
                        help="reverse the string of characters")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="print some useful information")

    args = parser.parse_args()

    if not args.chars:
        sys.exit("Error: --chars must not be empty")

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Error: no such file or folder: {input_path}")

    output_path = Path(args.output) if args.output else None
    # Match the C tool: with no output file, print to the console automatically.
    print_output = args.print_output or output_path is None

    # --- Batch mode: the input is a folder ---
    if input_path.is_dir():
        images = sorted(
            p for p in input_path.iterdir()
            if p.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not images:
            sys.exit(f"Error: no images found in {input_path}")

        for image_path in images:
            print(f"\n=== {image_path.name} ===", file=sys.stderr)
            target = (output_path / f"{image_path.stem}.txt") if output_path else None
            convert(
                image_path, target, args.chars, args.width,
                args.grayscale, args.reverse, print_output, args.debug,
            )
        return

    # --- Single file ---
    convert(
        input_path, output_path, args.chars, args.width,
        args.grayscale, args.reverse, print_output, args.debug,
    )


if __name__ == "__main__":
    main()
