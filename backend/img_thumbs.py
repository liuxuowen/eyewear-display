"""Thumbnail batch generator.

Generates width-constrained thumbnails (default width=300px) for all images
under the original images directory. Thumbnails are written into a sibling
`thumb` subdirectory inside the public images directory so they can be served
with a path pattern like:
    /static/images/thumb/<filename>

Environment variables expected (align with existing deployment):
  IMAGE_SAVE_DIR_ORIG   (optional) original source images directory.
  IMAGE_SAVE_DIR        public processed images directory (already served at /static/images/).

If IMAGE_SAVE_DIR_ORIG is not set, falls back to IMAGE_SAVE_DIR as source.

Usage (Windows PowerShell example):
  python generate_thumbs.py --width 300 --force

Features:
  - Skips non image extensions.
  - Skips existing thumbnail if dimensions already <= target width unless --force.
  - Preserves aspect ratio.
  - Writes thumbnails in PNG for PNG sources, JPEG otherwise (configurable).
  - Logs summary (created / skipped / errors).

Requires Pillow; ensure requirements.txt includes Pillow >= 10.0.0.
"""

from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("[ERROR] Pillow not installed. Please add 'Pillow' to requirements.txt and pip install.")
    sys.exit(1)

SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}

def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SUPPORTED_EXT

def derive_paths() -> Tuple[Path, Path]:
    src = Path(r"C:/Users/liuxu/Downloads/output_images")   # 原始图片目录
    dst = Path(r"C:/Users/liuxu/Downloads/output_images/thumb")   # 缩略图目录

    return src, dst

def make_thumb(src_path: Path, dst_path: Path, width: int, force: bool) -> str:
    try:
        with Image.open(src_path) as im:
            w, h = im.size
            if not force and w <= width:
                return 'skip_small'
            # Keep aspect ratio
            ratio = width / float(w)
            new_h = int(h * ratio)
            im = im.resize((width, new_h), Image.LANCZOS)
            # Decide format
            fmt = 'PNG' if src_path.suffix.lower() == '.png' else 'JPEG'
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            # Pillow: for JPEG must convert RGBA to RGB
            if fmt == 'JPEG' and im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            im.save(dst_path, format=fmt, optimize=True)
            return 'created'
    except Exception as e:  # pragma: no cover
        return f'error:{e}'

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description='Generate width-constrained thumbnails.')
    ap.add_argument('--width', type=int, default=300, help='Target width in pixels (default: 300)')
    ap.add_argument('--force', action='store_true', help='Regenerate even if original width <= target width')
    ap.add_argument('--dry-run', action='store_true', help='Only list actions; do not write files')
    args = ap.parse_args(argv)

    src_root, dst_root = derive_paths()
    if not src_root.exists():
        print(f'[ERROR] Source directory not found: {src_root}')
        return 2
    print(f'[INFO] Source: {src_root}')
    print(f'[INFO] Thumbs: {dst_root}')
    print(f'[INFO] Width : {args.width}  Force: {args.force}  Dry-run: {args.dry_run}')

    created = 0
    skipped = 0
    errors = 0
    small_skipped = 0

    for path in src_root.rglob('*'):
        if not is_image_file(path):
            continue
        rel = path.relative_to(src_root)
        dst_file = dst_root / rel
        try:
            if dst_file.exists() and not args.force:
                skipped += 1
                continue
            if args.dry_run:
                # simulate decision
                with Image.open(path) as im:
                    if im.size[0] <= args.width and not args.force:
                        small_skipped += 1
                    else:
                        created += 1
                continue
            result = make_thumb(path, dst_file, args.width, args.force)
            if result == 'created':
                created += 1
                print(f'[CREATE] {rel} -> {dst_file.relative_to(dst_root)}')
            elif result == 'skip_small':
                small_skipped += 1
            elif result.startswith('error:'):
                errors += 1
                print(f'[ERROR] {rel}: {result}')
        except Exception as e:  # pragma: no cover
            errors += 1
            print(f'[ERROR] {rel}: {e}')

    print('\n[SUMMARY]')
    print(f'  created      : {created}')
    print(f'  skipped exist: {skipped}')
    print(f'  skipped small: {small_skipped}')
    print(f'  errors       : {errors}')
    return 0 if errors == 0 else 1

if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
