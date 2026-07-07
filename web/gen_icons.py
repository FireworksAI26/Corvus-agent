"""Regenerate the PWA PNG icons (pure-Python, no image libraries).

The binary PNGs aren't tracked in git; run this once to create them:
    python web/gen_icons.py
Produces web/icon-192.png and web/icon-512.png (brand indigo mark).
"""
import os
import struct
import zlib


def png_icon(path: str, size: int, bg=(14, 14, 20), fg=(124, 108, 255)):
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 for each scanline
        for x in range(size):
            inside = (abs(x - size / 2) + abs(y - size / 2)) < size * 0.30
            raw += bytes(fg if inside else bg)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for s in (192, 512):
        png_icon(os.path.join(here, f"icon-{s}.png"), s)
        print(f"wrote web/icon-{s}.png")
