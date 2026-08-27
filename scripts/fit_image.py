#!/usr/bin/env python3
"""
fit_image.py - Shrink a PNG until its file size is under a byte limit.

This is the orchestration layer on top of resize_png.py: it checks the current
size, then iteratively downscales (lowering --maxdim) until the result fits
under the limit, or until a minimum dimension is reached.

Pure standard library only (imports resize_png from the same scripts/ folder).

Typical uses:
  - General "image must not exceed 1 MB":
      python3 fit_image.py avatar.png --max-mb 1.0
  - Marketplace / plugin avatar (rule: <= 500 KB, 512x512 display):
      python3 fit_image.py avatar.png --max-mb 0.5 --maxdim-start 512

By default the input file is overwritten in place (the common case when
preparing an avatar inside a package). Pass --output to write elsewhere.
"""
import os
import sys
import argparse

# Allow importing the sibling resize_png module regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resize_png


def fit(input_path, max_bytes, start_maxdim=512, min_maxdim=64,
        output_path=None, verbose=True):
    """Shrink input_path until <= max_bytes. Returns the maxdim actually used,
    or None if no change was needed."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    if os.path.getsize(input_path) <= max_bytes:
        if verbose:
            print("OK: %s already %.1f KB (<= limit)" % (
                input_path, os.path.getsize(input_path) / 1024))
        return None

    target = output_path or input_path
    tmp = input_path + ".fit_tmp.png"
    cur = start_maxdim
    used = cur
    while cur >= min_maxdim:
        try:
            resize_png.resize(input_path, tmp, maxdim=cur)
        except Exception as e:  # noqa: BLE001 - surface a clear message
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError("resize failed at maxdim=%d: %s" % (cur, e))
        used = cur
        sz = os.path.getsize(tmp)
        if verbose:
            print("  maxdim=%d -> %.1f KB" % (cur, sz / 1024))
        if sz <= max_bytes:
            break
        cur = max(min_maxdim, int(cur * 0.8))

    if os.path.exists(tmp):
        os.replace(tmp, target)
    final = os.path.getsize(target)
    if verbose:
        print("done: %s = %.1f KB (maxdim=%d, limit=%.2f MB)" % (
            target, final / 1024, used, max_bytes / (1024 * 1024)))
    return used


def main():
    ap = argparse.ArgumentParser(description="Shrink a PNG to fit a size limit")
    ap.add_argument("input", help="source PNG path")
    ap.add_argument("--max-mb", type=float, default=1.0,
                    help="maximum file size in MB (default 1.0)")
    ap.add_argument("--maxdim-start", type=int, default=512,
                    help="starting longest-side in px (default 512)")
    ap.add_argument("--min-maxdim", type=int, default=64,
                    help="stop downscaling below this longest-side (default 64)")
    ap.add_argument("--output", default=None,
                    help="output path (default: overwrite input in place)")
    args = ap.parse_args()
    fit(args.input, args.max_mb * 1024 * 1024, args.maxdim_start,
        args.min_maxdim, args.output)


if __name__ == "__main__":
    main()
