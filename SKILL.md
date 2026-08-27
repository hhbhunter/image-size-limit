---
name: image-size-limit
description: "Shrink an image (PNG) so its file size fits under a hard limit when no imaging library is available. Use this skill when an image exceeds an upload or packaging size cap (e.g. 图片不能超过 1M, marketplace avatar at or below 500 KB), especially AI-generated avatars that arrive at 1024x1024 and about 1.6 MB. It uses a pure-stdlib PNG downscaler plus an auto-iterate fit-to-limit loop. Trigger on phrases like 'compress image', '图片不能超过 1M', '头像太大', 'shrink png', or any task that must meet a byte or size constraint before upload or packaging."
agent_created: true
---

# Image Size Limit

## Overview

Enforce a maximum file size on an image without third-party tools. The host
sandbox here has no Pillow / ImageMagick / ffmpeg, and PowerShell COM is often
blocked — so this skill relies purely on the Python standard library
(`zlib` + `struct`) to decode, average-downsample, and re-encode a PNG.

It bundles three scripts:
- `scripts/resize_png.py` — pure-stdlib PNG downscaler (8-bit RGB / RGBA).
- `scripts/fit_image.py` — orchestrator that checks the size and iteratively
  downscales until the result is under the limit.
- `scripts/fit_avatar.py` — one-call avatar fitter: caps the longest side at
  512 px **and** shrinks to <= 500 KB, for the WorkBuddy expert-avatar spec.

This is complementary to the lower-level `png-stdlib-resize` skill: that one
exposes the resize primitive; this one wraps it with the "meet a size cap"
workflow, default limits, and the Windows path pitfall below.

## When to use

- An image must not exceed a byte limit before upload / sharing / packaging
  (common rule: **图片不能超过 1M**; marketplace / plugin avatars: **<= 500 KB**).
- An AI-generated avatar comes back at 1024x1024 and ~1.6 MB and must shrink.
- No imaging library is installed and you cannot `pip install` one.

Only 8-bit RGB(2) / RGBA(6) PNGs are supported. For JPG/WebP/GIF, convert or
re-export from the source first; this skill handles the PNG path.

## How to use

### 0. Expert avatar (recommended for expert creation)

When creating a WorkBuddy expert, the avatar comes from ImageGen at 1024x1024
and ~1.6 MB. After generating + renaming it (e.g. `avatars/expert.png`), run:

```bash
python3 scripts/fit_avatar.py avatars/expert.png
# -> caps longest side at 512, shrinks to <= 500 KB, in place
```

This is wired into `skill-expert-manager`'s avatar flow (see its
`references/avatar-spec.md`), so every expert avatar auto-passes the spec.
Pass `--output` to write to a different file instead of overwriting in place.

### 1. Single command (general images)

```bash
python3 scripts/fit_image.py <image.png> --max-mb 1.0
```

- `--max-mb` : ceiling in MB (default `1.0`). For marketplace avatars use `0.5`.
- `--maxdim-start` : longest-side to try first (default `512`).
- `--output` : write to a new file instead of overwriting the input in place.
- No change is made if the file is already under the limit (it reports `OK`).

The loop lowers `--maxdim` by 20% each round (512 → 409 → 327 → … down to 64)
until the output fits, then replaces the target file.

### 2. Just downscale to a dimension

```bash
python3 scripts/resize_png.py <in.png> <out.png> --maxdim 512
```

### 3. Verify the result

```bash
ls -la <image.png>        # confirm bytes <= limit
```

## Critical pitfall: Windows paths in Git Bash

When invoking these scripts from the Bash tool on Windows, **do not put a
`C:\...` path into a shell variable or pass it with backslashes** — Git Bash can
mangle it and silently drop the `C:` (e.g. `C:\Users\...` becomes
`:/Users/...`, raising `OSError: [Errno 22]`). Use **forward slashes** instead:

```bash
# Good
C:/Users/test/.workbuddy/binaries/python/versions/3.13.12/python.exe \
  C:/Users/test/.workbuddy/skills/image-size-limit/scripts/fit_image.py \
  C:/path/to/avatar.png --max-mb 1.0

# Bad (the backslash in the var breaks it)
AV="C:\Users\test\...\avatar.png"   # -> drops the drive letter
```

Python on Windows accepts forward-slash paths, so keep everything forward-slashed
and run the command as a single line (no shell-variable indirection) to avoid the
permission parser also choking on multiline assignments.

## Conventions / defaults

- General upload/share cap: **1 MB** (`--max-mb 1.0`).
- Marketplace or plugin avatar cap: **500 KB**, display 512x512
  (`--max-mb 0.5 --maxdim-start 512`).
- Downsampling is area-average (lossless at the pixel-average level); the stored
  pixels are exact averages of their source blocks — fine for avatars/icons.
