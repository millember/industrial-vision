from io import BytesIO
import struct
import zlib
import pytest
from PIL import Image
from app.application.dtos.analysis import MAX_IMAGE_BYTES
from app.domain.errors import AnalysisError
from app.infrastructure.images import PillowImageDecoder


def picture(fmt="PNG", size=(12, 8), orientation=None):
    output = BytesIO()
    with Image.new("RGB", size, (120, 30, 60)) as image:
        exif = Image.Exif()
        if orientation is not None:
            exif[274] = orientation
        image.save(output, format=fmt, exif=exif)
    return output.getvalue()


@pytest.mark.parametrize("fmt,media_type", [("JPEG", "image/jpeg"), ("PNG", "image/png")])
def test_normalized_image_matches_dimensions_and_removes_exif(fmt, media_type):
    result = PillowImageDecoder().normalize(picture(fmt, orientation=6))
    assert (result.width, result.height, result.media_type) == (8, 12, media_type)
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (8, 12)
        assert not image.getexif()
        image.load()


@pytest.mark.parametrize("content,code", [
    (b"", "INVALID_IMAGE"),
    (b"\xff\xd8broken", "INVALID_IMAGE"),
    (b"not an image", "UNSUPPORTED_IMAGE_TYPE"),
    (picture("GIF"), "UNSUPPORTED_IMAGE_TYPE"),
    (b"x" * (MAX_IMAGE_BYTES + 1), "IMAGE_TOO_LARGE"),
    (picture()[:-16], "INVALID_IMAGE"),
])
def test_rejects_invalid_images(content, code):
    with pytest.raises(AnalysisError) as error:
        PillowImageDecoder().normalize(content)
    assert error.value.code == code


def test_rejects_large_pixel_count_before_decoding():
    content = bytearray(picture())
    content[16:24] = struct.pack(">II", 5000, 4001)
    content[29:33] = struct.pack(">I", zlib.crc32(content[12:29]))
    with pytest.raises(AnalysisError) as error:
        PillowImageDecoder().normalize(bytes(content))
    assert error.value.code == "IMAGE_TOO_LARGE"


def test_rejects_animated_png():
    output = BytesIO()
    with Image.new("RGB", (10, 10), "red") as first, Image.new("RGB", (10, 10), "blue") as second:
        first.save(output, format="PNG", save_all=True, append_images=[second])
    with pytest.raises(AnalysisError) as error:
        PillowImageDecoder().normalize(output.getvalue())
    assert error.value.code == "INVALID_IMAGE"
