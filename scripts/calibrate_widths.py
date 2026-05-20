#!/usr/bin/env python3
"""Batch-calibrate figure embeds across the paper-to-note Obsidian vault.

Two correctness passes are bundled into a single dry-runnable tool:

1. **Width calibration** (default): walks every Markdown file under
   `<vault>/notes/`, resolves each `<img src="...">` (and Obsidian
   `![[name|N]]`) to its on-disk asset under `<vault>/files/...`,
   recomputes the per-figure recommended width via
   `extract_figures.recommend_width`, and reports / rewrites embeds
   whose current width differs from the recommendation by more than
   `--tolerance`.

2. **Center wrapping** (`--auto-center`): bare `<img>` tags render
   left-aligned in Obsidian/GitHub. With this flag, every standalone
   `<img>` line that is NOT already inside a `<div align="center">` /
   `<p align="center">` / `<center>` container is wrapped on its own
   block:

       <div align="center">
         <img src="..." alt="..." width="N">
       </div>

   `<img>` tags that share a line with other text are surfaced as
   `skip-inline-img` instead of being rewritten, since wrapping them
   would split the line into a broken HTML block. Obsidian
   `![[name|N]]` embeds are skipped (different rendering pipeline).

Default behavior is dry-run: nothing is written. Pass `--apply` to
rewrite notes in place. With `--apply`, every modified note's original
content is first copied to a timestamped backup directory outside the
vault, so a regression can be undone without touching git history.

Why a single script: we want a single auditable pass over the whole
vault that respects the same `recommend_width` and centering policies
used at note creation time, so older notes that were written with the
old hard-coded `width="1000"` and bare `<img>` tags get the same
treatment as new notes.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import extract_figures as ef  # noqa: E402

DEFAULT_VAULT = Path(
    "/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes"
)

# Match any `<img src="...">` tag, regardless of whether `width` is
# present and regardless of whether it is given in pixels or as a
# percentage. Width is parsed separately so this single regex can drive
# both width calibration (px only) and centering (any width form).
IMG_TAG_RE = re.compile(
    r'<img\b[^>]*?\bsrc\s*=\s*"(?P<src>[^"]+)"[^>]*>',
    re.IGNORECASE,
)
WIDTH_PX_RE = re.compile(r'\bwidth\s*=\s*"(?P<width>\d+)"', re.IGNORECASE)
OBSIDIAN_EMBED_RE = re.compile(
    r"!\[\[(?P<target>[^\]|]+)\|(?P<spec>[^\]]+)\]\]",
)
OBSIDIAN_WIDTH_ONLY_RE = re.compile(r"^\s*(?P<w>\d+)\s*$")
OBSIDIAN_WIDTH_HEIGHT_RE = re.compile(
    r"^\s*(?P<w>\d+)\s*[xX×]\s*(?P<h>\d+)\s*$"
)
ASSET_EXTS = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")

# Detect a center-aligning HTML container around an <img>. Both attribute
# orderings (`<div align="center">` and `<div style="text-align:center">`)
# are treated as already-centered because they all render the same way in
# Obsidian / GitHub / VS Code preview.
CENTER_OPEN_RE = re.compile(
    r'<\s*(?:div|p)\b[^>]*\b(?:align\s*=\s*["\']?center["\']?'
    r'|style\s*=\s*["\'][^"\']*text-align\s*:\s*center)[^>]*>'
    r'|<\s*center\b[^>]*>',
    re.IGNORECASE,
)
CENTER_CLOSE_RE = re.compile(r'</\s*(?:div|p|center)\s*>', re.IGNORECASE)
HTML_FILLER_RE = re.compile(
    r'<\s*br\s*/?\s*>|&nbsp;|&emsp;|&ensp;|&thinsp;', re.IGNORECASE,
)


def is_pure_embed_line(line: str) -> bool:
    """True iff `line` contains only `<img>` tags / `![[...]]` embeds +
    whitespace / `<br>` / nbsp.

    Used to decide whether a multi-embed line (e.g. side-by-side
    comparison strips like `<img a> <img b>` or `![[a]] ![[b]]`) can
    be safely wrapped as a single `<div align="center">...</div>`
    block.
    """
    stripped = IMG_TAG_RE.sub('', line)
    stripped = OBSIDIAN_EMBED_RE.sub('', stripped)
    stripped = HTML_FILLER_RE.sub('', stripped)
    return stripped.strip() == ''


@dataclass
class Embed:
    note: Path
    line: int
    kind: str            # "img" or "embed"
    raw: str             # original matched substring
    src: str             # raw src as written in the note (may be url-encoded)
    asset: Path | None   # resolved on-disk path or None if missing
    current_width: int
    recommended_width: int | None
    note_action: str     # width calibration: "calibrate", "skip-tolerance",
                         # "skip-no-asset", "skip-remote", "skip-shape-spec"
    is_centered: bool = False
    center_action: str = ""  # "wrap" (single-img line, multi-line block),
                             # "wrap-line" (multi-img pure line, inline block),
                             # "skip-already-centered",
                             # "skip-not-applicable" (obsidian embed),
                             # "skip-shared-line" (other img on same wrap-line),
                             # "skip-inline-img" (img mixed with prose),
                             # "" (centering disabled)
    line_text: str = ""  # full line content (used to verify wrap safety)


def find_vault_files_root(vault: Path) -> Path:
    files_root = vault / "files"
    if not files_root.is_dir():
        raise SystemExit(f"vault has no files/ directory: {files_root}")
    return files_root


def resolve_relative_src(note_path: Path, src: str, vault: Path) -> Path | None:
    """Resolve an `<img src="...">` value to a real path inside the vault.

    The skill writes embeds with `<img src="../../../files/.../fig.svg">`,
    relative to the note's directory. Some older notes use vault-relative
    `files/.../fig.svg` (no leading `..`), absolute paths, URL-encoded
    characters, or HTML-entity-escaped `&amp;` in category names like
    `LLM &amp; VLM`. Handle the common shapes and bail out for remote URLs.
    """
    if src.startswith(("http://", "https://", "data:")):
        return None
    decoded = html.unescape(urllib.parse.unquote(src))

    candidate = (note_path.parent / decoded).resolve()
    if candidate.exists():
        return candidate

    if decoded.startswith("/"):
        candidate = (vault / decoded.lstrip("/")).resolve()
        if candidate.exists():
            return candidate

    # Some older notes wrote vault-relative paths like `files/<Top>/<Sub>/...`
    # without the `../../../` prefix; treat those as relative to the vault.
    if decoded.startswith("files/") or decoded.startswith("./files/"):
        candidate = (vault / decoded.lstrip("./")).resolve()
        if candidate.exists():
            return candidate

    return None


def find_obsidian_target(name: str, files_root: Path) -> Path | None:
    """Locate an Obsidian `![[name]]` target under <vault>/files/.

    Obsidian resolves `![[name]]` against vault-wide attachments; for the
    paper-to-note layout these live under `files/<TopCategory>/...`. We
    walk a small index of basenames so this stays linear in vault size
    rather than quadratic per match.
    """
    target = name.strip()
    target_basename = os.path.basename(target)
    if not target_basename:
        return None
    matches = list(files_root.rglob(target_basename))
    if not matches:
        return None
    # Prefer the shortest path (closest to vault root) when there are dups.
    matches.sort(key=lambda p: len(str(p)))
    return matches[0]


def is_already_centered(lines: list[str], img_line_idx: int) -> bool:
    """Check whether the `<img>` on `lines[img_line_idx]` is wrapped in a
    centering container.

    Two shapes are recognised:

    1. **Inline single-line wrap**: the same line contains both an opening
       center tag and its matching close (e.g.
       `<div align="center"><img ...></div>`).
    2. **Multi-line wrap**: the previous non-empty line opens with a
       center tag and the next non-empty line closes with `</div>`,
       `</p>`, or `</center>`.
    """
    if not (0 <= img_line_idx < len(lines)):
        return False
    line = lines[img_line_idx]
    if CENTER_OPEN_RE.search(line) and CENTER_CLOSE_RE.search(line):
        return True
    prev_open = False
    for i in range(img_line_idx - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        prev_open = bool(CENTER_OPEN_RE.search(s))
        break
    next_close = False
    for i in range(img_line_idx + 1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        next_close = bool(CENTER_CLOSE_RE.search(s))
        break
    return prev_open and next_close


def collect_embeds(vault: Path) -> list[Embed]:
    notes_root = vault / "notes"
    files_root = find_vault_files_root(vault)
    if not notes_root.is_dir():
        raise SystemExit(f"vault has no notes/ directory: {notes_root}")

    embeds: list[Embed] = []
    for md_path in sorted(notes_root.rglob("*.md")):
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"[skip] cannot decode: {md_path}", file=sys.stderr)
            continue

        lines = content.splitlines()
        for line_no, line in enumerate(lines, 1):
            for m in IMG_TAG_RE.finditer(line):
                raw = m.group(0)
                src = m.group("src")
                width_match = WIDTH_PX_RE.search(raw)
                if width_match is not None:
                    current_width = int(width_match.group("width"))
                    initial_action = ""
                else:
                    # No `width="N"` (missing entirely) or non-pixel
                    # width like `width="95%"`. Skip width calibration
                    # but still let the embed participate in centering.
                    current_width = -1
                    initial_action = "skip-non-px-width"
                asset = resolve_relative_src(md_path, src, vault)
                embeds.append(Embed(
                    note=md_path, line=line_no, kind="img",
                    raw=raw, src=src, asset=asset,
                    current_width=current_width, recommended_width=None,
                    note_action=initial_action,
                    is_centered=is_already_centered(lines, line_no - 1),
                    line_text=line,
                ))

            for m in OBSIDIAN_EMBED_RE.finditer(line):
                target = m.group("target")
                spec = m.group("spec").strip()
                ext = os.path.splitext(target)[1].lower()
                if ext and ext not in ASSET_EXTS:
                    continue
                width_match = OBSIDIAN_WIDTH_ONLY_RE.match(spec)
                shape_match = OBSIDIAN_WIDTH_HEIGHT_RE.match(spec)
                if width_match:
                    width = int(width_match.group("w"))
                    asset = find_obsidian_target(target, files_root)
                    embeds.append(Embed(
                        note=md_path, line=line_no, kind="embed",
                        raw=m.group(0), src=target, asset=asset,
                        current_width=width, recommended_width=None,
                        note_action="",
                        is_centered=is_already_centered(lines, line_no - 1),
                        line_text=line,
                    ))
                elif shape_match:
                    # Width+height pin: skip; rewriting only width would
                    # leave a stale height. Surface in report but do not
                    # auto-rewrite.
                    width = int(shape_match.group("w"))
                    asset = find_obsidian_target(target, files_root)
                    embeds.append(Embed(
                        note=md_path, line=line_no, kind="embed",
                        raw=m.group(0), src=target, asset=asset,
                        current_width=width, recommended_width=None,
                        note_action="skip-shape-spec",
                        is_centered=is_already_centered(lines, line_no - 1),
                        line_text=line,
                    ))

    return embeds


def annotate(embeds: Iterable[Embed], tolerance: int,
             max_height: int, max_width: int, min_width: int,
             auto_center: bool = False) -> None:
    for e in embeds:
        if e.note_action not in ("skip-shape-spec", "skip-non-px-width"):
            if e.asset is None:
                if e.src.startswith(("http://", "https://", "data:")):
                    e.note_action = "skip-remote"
                else:
                    e.note_action = "skip-no-asset"
            else:
                try:
                    w, h = ef._image_dimensions(str(e.asset))
                except Exception:
                    e.note_action = "skip-no-asset"
                else:
                    rec = ef.recommend_width(
                        w, h,
                        is_hero=ef._is_hero_figure(e.asset.name),
                        max_height=max_height,
                        max_width=max_width,
                        min_width=min_width,
                    )
                    e.recommended_width = rec
                    delta = abs(rec - e.current_width)
                    if delta <= tolerance:
                        e.note_action = "skip-tolerance"
                    else:
                        e.note_action = "calibrate"

    if not auto_center:
        return

    # Both kinds need centering; an Obsidian `![[...]]` embed left-aligns
    # by default in Obsidian/GitHub just like a bare `<img>`. We collect
    # them together so a multi-embed line wraps as one inline block,
    # even when the line mixes `<img>` and `![[...]]`.
    by_line: dict[tuple[Path, int], list[Embed]] = {}
    for e in embeds:
        if e.kind in ("img", "embed"):
            by_line.setdefault((e.note, e.line), []).append(e)

    for e in embeds:
        if e.kind not in ("img", "embed"):
            e.center_action = "skip-not-applicable"
            continue
        if e.is_centered:
            e.center_action = "skip-already-centered"
            continue
        if e.note_action == "skip-shape-spec":
            # Obsidian width+height pin like `![[fig|800x500]]`: leave
            # alone for now; rewriting the surrounding HTML could break
            # the pin's intended display geometry.
            e.center_action = "skip-shape-spec"
            continue

        siblings = by_line.get((e.note, e.line), [e])
        if len(siblings) == 1:
            if e.line_text.strip() == e.raw.strip():
                e.center_action = "wrap"
            else:
                e.center_action = "skip-inline-embed"
            continue

        # Multiple embeds on this line. Only wrap when nothing else
        # lives on the line (typical: side-by-side comparison strips).
        # The first embed in line order is the "primary" wrapper; the
        # rest defer to it so we don't wrap the same line twice.
        if not is_pure_embed_line(e.line_text):
            e.center_action = "skip-inline-embed"
            continue
        primary = siblings[0]
        e.center_action = "wrap-line" if e is primary else "skip-shared-line"


def summarize(embeds: list[Embed], auto_center: bool = False) -> None:
    by_action: dict[str, int] = {}
    by_center: dict[str, int] = {}
    for e in embeds:
        by_action[e.note_action] = by_action.get(e.note_action, 0) + 1
        if e.center_action:
            by_center[e.center_action] = by_center.get(e.center_action, 0) + 1
    affected_notes: set[Path] = set()
    for e in embeds:
        if e.note_action == "calibrate" or e.center_action in ("wrap", "wrap-line"):
            affected_notes.add(e.note)

    print("\n=== Calibration plan ===")
    print(f"  total embeds scanned: {len(embeds)}")
    for k in ("calibrate", "skip-tolerance", "skip-no-asset", "skip-remote",
              "skip-shape-spec", "skip-non-px-width"):
        if k in by_action:
            print(f"  width  {k:18s}: {by_action[k]}")
    if auto_center:
        for k in ("wrap", "wrap-line", "skip-already-centered",
                  "skip-not-applicable", "skip-shared-line",
                  "skip-inline-embed", "skip-shape-spec"):
            if k in by_center:
                print(f"  center {k:18s}: {by_center[k]}")
    print(f"  notes with at least one rewrite: {len(affected_notes)}")
    print()


def _vault_relative(note: Path) -> Path:
    for p in note.parents:
        if p.name == "notes":
            return note.relative_to(p.parent)
    return note


def show_diffs(embeds: list[Embed], limit: int = 40) -> None:
    changes = [e for e in embeds if e.note_action == "calibrate"]
    if not changes:
        print("(no width calibrations needed)\n")
        return
    print(f"=== Width calibrations (showing first {min(limit, len(changes))} of {len(changes)}) ===")
    for e in changes[:limit]:
        asset_name = e.asset.name if e.asset else "(unresolved)"
        print(
            f"  {_vault_relative(e.note)}:{e.line}  "
            f"{asset_name}  "
            f"width {e.current_width} -> {e.recommended_width}"
        )
    if len(changes) > limit:
        print(f"  ... ({len(changes) - limit} more)")
    print()


def show_wraps(embeds: list[Embed], limit: int = 40) -> None:
    wraps = [e for e in embeds if e.center_action in ("wrap", "wrap-line")]
    if not wraps:
        print("(no center wraps needed)\n")
        return
    print(f"=== Center wraps (showing first {min(limit, len(wraps))} of {len(wraps)}) ===")
    for e in wraps[:limit]:
        asset_name = e.asset.name if e.asset else os.path.basename(e.src)
        kind = "line" if e.center_action == "wrap-line" else "img "
        print(f"  [{kind}] {_vault_relative(e.note)}:{e.line}  {asset_name}")
    if len(wraps) > limit:
        print(f"  ... ({len(wraps) - limit} more)")
    print()


def show_problem_embeds(embeds: list[Embed], limit: int = 30,
                        auto_center: bool = False) -> None:
    """List embeds that could not be resolved or had unusable specs.

    These are interesting on their own merits (broken links, leftover
    URLs, width+height pins, inline `<img>` mixed with prose) and worth
    surfacing so the operator knows what the calibrator did NOT touch.
    """
    issues: list[tuple[str, Embed]] = []
    for e in embeds:
        if e.note_action.startswith("skip-") and e.note_action not in (
            "skip-tolerance", "skip-non-px-width",
        ):
            issues.append((f"width:{e.note_action}", e))
        if auto_center and e.center_action in (
            "skip-inline-embed", "skip-shape-spec",
        ):
            issues.append((f"center:{e.center_action}", e))
    if not issues:
        return
    print(f"=== Skipped (showing first {min(limit, len(issues))} of {len(issues)}) ===")
    for tag, e in issues[:limit]:
        print(
            f"  [{tag}] {_vault_relative(e.note)}:{e.line}  "
            f"src={e.src}  width={e.current_width}"
        )
    if len(issues) > limit:
        print(f"  ... ({len(issues) - limit} more)")
    print()


def _calibrate_raw(e: Embed) -> str:
    """Return `e.raw` with its width attribute updated to `e.recommended_width`.

    Returns `e.raw` unchanged when no width calibration is requested.
    """
    if e.note_action != "calibrate":
        return e.raw
    assert e.recommended_width is not None
    if e.kind == "img":
        return re.sub(
            r'(\bwidth\s*=\s*")\d+(")',
            rf'\g<1>{e.recommended_width}\g<2>',
            e.raw, count=1,
        )
    return re.sub(
        r'(\|)\d+(\]\])',
        rf'\g<1>{e.recommended_width}\g<2>',
        e.raw, count=1,
    )


def _build_line_replacements(
    line_embeds: list[Embed],
) -> tuple[str, str] | None:
    """Compute the new full-line text for one affected note line.

    Returns `(original_line, new_line)` if any rewrite is required, or
    `None` when the line is unchanged. Width calibration is applied
    first; the resulting line is then optionally wrapped:

    - `wrap` (single-`<img>` line): block-level multi-line wrap, e.g.
      ``<div align="center">\\n  <img ...>\\n</div>``.
    - `wrap-line` (multi-`<img>` pure line): inline single-line wrap,
      ``<div align="center"><img a> <img b></div>``, so the side-by-side
      layout is preserved.
    """
    if not line_embeds:
        return None
    line_text = line_embeds[0].line_text
    new_line_text = line_text
    for e in line_embeds:
        new_raw = _calibrate_raw(e)
        if new_raw != e.raw:
            new_line_text = new_line_text.replace(e.raw, new_raw, 1)

    indent = new_line_text[: len(new_line_text) - len(new_line_text.lstrip())]
    inner = new_line_text.strip()

    wrap_embed = next(
        (e for e in line_embeds if e.center_action == "wrap"), None,
    )
    wrap_line_embed = next(
        (e for e in line_embeds if e.center_action == "wrap-line"), None,
    )
    if wrap_embed is not None:
        if wrap_embed.kind == "embed":
            # Obsidian `![[...]]` embeds need blank lines inside the
            # `<div>` block, otherwise Obsidian/GitHub treat the wikilink
            # as raw HTML content and skip the link/image rendering.
            new_line_text = (
                f'{indent}<div align="center">\n'
                f'{indent}\n'
                f'{indent}{inner}\n'
                f'{indent}\n'
                f'{indent}</div>'
            )
        else:
            new_line_text = (
                f'{indent}<div align="center">\n'
                f'{indent}  {inner}\n'
                f'{indent}</div>'
            )
    elif wrap_line_embed is not None:
        new_line_text = f'{indent}<div align="center">{inner}</div>'

    if new_line_text == line_text:
        return None
    return line_text, new_line_text


def apply_changes(embeds: list[Embed], backup_root: Path) -> int:
    """Rewrite each affected note in place after backing it up.

    Per-line strategy: every affected line is rebuilt once from its
    current embeds (width calibration + optional center wrap), then the
    note is rewritten by splicing those new lines into place. Bottom-up
    iteration over line numbers keeps the indices valid even when a
    `wrap` action expands a line into a 3-line block. The original
    file is copied to a timestamped backup directory before being
    overwritten so a regression can be undone without git history.
    """
    by_line: dict[tuple[Path, int], list[Embed]] = {}
    for e in embeds:
        if e.note_action == "calibrate" or e.center_action in ("wrap", "wrap-line"):
            by_line.setdefault((e.note, e.line), []).append(e)
    if not by_line:
        print("Nothing to apply.")
        return 0

    by_note: dict[Path, list[tuple[int, str, str]]] = {}
    for (note, line_no), line_embeds in by_line.items():
        rep = _build_line_replacements(line_embeds)
        if rep is None:
            continue
        original_line, new_line = rep
        by_note.setdefault(note, []).append((line_no, original_line, new_line))

    backup_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for note, replacements in by_note.items():
        original = note.read_text(encoding="utf-8")
        trailing_nl = original.endswith("\n")
        lines = original.splitlines()
        # Bottom-up so multi-line wraps don't invalidate earlier indices.
        for line_no, original_line, new_line in sorted(
            replacements, key=lambda x: -x[0],
        ):
            idx = line_no - 1
            if not (0 <= idx < len(lines)):
                continue
            if lines[idx] != original_line:
                continue
            insert = new_line.split("\n")
            lines[idx:idx + 1] = insert
        new_text = "\n".join(lines)
        if trailing_nl and not new_text.endswith("\n"):
            new_text += "\n"
        if new_text == original:
            continue

        rel = _vault_relative(note)
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(note, backup_path)
        note.write_text(new_text, encoding="utf-8")
        written += 1

    print(f"\nApplied rewrites to {written} notes.")
    print(f"Backups: {backup_root}")
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault", type=Path, default=DEFAULT_VAULT,
        help=f"vault root (default: {DEFAULT_VAULT})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Rewrite notes in place. Without this flag the run is dry.",
    )
    parser.add_argument(
        "--auto-center", action="store_true",
        help='Also wrap each bare <img> in `<div align="center">...</div>` '
             "so figures render centered in Obsidian/GitHub. Skipped for "
             "Obsidian `![[...]]` embeds and `<img>` tags that share a "
             "line with other text.",
    )
    parser.add_argument(
        "--tolerance", type=int, default=80,
        help="Skip width calibration when |current - recommended| <= tolerance px (default: 80).",
    )
    parser.add_argument(
        "--rec-max-height", type=int, default=ef.REC_MAX_HEIGHT,
        help=f"Target max rendered height (px) (default: {ef.REC_MAX_HEIGHT}).",
    )
    parser.add_argument(
        "--rec-max-width", type=int, default=ef.REC_MAX_WIDTH,
        help=f"Cap on recommended <img width> (default: {ef.REC_MAX_WIDTH}).",
    )
    parser.add_argument(
        "--rec-min-width", type=int, default=ef.REC_MIN_WIDTH,
        help=f"Floor on recommended <img width> (default: {ef.REC_MIN_WIDTH}).",
    )
    parser.add_argument(
        "--limit-diffs", type=int, default=40,
        help="Max diffs to print in dry-run sample (default: 40).",
    )
    parser.add_argument(
        "--limit-issues", type=int, default=30,
        help="Max skip-* entries to list (default: 30).",
    )
    parser.add_argument(
        "--backup-dir", type=Path, default=None,
        help="Override backup directory (default: ~/.cache/paper_notes_calibration_backup/<ts>).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = args.vault
    if not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 2

    print(f"Vault: {vault}")
    print(f"Recommendation policy: max_height={args.rec_max_height} max_width={args.rec_max_width} min_width={args.rec_min_width} tolerance={args.tolerance} auto_center={args.auto_center}")

    embeds = collect_embeds(vault)
    annotate(
        embeds,
        tolerance=args.tolerance,
        max_height=args.rec_max_height,
        max_width=args.rec_max_width,
        min_width=args.rec_min_width,
        auto_center=args.auto_center,
    )
    summarize(embeds, auto_center=args.auto_center)
    show_diffs(embeds, limit=args.limit_diffs)
    if args.auto_center:
        show_wraps(embeds, limit=args.limit_diffs)
    show_problem_embeds(embeds, limit=args.limit_issues, auto_center=args.auto_center)

    if not args.apply:
        print("Dry-run only. Re-run with --apply to write changes.")
        return 0

    backup_root = args.backup_dir
    if backup_root is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_root = Path.home() / ".cache" / "paper_notes_calibration_backup" / ts
    apply_changes(embeds, backup_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
