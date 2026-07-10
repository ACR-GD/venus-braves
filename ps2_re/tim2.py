"""TIM2 / TM2 — format texture standard PS2 (trouver, exporter, modifier)."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .tim2_swizzle import (
    clut_to_rgba,
    deswizzle_psmct32,
    deswizzle_psmt4,
    deswizzle_psmt8,
    rgba_to_clut,
    swizzle_psmct32,
    swizzle_psmt4,
    swizzle_psmt8,
)

IMAGE_TYPES = {
    0: "undefined",
    1: "rgba16",
    2: "rgb32",
    3: "rgba32",
    4: "indexed4",
    5: "indexed8",
}

PSM_NAMES = {
    0: "PSMCT32",
    1: "PSMCT24",
    2: "PSMCT16",
    10: "PSMCT16S",
    19: "PSMT8",
    20: "PSMT4",
}


@dataclass
class Tim2Picture:
    index: int
    offset: int
    total_size: int
    clut_size: int
    image_size: int
    header_size: int
    clut_colors: int
    mipmap_count: int
    clut_type: int
    image_type: int
    width: int
    height: int
    gs_tex0: int
    gs_tex1: int
    gs_flags: int
    gs_clut: int
    bitmap_offset: int
    clut_offset: int | None
    psm: int = 0
    csm: int = 0

    @property
    def image_type_name(self) -> str:
        return IMAGE_TYPES.get(self.image_type, f"type_{self.image_type}")

    @property
    def psm_name(self) -> str:
        return PSM_NAMES.get(self.psm, f"PSM_{self.psm}")


@dataclass
class Tim2File:
    path: Path | None
    data: bytes
    version: int
    format_id: int
    header_size: int
    pictures: list[Tim2Picture] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path else None,
            "size": len(self.data),
            "version": self.version,
            "format_id": self.format_id,
            "header_size": self.header_size,
            "picture_count": len(self.pictures),
            "pictures": [
                {
                    "index": p.index,
                    "offset": f"0x{p.offset:X}",
                    "width": p.width,
                    "height": p.height,
                    "image_type": p.image_type_name,
                    "psm": p.psm_name,
                    "mipmaps": p.mipmap_count,
                    "clut_colors": p.clut_colors,
                    "image_size": p.image_size,
                    "clut_size": p.clut_size,
                }
                for p in self.pictures
            ],
        }


def _read_u64(data: bytes, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]


def parse_tim2(data: bytes, path: Path | None = None) -> Tim2File:
    if len(data) < 16 or data[:4] != b"TIM2":
        raise ValueError("Magic TIM2 attendu")

    version = data[4]
    format_id = data[5]
    pic_count = struct.unpack_from("<H", data, 6)[0]
    header_size = 16 if format_id == 0 else 128

    if pic_count == 0 or pic_count > 256:
        raise ValueError(f"picture_count invalide ({pic_count})")

    pictures: list[Tim2Picture] = []
    off = header_size
    for idx in range(pic_count):
        if off + 48 > len(data):
            raise ValueError(f"header image {idx} tronqué")
        total_size, clut_size, image_size = struct.unpack_from("<III", data, off)
        header_size_pic, clut_colors = struct.unpack_from("<HH", data, off + 12)
        pict_fmt, mipmaps, clut_type, image_type = struct.unpack_from("<BBBB", data, off + 16)
        width, height = struct.unpack_from("<HH", data, off + 20)
        gs_tex0 = _read_u64(data, off + 24)
        gs_tex1 = _read_u64(data, off + 32)
        gs_flags, gs_clut = struct.unpack_from("<II", data, off + 40)

        psm = (gs_tex0 >> 20) & 0x3F
        csm = (gs_tex0 >> 55) & 1

        body = off + header_size_pic
        if mipmaps > 1:
            body += (mipmaps - 1) * 48
        bitmap_off = body
        clut_off = body + image_size if clut_size > 0 else None

        pictures.append(Tim2Picture(
            index=idx,
            offset=off,
            total_size=total_size,
            clut_size=clut_size,
            image_size=image_size,
            header_size=header_size_pic,
            clut_colors=clut_colors,
            mipmap_count=mipmaps,
            clut_type=clut_type,
            image_type=image_type,
            width=width,
            height=height,
            gs_tex0=gs_tex0,
            gs_tex1=gs_tex1,
            gs_flags=gs_flags,
            gs_clut=gs_clut,
            bitmap_offset=bitmap_off,
            clut_offset=clut_off,
            psm=psm,
            csm=csm,
        ))
        if total_size <= 0:
            raise ValueError(f"total_size invalide pour image {idx}")
        off += total_size

    return Tim2File(
        path=path,
        data=data,
        version=version,
        format_id=format_id,
        header_size=header_size,
        pictures=pictures,
    )


def is_tim2(data: bytes, offset: int = 0) -> bool:
    if offset + 16 > len(data) or data[offset : offset + 4] != b"TIM2":
        return False
    pic_count = struct.unpack_from("<H", data, offset + 6)[0]
    fmt = data[offset + 5]
    if pic_count == 0 or pic_count > 256 or fmt not in (0, 1):
        return False
    try:
        parse_tim2(data[offset:])
        return True
    except Exception:
        return False


def find_tim2_in_blob(data: bytes, *, max_hits: int = 32) -> list[int]:
    """Cherche TIM2 embarqués (archives, gros .bin)."""
    hits: list[int] = []
    start = 0
    while start < len(data) - 16 and len(hits) < max_hits:
        pos = data.find(b"TIM2", start)
        if pos < 0:
            break
        if is_tim2(data, pos):
            hits.append(pos)
        start = pos + 4
    return hits


def scan_tim2_tree(
    root: Path,
    *,
    extensions: tuple[str, ...] = (".tm2", ".TM2", ".tim2", ".TIM2"),
    scan_embedded: bool = False,
) -> list[dict[str, Any]]:
    root = root.resolve()
    results: list[dict[str, Any]] = []

    files: list[Path] = []
    if root.is_file():
        files = [root]
    else:
        for ext in extensions:
            files.extend(root.rglob(f"*{ext}"))
        files = sorted(set(files))

    for path in files:
        try:
            data = path.read_bytes()
            if is_tim2(data):
                tf = parse_tim2(data, path)
                entry = tf.to_dict()
                entry["source"] = "file"
                results.append(entry)
        except Exception as exc:
            results.append({"path": str(path), "error": str(exc)})

    if scan_embedded and root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() in extensions:
                continue
            if path.stat().st_size > 50_000_000:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for off in find_tim2_in_blob(data):
                try:
                    tf = parse_tim2(data[off:], path)
                    entry = tf.to_dict()
                    entry["path"] = str(path)
                    entry["embedded_offset"] = f"0x{off:X}"
                    entry["source"] = "embedded"
                    results.append(entry)
                except Exception:
                    pass

    return results


def _picture_to_rgba(tf: Tim2File, pic: Tim2Picture):
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("pip install Pillow pour export TIM2")

    data = tf.data
    bitmap = data[pic.bitmap_offset : pic.bitmap_offset + pic.image_size]
    w, h = pic.width, pic.height

    if pic.image_type in (3, 2) or pic.psm == 0:
        rgba = bytearray(deswizzle_psmct32(bitmap, w, h))
        if pic.image_type == 2:
            for i in range(3, len(rgba), 4):
                rgba[i] = 255
        img = Image.frombytes("RGBA", (w, h), bytes(rgba[: w * h * 4]))
        return img

    if pic.image_type == 5 or pic.psm == 19:
        indices, _, _ = deswizzle_psmt8(bitmap, w, h)
        idx = bytes(indices[: w * h])
        if pic.clut_offset and pic.clut_size > 0:
            clut_raw = data[pic.clut_offset : pic.clut_offset + pic.clut_size]
            n = pic.clut_colors or 256
            pal = clut_to_rgba(clut_raw, n, csm1=bool(pic.csm))
            flat: list[int] = []
            for i in range(256):
                if i < n:
                    flat.extend(pal[i * 4 : i * 4 + 3])
                else:
                    flat.extend([0, 0, 0])
            img = Image.frombytes("P", (w, h), idx)
            img.putpalette(flat)
            return img.convert("RGBA")
        gray = Image.frombytes("L", (w, h), idx)
        return gray.convert("RGBA")

    if pic.image_type == 4 or pic.psm == 20:
        nibbles, bw, bh = deswizzle_psmt4(bitmap, w, h)
        idx = bytes(nibbles[: w * h])
        if pic.clut_offset and pic.clut_size > 0:
            clut_raw = data[pic.clut_offset : pic.clut_offset + pic.clut_size]
            n = pic.clut_colors or 16
            pal = clut_to_rgba(clut_raw, n, csm1=bool(pic.csm))
            img = Image.frombytes("P", (w, h), idx)
            img.putpalette(list(pal)[: 256 * 4])
            return img.convert("RGBA")
        gray = Image.frombytes("L", (w, h), bytes(v * 17 for v in idx))
        return gray.convert("RGBA")

    raise ValueError(
        f"Format non supporté: image_type={pic.image_type_name} psm={pic.psm_name}. "
        "Essayez Rainbow ou un dump PCSX2."
    )


def export_tim2(
    path: Path,
    out_dir: Path,
    *,
    picture_index: int | None = None,
    export_clut: bool = True,
) -> dict[str, Any]:
    data = path.read_bytes()
    tf = parse_tim2(data, path)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"file": str(path), "exported": []}

    pics = tf.pictures if picture_index is None else [tf.pictures[picture_index]]
    for pic in pics:
        tag = f"{path.stem}_pic{pic.index:02d}_{pic.width}x{pic.height}"
        img = _picture_to_rgba(tf, pic)
        png_path = out_dir / f"{tag}.png"
        img.save(png_path)
        item: dict[str, Any] = {
            "picture": pic.index,
            "png": str(png_path),
            "format": pic.image_type_name,
            "psm": pic.psm_name,
        }
        if export_clut and pic.clut_offset and pic.clut_size > 0:
            clut_path = out_dir / f"{tag}_clut.png"
            n = pic.clut_colors or (256 if pic.image_type == 5 else 16)
            pal = clut_to_rgba(
                tf.data[pic.clut_offset : pic.clut_offset + pic.clut_size],
                n,
                csm1=bool(pic.csm),
            )
            from PIL import Image
            pal_img = Image.frombytes("RGBA", (n, 1), pal)
            pal_img = pal_img.resize((n * 4, 16), Image.Resampling.NEAREST)
            pal_img.save(clut_path)
            item["clut_png"] = str(clut_path)
        result["exported"].append(item)

    meta = out_dir / f"{path.stem}_tim2.json"
    meta.write_text(json.dumps(tf.to_dict(), indent=2), encoding="utf-8")
    result["metadata"] = str(meta)
    return result


def replace_tim2_picture(
    tim2_path: Path,
    png_path: Path,
    out_path: Path,
    *,
    picture_index: int = 0,
    clut_png: Path | None = None,
) -> dict[str, Any]:
    """
    Remplace le bitmap (et optionnellement la CLUT) d'une image TIM2.

    Conserve la structure du fichier ; les tailles image_size/clut_size doivent
    correspondre (mêmes dimensions et format). Pour changer la taille, il faut
    reconstruire le TIM2 manuellement.
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("pip install Pillow")

    data = bytearray(tim2_path.read_bytes())
    tf = parse_tim2(bytes(data), tim2_path)
    pic = tf.pictures[picture_index]
    img = Image.open(png_path).convert("RGBA")
    if img.size != (pic.width, pic.height):
        raise ValueError(
            f"PNG {img.size} != TIM2 {pic.width}x{pic.height}. "
            "Redimensionnez l'image avant import."
        )

    new_bitmap: bytes
    if pic.image_type in (3, 2) or pic.psm == 0:
        rgba = img.tobytes()
        new_bitmap = swizzle_psmct32(rgba, pic.width, pic.height)
    elif pic.image_type == 5 or pic.psm == 19:
        n = pic.clut_colors or 256
        if pic.clut_offset and pic.clut_size > 0:
            clut_raw = data[pic.clut_offset : pic.clut_offset + pic.clut_size]
            pal = clut_to_rgba(clut_raw, n, csm1=bool(pic.csm))
            flat: list[int] = []
            for i in range(256):
                if i < n:
                    flat.extend(pal[i * 4 : i * 4 + 3])
                else:
                    flat.extend([0, 0, 0])
            pal_p = Image.new("P", (1, 1))
            pal_p.putpalette(flat)
            base = img.convert("RGB").quantize(palette=pal_p, dither=Image.Dither.NONE)
            idx = list(base.getdata())
        else:
            idx = list(img.convert("L").getdata())
        new_bitmap = swizzle_psmt8(bytes(idx), pic.width, pic.height)
    elif pic.image_type == 4 or pic.psm == 20:
        if pic.clut_offset:
            clut_raw = data[pic.clut_offset : pic.clut_offset + pic.clut_size]
            n = pic.clut_colors or 16
            pal = clut_to_rgba(clut_raw, n, csm1=bool(pic.csm))
            pal_img = Image.frombytes("RGBA", (n, 1), pal)
            base = img.quantize(colors=n, palette=pal_img, dither=Image.Dither.NONE)
            idx = list(base.getdata())
        else:
            gray = img.convert("L")
            idx = [v >> 4 for v in gray.getdata()]
        new_bitmap = swizzle_psmt4(bytes(idx), pic.width, pic.height)
    else:
        raise ValueError(f"Import non supporté pour {pic.image_type_name}")

    if len(new_bitmap) > pic.image_size:
        raise ValueError(
            f"Bitmap swizzlé ({len(new_bitmap)} o) > image_size ({pic.image_size}). "
            "Dimensions ou format incompatible."
        )
    new_bitmap = new_bitmap.ljust(pic.image_size, b"\x00")
    data[pic.bitmap_offset : pic.bitmap_offset + pic.image_size] = new_bitmap

    if clut_png and pic.clut_offset and pic.clut_size > 0:
        cimg = Image.open(clut_png).convert("RGBA")
        n = pic.clut_colors or 256
        cimg = cimg.resize((n, 1))
        new_clut = rgba_to_clut(cimg.tobytes(), n, csm1=bool(pic.csm))
        if len(new_clut) > pic.clut_size:
            raise ValueError("CLUT trop grande pour l'emplacement TIM2")
        new_clut = new_clut.ljust(pic.clut_size, b"\x00")
        data[pic.clut_offset : pic.clut_offset + pic.clut_size] = new_clut

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return {
        "input": str(tim2_path),
        "png": str(png_path),
        "output": str(out_path),
        "picture": picture_index,
        "format": pic.image_type_name,
        "bitmap_bytes": len(new_bitmap),
    }
