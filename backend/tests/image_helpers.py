"""Create valid in-memory image fixtures for upload tests."""

from io import BytesIO

from PIL import ExifTags, Image, TiffImagePlugin


def make_image_bytes(image_format: str, size: tuple[int, int] = (1, 1)) -> bytes:
    image = Image.new("RGB", size, (255, 255, 255))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def make_gps_jpeg() -> bytes:
    rational = TiffImagePlugin.IFDRational
    exif = Image.Exif()
    exif[ExifTags.IFD.GPSInfo] = {
        1: "S",
        2: (rational(37, 1), rational(48, 1), rational(0, 1)),
        3: "E",
        4: (rational(144, 1), rational(57, 1), rational(0, 1)),
    }

    image = Image.new("RGB", (24, 16), (80, 120, 160))
    output = BytesIO()
    image.save(output, format="JPEG", quality=100, subsampling=0, exif=exif)
    return output.getvalue()


def make_oriented_jpeg() -> bytes:
    image = Image.new("RGB", (40, 20), (255, 0, 0))
    image.paste((0, 0, 255), (20, 0, 40, 20))
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6

    output = BytesIO()
    image.save(output, format="JPEG", quality=100, subsampling=0, exif=exif)
    return output.getvalue()


TINY_PNG = make_image_bytes("PNG")
TINY_JPEG = make_image_bytes("JPEG")
