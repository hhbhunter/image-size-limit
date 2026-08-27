#!/usr/bin/env python3
"""
Pure-stdlib PNG downscaler (no Pillow / ImageMagick / ffmpeg needed).

Use when the host sandbox has no third-party image libraries and PowerShell
Add-Type / COM (WIA) are blocked by security policy. This script relies only
on the Python standard library (zlib + struct) to decode a PNG, average-downsample
it, and re-encode it with per-row adaptive filtering for best compression.

Supports: 8-bit, color type 2 (RGB) and 6 (RGBA).

Usage:
    python3 resize_png.py <input.png> <output.png> [--scale 0.5]
    python3 resize_png.py <input.png> <output.png> [--maxdim 512]

Options:
    --scale F   target size = round(src * F) per axis (default 0.5)
    --maxdim N  scale so the longest side <= N (overrides --scale if given)

The block-averaging handles arbitrary (non-even) source dimensions by clamping
each output pixel's source block to image bounds.
"""
import zlib
import struct
import os
import sys
import argparse


def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG file"
    pos = 8
    width = height = bitdepth = colortype = None
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bitdepth, colortype, comp, filt, inter = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    return width, height, bitdepth, colortype, idat


def unfilter(raw, width, height, channels):
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        ftype = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pval = a + b - c
                pa, pb, pc = abs(pval - a), abs(pval - b), abs(pval - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def filter_row(ftype, line, prev, stride, channels):
    res = bytearray(stride)
    for i in range(stride):
        x = line[i]
        a = line[i - channels] if i >= channels else 0
        b = prev[i]
        c = prev[i - channels] if i >= channels else 0
        if ftype == 0:
            v = x
        elif ftype == 1:
            v = x - a
        elif ftype == 2:
            v = x - b
        elif ftype == 3:
            v = x - ((a + b) >> 1)
        else:  # Paeth
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            v = x - pr
        res[i] = v & 0xFF
    return res


def chunk(ctype, cdata):
    c = ctype + cdata
    return struct.pack(">I", len(cdata)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def resize(input_path, output_path, maxdim=None, scale=0.5):
    """Downscale a PNG and write it to output_path. Returns (ow, oh)."""
    w, h, bd, ct, idat = read_png(input_path)
    assert bd == 8, "only 8-bit PNG supported"
    assert ct in (2, 6), "only RGB(2)/RGBA(6) color types supported"
    channels = 3 if ct == 2 else 4

    if maxdim:
        ratio = maxdim / max(w, h)
        ow, oh = max(1, round(w * ratio)), max(1, round(h * ratio))
    else:
        ow, oh = max(1, round(w * scale)), max(1, round(h * scale))

    raw = zlib.decompress(idat)
    pixels = unfilter(raw, w, h, channels)

    bw = w / ow
    bh = h / oh
    out = bytearray(ow * oh * channels)
    for y in range(oh):
        y0 = int(y * bh)
        y1 = max(y0 + 1, int((y + 1) * bh))
        for x in range(ow):
            x0 = int(x * bw)
            x1 = max(x0 + 1, int((x + 1) * bw))
            acc = [0] * channels
            cnt = 0
            for sy in range(y0, y1):
                for sx in range(x0, x1):
                    base = (sy * w + sx) * channels
                    for c in range(channels):
                        acc[c] += pixels[base + c]
                    cnt += 1
            o = (y * ow + x) * channels
            for c in range(channels):
                out[o + c] = acc[c] // cnt

    stride = ow * channels
    raw2 = bytearray()
    prev = bytearray(stride)
    for y in range(oh):
        line = out[y * stride:(y + 1) * stride]
        best, bestsum, bestf = None, None, 0
        for ftype in range(5):
            fb = filter_row(ftype, line, prev, stride, channels)
            s = sum(abs(b) for b in fb)
            if bestsum is None or s < bestsum:
                bestsum, best, bestf = s, fb, ftype
        raw2.append(bestf)
        raw2 += best
        prev = line
    comp = zlib.compress(bytes(raw2), 9)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", ow, oh, bd, ct, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(png)
    return ow, oh


def main():
    ap = argparse.ArgumentParser(description="Pure-stdlib PNG downscaler")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--scale", type=float, default=0.5, help="target = src*scale per axis")
    ap.add_argument("--maxdim", type=int, default=None, help="longest side <= N")
    args = ap.parse_args()
    ow, oh = resize(args.input, args.output, args.maxdim, args.scale)
    print("written: %s  %d x %d  %.1f KB" % (
        args.output, ow, oh, os.path.getsize(args.output) / 1024))


if __name__ == "__main__":
    main()
