#!/usr/bin/env python3
"""
fit_avatar.py - Fit an image to the WorkBuddy expert-avatar spec.

Avatar rule (references/avatar-spec.md in skill-expert-manager):
    PNG/JPG, 512x512 px, single file <= 500 KB.

AI-generated avatars come back from ImageGen at 1024x1024 and ~1.6 MB, so this
script makes them compliant in one call:
    1. caps the longest side at 512 px (avatars must display 512x512), and
    2. shrinks until the file is <= 500 KB (default), using the pure-stdlib
       fit loop from fit_image.py.

Delegates to resize_png + fit_image in the same scripts/ folder.
Pure standard library only. Supports 8-bit RGB(2) / RGBA(6) PNGs.

Usage:
    python3 fit_avatar.py avatars/expert.png
    python3 fit_avatar.py avatars/expert.png --max-mb 0.5 --maxdim 512
    python3 fit_avatar.py big.png --output avatars/expert.png
"""
import os
import sys
import argparse
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resize_png
import fit_image


def fit_avatar(input_path, max_mb=0.5, maxdim=512, output_path=None, verbose=True):
    """Make input_path satisfy the avatar spec (<= maxdim px, <= max_mb MB).
    Writes to output_path if given, otherwise in place. Returns the maxdim used
    or None if already compliant."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    target = output_path or input_path
    max_bytes = max_mb * 1024 * 1024

    # Step 1: cap the longest side at maxdim (display rule is 512x512).
    w, h, *_ = resize_png.read_png(input_path)
    dim_capped = None
    if max(w, h) > maxdim:
        dim_capped = input_path + ".av_dim_tmp.png"
        resize_png.resize(input_path, dim_capped, maxdim=maxdim)
        source = dim_capped
    else:
        source = input_path

    # Step 2: shrink until under the byte limit.
    used = fit_image.fit(source, max_bytes, start_maxdim=maxdim,
                         output_path=target, verbose=verbose)

    # fit() returns None (no change) when source is already under the limit, but
    # it never copies a temp/dim-capped source into target. Do that here.
    if used is None and source != target and os.path.exists(source):
        shutil.copyfile(source, target)
        if verbose:
            print("copied dim-capped source -> %s (already under limit)" % target)

    if dim_capped and os.path.exists(dim_capped):
        os.remove(dim_capped)

    if verbose and used is not None:
        print("avatar spec met: %s = %d KB, longest side <= %d" % (
            target, os.path.getsize(target) // 1024, maxdim))
    return used


def main():
    ap = argparse.ArgumentParser(description="Fit a PNG to the expert-avatar spec")
    ap.add_argument("input", help="source PNG path")
    ap.add_argument("--max-mb", type=float, default=0.5,
                    help="max file size in MB (default 0.5 = avatar rule)")
    ap.add_argument("--maxdim", type=int, default=512,
                    help="max longest side in px (default 512 = avatar rule)")
    ap.add_argument("--output", default=None,
                    help="output path (default: overwrite input in place)")
    args = ap.parse_args()
    fit_avatar(args.input, args.max_mb, args.maxdim, args.output)


if __name__ == "__main__":
    main()
