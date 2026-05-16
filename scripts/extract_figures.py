#!/usr/bin/env python3
"""Extract figures from academic papers.

Supports two modes:
1. arxiv source mode: download LaTeX source, extract original figure files
2. PDF rendering mode: render specific pages as PNG (fallback)
3. compose mode: combine related subfigures into one SVG group

Usage:
    # arxiv source mode (preferred)
    python extract_figures.py --arxiv <arxiv_id> <output_dir>

    # PDF page rendering mode (last-resort fallback)
    python extract_figures.py --pdf <pdf_path> <output_dir> --pages 3 5

    # grouped subfigures, preserving the paper's row/grid layout
    python extract_figures.py <output_dir> --compose "fig3_group:row:a.svg,b.svg,c.svg"
"""

import sys
import os
import base64
import math
import re
import subprocess
import shutil
import tarfile
import tempfile
import argparse
import gzip
from xml.sax.saxutils import escape

MAX_WIDTH = 1200  # max image width in pixels for PDF fallback modes
SOURCE_PDF_DPI = 600  # high-DPI fallback when source vector conversion is unavailable


def resize_image(path: str, max_width: int = MAX_WIDTH):
    """Resize image to max_width if wider, using Pillow LANCZOS."""
    if not max_width or max_width <= 0:
        return
    try:
        from PIL import Image
        img = Image.open(path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            img.save(path, optimize=True)
    except ImportError:
        pass  # Pillow not available, skip resize


def _sanitize_filename(name: str) -> str:
    """Return a filesystem-safe filename stem while keeping it recognizable."""
    name = re.sub(r"[\\/]+", "_", name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name.strip("._-") or "figure"


def _unique_output_name(preferred_stem: str, ext: str, used_names: set[str]) -> str:
    """Avoid overwriting different source figures that share the same basename."""
    stem = _sanitize_filename(preferred_stem)
    ext = ext.lower()
    candidate = f"{stem}{ext}"
    i = 2
    while candidate in used_names:
        candidate = f"{stem}_{i}{ext}"
        i += 1
    used_names.add(candidate)
    return candidate


def _unpack_arxiv_source(source_path: str, tmpdir: str) -> str | None:
    """Unpack an arXiv e-print payload.

    Most arXiv sources are tarballs, but some older e-prints are a single
    gzipped TeX file. Handling both keeps arXiv notes source-first instead of
    silently falling back to blurry PDF page crops.
    """
    source_dir = os.path.join(tmpdir, "source")
    os.makedirs(source_dir, exist_ok=True)

    try:
        with tarfile.open(source_path) as tar:
            try:
                tar.extractall(source_dir, filter="data")
            except TypeError:
                tar.extractall(source_dir)
        return source_dir
    except tarfile.TarError:
        pass

    raw = None
    try:
        with gzip.open(source_path, "rb") as f:
            raw = f.read()
    except OSError:
        try:
            with open(source_path, "rb") as f:
                raw = f.read()
        except OSError:
            raw = None

    if not raw:
        return None
    if raw.lstrip().lower().startswith((b"<html", b"<!doctype html")):
        return None

    with open(os.path.join(source_dir, "source.tex"), "wb") as f:
        f.write(raw)
    return source_dir


def _copy_or_convert_pdf_figure(
    src_path: str,
    output_dir: str,
    base: str,
    used_names: set[str],
    has_pdf2svg: bool,
    has_pymupdf: bool,
    dpi: int = SOURCE_PDF_DPI,
) -> tuple[str, str] | None:
    """Convert a source figure PDF to SVG when possible, otherwise high-DPI PNG."""
    if has_pdf2svg:
        dst_name = _unique_output_name(base, ".svg", used_names)
        dst_path = os.path.join(output_dir, dst_name)
        result = subprocess.run(["pdf2svg", src_path, dst_path], capture_output=True)
        svg_size = os.path.getsize(dst_path) if os.path.exists(dst_path) else 0
        if result.returncode == 0 and svg_size > 0:
            return dst_name, dst_path
        if os.path.exists(dst_path):
            os.remove(dst_path)
        used_names.discard(dst_name)

    if not has_pymupdf:
        return None

    import pymupdf

    dst_name = _unique_output_name(base, ".png", used_names)
    dst_path = os.path.join(output_dir, dst_name)
    doc = pymupdf.open(src_path)
    page = doc[0]
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pix.save(dst_path)
    doc.close()
    return dst_name, dst_path


def _convert_eps_figure(
    src_path: str,
    output_dir: str,
    base: str,
    used_names: set[str],
    has_pdf2svg: bool,
    has_pymupdf: bool,
    dpi: int = SOURCE_PDF_DPI,
) -> tuple[str, str] | None:
    """Convert a source EPS figure without falling back to full-paper crops."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, f"{_sanitize_filename(base)}.pdf")
        if shutil.which("epstopdf"):
            result = subprocess.run(["epstopdf", src_path, f"--outfile={pdf_path}"], capture_output=True)
            if result.returncode == 0 and os.path.exists(pdf_path):
                return _copy_or_convert_pdf_figure(
                    pdf_path, output_dir, base, used_names, has_pdf2svg, has_pymupdf, dpi=dpi
                )

        magick = shutil.which("magick") or shutil.which("convert")
        if magick:
            dst_name = _unique_output_name(base, ".png", used_names)
            dst_path = os.path.join(output_dir, dst_name)
            cmd = [magick]
            if os.path.basename(magick) == "magick":
                cmd += ["convert"]
            cmd += ["-density", str(dpi), src_path, "-background", "white", "-alpha", "remove", dst_path]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0 and os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
                return dst_name, dst_path
            if os.path.exists(dst_path):
                os.remove(dst_path)
            used_names.discard(dst_name)

    return None


def trim_whitespace(path: str, threshold: int = 245, pad: int = 24) -> bool:
    """Trim near-white margins from a bitmap figure in-place.

    Returns True when the image was cropped. SVG/PDF files are intentionally
    ignored; use source-aware cropping or compose mode for vector figures.
    """
    if os.path.splitext(path)[1].lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return False
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return False

    img = Image.open(path)
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        rgb = bg.convert("RGB")
    else:
        rgb = img.convert("RGB")

    white = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, white)
    r, g, b = diff.split()
    max_diff = ImageChops.lighter(ImageChops.lighter(r, g), b)
    tolerance = max(0, 255 - threshold)
    mask = max_diff.point(lambda v: 255 if v > tolerance else 0)
    bbox = mask.getbbox()
    if not bbox:
        return False

    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(rgb.width, x1 + pad)
    y1 = min(rgb.height, y1 + pad)
    new_w, new_h = x1 - x0, y1 - y0
    if new_w >= rgb.width * 0.98 and new_h >= rgb.height * 0.98:
        return False

    cropped = rgb.crop((x0, y0, x1, y1))
    cropped.save(path, optimize=True)
    print(f"  trimmed {os.path.basename(path)}: {rgb.width}x{rgb.height} -> {new_w}x{new_h}")
    return True


def trim_output_dir_images(output_dir: str, threshold: int = 245, pad: int = 24) -> int:
    """Trim near-white margins for all bitmap figures under output_dir."""
    count = 0
    for root, _, files in os.walk(output_dir):
        for filename in files:
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                if trim_whitespace(os.path.join(root, filename), threshold=threshold, pad=pad):
                    count += 1
    print(f"\nTrimmed whitespace in {count} bitmap figures under {output_dir}")
    return count


def extract_from_arxiv_source(
    arxiv_id: str,
    output_dir: str,
    source_dpi: int = SOURCE_PDF_DPI,
    resize_source: bool = False,
    max_width: int = MAX_WIDTH,
):
    """Download arXiv LaTeX source and extract original figure files.

    Source mode intentionally preserves original raster dimensions and prefers
    vector SVG for source PDFs. PDF-page crops are a separate fallback mode and
    are never used implicitly here.
    """
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        source_payload = os.path.join(tmpdir, "source.eprint")

        # Download source
        url = f"https://arxiv.org/e-print/{arxiv_id}"
        result = subprocess.run(
            [
                "curl", "-fL", "--retry", "3", "--connect-timeout", "20",
                "--max-time", "180", "-A", "paper-to-note/1.0",
                "-o", source_payload, url,
            ],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not os.path.exists(source_payload) or os.path.getsize(source_payload) < 100:
            stderr = result.stderr.strip()
            print(f"ERROR: Failed to download arXiv source {url}" + (f": {stderr}" if stderr else ""))
            return []

        source_dir = _unpack_arxiv_source(source_payload, tmpdir)
        if not source_dir:
            print(f"ERROR: Downloaded arXiv source payload could not be unpacked: {url}")
            return []

        # Find image files
        image_exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
        figures = []
        for root, dirs, files in os.walk(source_dir):
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in image_exts:
                    src_path = os.path.join(root, f)
                    # Skip tiny files (icons, logos)
                    if os.path.getsize(src_path) < 5000:
                        continue
                    figures.append((src_path, os.path.relpath(src_path, source_dir)))

        # Convert and copy to output
        results = []
        try:
            import pymupdf
            has_pymupdf = True
        except ImportError:
            has_pymupdf = False

        has_pdf2svg = shutil.which("pdf2svg") is not None
        used_names: set[str] = set()

        print(f"Extracting original figures from arXiv LaTeX source for {arxiv_id}")
        for src_path, rel_name in figures:
            base = os.path.splitext(rel_name)[0]
            ext = os.path.splitext(rel_name)[1].lower()

            if ext in (".png", ".jpg", ".jpeg"):
                # Preserve the original source raster bytes by default. Do not
                # downsample high-resolution arXiv assets unless explicitly
                # requested with --resize-source.
                dst_name = _unique_output_name(base, ext, used_names)
                dst_path = os.path.join(output_dir, dst_name)
                shutil.copy2(src_path, dst_path)
                if resize_source:
                    resize_image(dst_path, max_width=max_width)
            elif ext == ".svg":
                dst_name = _unique_output_name(base, ".svg", used_names)
                dst_path = os.path.join(output_dir, dst_name)
                shutil.copy2(src_path, dst_path)
            elif ext == ".pdf":
                converted = _copy_or_convert_pdf_figure(
                    src_path, output_dir, base, used_names, has_pdf2svg, has_pymupdf, dpi=source_dpi
                )
                if not converted:
                    continue
                dst_name, dst_path = converted
            elif ext == ".eps":
                converted = _convert_eps_figure(
                    src_path, output_dir, base, used_names, has_pdf2svg, has_pymupdf, dpi=source_dpi
                )
                if not converted:
                    continue
                dst_name, dst_path = converted
            else:
                continue
            size_kb = os.path.getsize(dst_path) // 1024
            results.append({"filename": dst_name, "size_kb": size_kb})
            marker = "source"
            if ext == ".pdf" and dst_name.endswith(".svg"):
                marker = "source vector"
            elif ext in (".pdf", ".eps"):
                marker = f"source high-DPI {source_dpi}"
            print(f"  {dst_name}: {size_kb}KB ({marker})")

        print(f"\nExtracted {len(results)} figures to {output_dir}")
        return results


def crop_pdf_figures(pdf_path: str, output_dir: str, figures: list[str], dpi: int = 300):
    """Crop individual figures from PDF pages.

    Each figure spec: "name:page:x0,y0,x1,y1"
    - name: output filename (without extension)
    - page: 1-indexed page number
    - x0,y0,x1,y1: crop rectangle in PDF points (612x792 for letter)

    Example: "fig1_overview:5:72,48,540,260"
    """
    import pymupdf

    os.makedirs(output_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)

    results = []
    for spec in figures:
        parts = spec.split(":")
        if len(parts) != 3:
            print(f"  SKIP invalid spec: {spec} (expected name:page:x0,y0,x1,y1)")
            continue
        name = parts[0]
        try:
            page_num = int(parts[1])
            coords = [float(c) for c in parts[2].split(",")]
        except (ValueError, IndexError):
            print(f"  SKIP invalid spec: {spec}")
            continue
        if len(coords) != 4:
            print(f"  SKIP invalid coords: {spec}")
            continue
        if page_num < 1 or page_num > total_pages:
            print(f"  SKIP page {page_num} out of range (1-{total_pages})")
            continue

        x0, y0, x1, y1 = coords
        page = doc[page_num - 1]
        clip = pymupdf.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        filename = f"{name}.png"
        filepath = os.path.join(output_dir, filename)
        pix.save(filepath)
        size_kb = os.path.getsize(filepath) // 1024
        results.append({"filename": filename, "page": page_num, "size_kb": size_kb})
        print(f"  {filename}: {pix.width}x{pix.height}, {size_kb}KB")

    doc.close()
    print(f"\nCropped {len(results)} figures to {output_dir}")
    return results


def render_pdf_pages(pdf_path: str, output_dir: str, pages: list[int] | None = None, dpi: int = 200):
    """Render specific PDF pages as PNG images (last resort fallback).

    WARNING: Prefer --crop mode for individual figures. Full-page rendering
    produces page_N.png files that include surrounding text and look unprofessional.
    """
    import pymupdf

    os.makedirs(output_dir, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)

    if pages is None:
        pages = list(range(1, min(21, total_pages + 1)))

    results = []
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)

    for page_num in pages:
        if page_num < 1 or page_num > total_pages:
            continue
        page = doc[page_num - 1]
        images = page.get_images(full=True)
        drawings = page.get_drawings()
        if not images and len(drawings) <= 10:
            continue

        pix = page.get_pixmap(matrix=mat)
        filename = f"page_{page_num}.png"
        filepath = os.path.join(output_dir, filename)
        pix.save(filepath)
        resize_image(filepath)
        size_kb = os.path.getsize(filepath) // 1024
        results.append({"filename": filename, "page": page_num, "size_kb": size_kb})
        print(f"  {filename}: {size_kb}KB")

    doc.close()
    print(f"\nRendered {len(results)} pages to {output_dir}")
    return results


def _parse_svg_length(value: str | None) -> float | None:
    """Parse SVG length attributes into CSS pixels."""
    if not value:
        return None
    match = re.match(r"\s*([0-9.]+)\s*([a-zA-Z%]*)", value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("", "px"):
        return number
    if unit == "pt":
        return number * 96 / 72
    if unit == "in":
        return number * 96
    if unit == "cm":
        return number * 96 / 2.54
    if unit == "mm":
        return number * 96 / 25.4
    return None


def _image_dimensions(path: str) -> tuple[float, float]:
    """Return image dimensions for SVG/raster inputs; fallback to a 4:3 panel."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        text = open(path, "r", encoding="utf-8", errors="ignore").read(4096)
        viewbox = re.search(r'viewBox=["\']\s*([-0-9.]+)\s+([-0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*["\']', text)
        if viewbox:
            return float(viewbox.group(3)), float(viewbox.group(4))
        width = re.search(r'\bwidth=["\']([^"\']+)["\']', text)
        height = re.search(r'\bheight=["\']([^"\']+)["\']', text)
        w = _parse_svg_length(width.group(1) if width else None)
        h = _parse_svg_length(height.group(1) if height else None)
        if w and h:
            return w, h
    try:
        from PIL import Image
        with Image.open(path) as img:
            return float(img.width), float(img.height)
    except Exception:
        return 400.0, 300.0


def _mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")


def compose_grouped_figures(output_dir: str, specs: list[str], gap: int = 24, cell_width: int = 420):
    """Compose subfigure panels into one SVG.

    Spec format: "output_name:layout:image1,image2,image3"
    Layout: row/horizontal, column/vertical, or NxM such as 2x2 / 3x1.
    Image paths are relative to output_dir unless absolute.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for spec in specs:
        try:
            output_name, layout, image_list = spec.split(":", 2)
        except ValueError:
            print(f"WARNING: skip invalid compose spec: {spec}", file=sys.stderr)
            continue

        image_paths = []
        for name in [x.strip() for x in image_list.split(",") if x.strip()]:
            path = name if os.path.isabs(name) else os.path.join(output_dir, name)
            if not os.path.exists(path):
                print(f"WARNING: compose input not found: {path}", file=sys.stderr)
                continue
            image_paths.append(path)
        if not image_paths:
            continue

        layout = layout.lower()
        if layout in ("row", "horizontal"):
            cols = len(image_paths)
        elif layout in ("column", "col", "vertical"):
            cols = 1
        elif "x" in layout:
            left, _right = layout.split("x", 1)
            cols = max(1, int(left))
        else:
            cols = max(1, math.ceil(math.sqrt(len(image_paths))))

        panels = []
        for path in image_paths:
            w, h = _image_dimensions(path)
            scale = cell_width / max(w, 1.0)
            panels.append({
                "path": path,
                "width": cell_width,
                "height": max(1, h * scale),
                "data": base64.b64encode(open(path, "rb").read()).decode("ascii"),
                "mime": _mime_type(path),
            })

        rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
        row_heights = [max(p["height"] for p in row) for row in rows]
        total_width = max(sum(p["width"] for p in row) + gap * (len(row) - 1) for row in rows)
        total_height = sum(row_heights) + gap * (len(rows) - 1)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width:.0f}" height="{total_height:.0f}" viewBox="0 0 {total_width:.0f} {total_height:.0f}">'
        ]
        y = 0.0
        for row, row_height in zip(rows, row_heights):
            x = 0.0
            for panel in row:
                href = f"data:{panel['mime']};base64,{panel['data']}"
                title = escape(os.path.basename(panel["path"]))
                y_offset = y + (row_height - panel["height"]) / 2
                svg_parts.append(
                    f'<image x="{x:.0f}" y="{y_offset:.0f}" width="{panel["width"]:.0f}" height="{panel["height"]:.0f}" href="{href}" preserveAspectRatio="xMidYMid meet"><title>{title}</title></image>'
                )
                x += panel["width"] + gap
            y += row_height + gap
        svg_parts.append("</svg>\n")

        if not os.path.splitext(output_name)[1]:
            output_name += ".svg"
        output_path = output_name if os.path.isabs(output_name) else os.path.join(output_dir, output_name)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(svg_parts))
        results.append(output_path)
        print(f"Composed grouped figure: {output_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract figures from papers")
    parser.add_argument("--arxiv", type=str, help="arxiv paper ID (e.g. 2603.04379)")
    parser.add_argument("--pdf", type=str, help="PDF file path")
    parser.add_argument("--crop", action="store_true",
                        help="Crop individual figures instead of full pages")
    parser.add_argument("output_dir", type=str, help="Output directory for figures")
    parser.add_argument("--figures", nargs="+", type=str,
                        help="Figure specs for crop mode: name:page:x0,y0,x1,y1")
    parser.add_argument("--pages", nargs="+", type=int,
                        help="Page numbers for PDF full-page mode")
    parser.add_argument("--compose", nargs="+", type=str,
                        help="Compose grouped subfigures: output:layout:image1,image2,... (layout row, column, or NxM)")
    parser.add_argument("--trim", action="store_true",
                        help="Trim near-white margins from bitmap figures in output_dir after extraction/compose")
    parser.add_argument("--trim-threshold", type=int, default=245,
                        help="Near-white threshold for --trim (default: 245)")
    parser.add_argument("--trim-pad", type=int, default=24,
                        help="Padding in pixels kept around detected content for --trim (default: 24)")
    parser.add_argument("--source-dpi", type=int, default=SOURCE_PDF_DPI,
                        help=f"DPI for arXiv source PDF/EPS fallback rasterization (default: {SOURCE_PDF_DPI})")
    parser.add_argument("--resize-source", action="store_true",
                        help="Downscale arXiv source raster images to --max-width (off by default; preserves source quality)")
    parser.add_argument("--max-width", type=int, default=MAX_WIDTH,
                        help=f"Max width for PDF fallback rendering and optional --resize-source (default: {MAX_WIDTH}; use 0 to disable)")
    args = parser.parse_args()

    if args.arxiv:
        extract_from_arxiv_source(
            args.arxiv,
            args.output_dir,
            source_dpi=args.source_dpi,
            resize_source=args.resize_source,
            max_width=args.max_width,
        )
    elif args.pdf and args.crop:
        if not args.figures:
            print("ERROR: --crop requires --figures specs")
            sys.exit(1)
        crop_pdf_figures(args.pdf, args.output_dir, args.figures)
    elif args.pdf:
        render_pdf_pages(args.pdf, args.output_dir, getattr(args, 'pages', None))
    elif args.compose:
        pass
    elif args.trim:
        pass
    else:
        print("ERROR: Specify --arxiv <id>, --pdf <path>, --compose, or --trim")
        sys.exit(1)

    if args.compose:
        compose_grouped_figures(args.output_dir, args.compose)

    if args.trim:
        trim_output_dir_images(args.output_dir, threshold=args.trim_threshold, pad=args.trim_pad)
