"""Photos and videos made at test time (nothing real, nothing large in a public repository):
what an iPhone and an Android phone send, with the metadata the pipeline must remove."""

from __future__ import annotations

import io
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image

ORIENTATION = 0x0112
GPS_IFD = 0x8825
EXIF_IFD = 0x8769
MAKE, MODEL = 0x010F, 0x0110
DATE_TIME_ORIGINAL, OFFSET_TIME_ORIGINAL = 0x9003, 0x9011


def picture(size: tuple[int, int] = (800, 600), colour: tuple[int, int, int] = (200, 40, 40)):
    image = Image.new("RGB", size, colour)
    # something to see, so a flipped image is not mistaken for the original
    for x in range(0, min(size[0], 120)):
        for y in range(0, min(size[1], 40)):
            image.putpixel((x, y), (20, 20, 220))
    return image


def exif(
    *, orientation: int | None = None, gps: bool = False, taken: datetime | None = None,
    offset: str | None = None,
) -> Image.Exif:
    data = Image.Exif()
    data[MAKE], data[MODEL] = "Apple", "iPhone 15"
    if orientation:
        data[ORIENTATION] = orientation
    if gps:
        # 17°58'N 76°47'W: Kingston, with the precision a phone gives
        data.get_ifd(GPS_IFD).update({
            1: "N", 2: (17.0, 58.0, 17.0), 3: "W", 4: (76.0, 47.0, 31.0),
        })
    inner = data.get_ifd(EXIF_IFD)
    if taken:
        inner[DATE_TIME_ORIGINAL] = taken.strftime("%Y:%m:%d %H:%M:%S")
    if offset:
        inner[OFFSET_TIME_ORIGINAL] = offset
    return data


def jpeg(size: tuple[int, int] = (800, 600), **meta: object) -> bytes:
    out = io.BytesIO()
    picture(size).save(out, "JPEG", quality=90, exif=exif(**meta))  # type: ignore[arg-type]
    return out.getvalue()


def png(size: tuple[int, int] = (200, 100), alpha: bool = False) -> bytes:
    out = io.BytesIO()
    image = picture(size).convert("RGBA") if alpha else picture(size)
    if alpha:
        image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(out, "PNG")
    return out.getvalue()


def heic(size: tuple[int, int] = (640, 480), **meta: object) -> bytes:
    import pillow_heif

    out = io.BytesIO()
    pillow_heif.from_pillow(picture(size)).save(out, format="HEIF", quality=70,
                                                exif=exif(**meta).tobytes())  # type: ignore[arg-type]
    return out.getvalue()


def has_exif_or_gps(data: bytes) -> bool:
    """True if the file still carries EXIF, GPS or the camera's make anywhere in it."""
    if b"Exif" in data or b"GPS" in data or b"iPhone" in data or b"Apple" in data:
        return True
    with Image.open(io.BytesIO(data)) as image:
        found = image.getexif()
        return bool(found) or bool(image.info.get("exif")) or bool(image.info.get("xmp"))


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def video(
    path: Path, *, seconds: int = 3, size: str = "1920x1080", codec: str = "libx264",
    rotate: int | None = None, audio: bool = True, container: str = "mp4",
) -> Path:
    """A clip made by ffmpeg itself. `rotate` sets the display-matrix flag a phone writes for a
    portrait video. Raises `subprocess.CalledProcessError` where the codec isn't built in."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=25"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    args += ["-c:v", codec, "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac"]
    target = path.with_suffix(".src") if rotate is not None else path
    args += ["-f", container, str(target)]
    subprocess.run(args, check=True, capture_output=True)  # noqa: S603
    if rotate is not None:  # remux with the display-matrix flag, as a phone writes it
        subprocess.run(  # noqa: S603
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-display_rotation",  # noqa: S607
             str(rotate), "-i", str(target), "-c", "copy", "-f", container, str(path)],
            check=True, capture_output=True,
        )
    return path
