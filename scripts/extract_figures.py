#!/usr/bin/env python3
"""Extract figures from academic paper PDFs.

Supports two modes:
1. arxiv source mode: download source tarball, extract original figure files
2. PDF rendering mode: render specific pages as PNG (fallback)
3. compose mode: combine related subfigures into one SVG group

Usage:
    # arxiv source mode (preferred)
    python extract_figures.py --arxiv <arxiv_id> <output_dir>

    # PDF page rendering mode (fallback)
    python extract_figures.py --pdf <pdf_path> <output_dir> [page_numbers...]

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
from xml.sax.saxutils import escape

MAX_WIDTH = 1200  # max image width in pixels


def resize_image(path: str, max_width: int = MAX_WIDTH):
    """Resize image to max_width if wider, using Pillow LANCZOS."""
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


def extract_from_arxiv_source(arxiv_id: str, output_dir: str):
    """Download arxiv source tarball and extract original figure files."""
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = os.path.join(tmpdir, "source.tar.gz")

        # Download source
        url = f"https://arxiv.org/e-print/{arxiv_id}"
        result = subprocess.run(
            ["curl", "-sL", "-o", tarball, url],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"ERROR: Failed to download {url}")
            return []

        # Extract tarball
        try:
            with tarfile.open(tarball) as tar:
                tar.extractall(tmpdir, filter="data")
        except Exception:
            try:
                subprocess.run(["tar", "xf", tarball, "-C", tmpdir],
                               capture_output=True)
            except Exception as e:
                print(f"ERROR: Failed to extract tarball: {e}")
                return []

        # Find image files
        image_exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
        figures = []
        for root, dirs, files in os.walk(tmpdir):
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in image_exts:
                    src_path = os.path.join(root, f)
                    # Skip tiny files (icons, logos)
                    if os.path.getsize(src_path) < 5000:
                        continue
                    figures.append((src_path, f))

        # Convert and copy to output
        results = []
        try:
            import pymupdf
            has_pymupdf = True
        except ImportError:
            has_pymupdf = False

        has_pdf2svg = shutil.which("pdf2svg") is not None

        for src_path, original_name in figures:
            base = os.path.splitext(original_name)[0]
            ext = os.path.splitext(original_name)[1].lower()

            if ext in (".png", ".jpg", ".jpeg"):
                dst_name = f"{base}.png"
                dst_path = os.path.join(output_dir, dst_name)
                shutil.copy2(src_path, dst_path)
                resize_image(dst_path)
            elif ext == ".pdf":
                # Try SVG first (vector, lossless zoom)
                if has_pdf2svg:
                    svg_path = os.path.join(output_dir, f"{base}.svg")
                    subprocess.run(["pdf2svg", src_path, svg_path],
                                   capture_output=True)
                    svg_size = os.path.getsize(svg_path) if os.path.exists(svg_path) else 0
                    if svg_size > 2 * 1024 * 1024:  # > 2MB = has embedded rasters
                        os.remove(svg_path)  # SVG too large, fall through to PNG
                    else:
                        dst_name = f"{base}.svg"
                        dst_path = svg_path
                        # skip resize for SVG
                        size_kb = svg_size // 1024
                        results.append({"filename": dst_name, "size_kb": size_kb})
                        print(f"  {dst_name}: {size_kb}KB (vector)")
                        continue

                # Fallback: render PDF → PNG
                if has_pymupdf:
                    dst_name = f"{base}.png"
                    dst_path = os.path.join(output_dir, dst_name)
                    doc = pymupdf.open(src_path)
                    page = doc[0]
                    zoom = 300 / 72
                    mat = pymupdf.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat)
                    pix.save(dst_path)
                    doc.close()
                    resize_image(dst_path)
                else:
                    continue
            else:
                continue
            size_kb = os.path.getsize(dst_path) // 1024
            results.append({"filename": dst_name, "size_kb": size_kb})
            print(f"  {dst_name}: {size_kb}KB")

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
    args = parser.parse_args()

    if args.arxiv:
        extract_from_arxiv_source(args.arxiv, args.output_dir)
    elif args.pdf and args.crop:
        if not args.figures:
            print("ERROR: --crop requires --figures specs")
            sys.exit(1)
        crop_pdf_figures(args.pdf, args.output_dir, args.figures)
    elif args.pdf:
        render_pdf_pages(args.pdf, args.output_dir, getattr(args, 'pages', None))
    elif args.compose:
        pass
    else:
        print("ERROR: Specify --arxiv <id> or --pdf <path>")
        sys.exit(1)

    if args.compose:
        compose_grouped_figures(args.output_dir, args.compose)
