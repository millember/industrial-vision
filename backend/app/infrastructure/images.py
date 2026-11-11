from io import BytesIO
from threading import Semaphore
from PIL import Image, ImageOps, UnidentifiedImageError
from app.application.dtos.analysis import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, NormalizedImage
from app.domain.errors import AnalysisError


class PillowImageDecoder:
    def __init__(self):
        self.workers = Semaphore(1)

    def normalize(self, content: bytes) -> NormalizedImage:
        if len(content) > MAX_IMAGE_BYTES:
            raise AnalysisError("IMAGE_TOO_LARGE", "Фотография превышает 10 МиБ")
        if not content:
            raise AnalysisError("INVALID_IMAGE", "Фотография пуста")
        with self.workers:
            return self._normalize(content)

    def _normalize(self, content: bytes) -> NormalizedImage:
        try:
            with Image.open(BytesIO(content), formats=("JPEG", "PNG")) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise AnalysisError("UNSUPPORTED_IMAGE_TYPE", "Поддерживаются только JPEG и PNG")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise AnalysisError("IMAGE_TOO_LARGE", "Фотография превышает 20 млн пикселей")
                if getattr(image, "n_frames", 1) != 1:
                    raise AnalysisError("INVALID_IMAGE", "Нужна фотография из одного кадра")
                image_format = image.format
                image.verify()
            with Image.open(BytesIO(content), formats=("JPEG", "PNG")) as image:
                image.load()
                ImageOps.exif_transpose(image, in_place=True)
                # Do not pass EXIF or other source metadata to the model.
                image.info.clear()
                output = BytesIO()
                image.save(output, format=image_format)
                return NormalizedImage(output.getvalue(), image.width, image.height,
                                       "image/jpeg" if image_format == "JPEG" else "image/png")
        except Image.DecompressionBombError:
            raise AnalysisError("IMAGE_TOO_LARGE", "Фотография превышает допустимое число пикселей") from None
        except UnidentifiedImageError:
            if content.startswith((b"\xff\xd8", b"\x89PNG\r\n\x1a\n")):
                raise AnalysisError("INVALID_IMAGE", "Фотография повреждена") from None
            raise AnalysisError("UNSUPPORTED_IMAGE_TYPE", "Файл не является изображением JPEG/PNG") from None
        except (OSError, ValueError, SyntaxError):
            raise AnalysisError("INVALID_IMAGE", "Фотография повреждена") from None
