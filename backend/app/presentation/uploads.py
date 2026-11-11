from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from typing import Literal
from python_multipart.exceptions import MultipartParseError
from app.application.dtos.analysis import MAX_IMAGE_BYTES
from app.domain.errors import AnalysisError

MAX_MULTIPART_BYTES = MAX_IMAGE_BYTES + 64 * 1024


class PreviewForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_id: int = Field(gt=0)
    source: Literal["CAMERA", "GALLERY"]


async def read_photo(request: Request) -> tuple[PreviewForm, bytes]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise AnalysisError("VALIDATION_ERROR", "Ожидается multipart/form-data")
    # Bound the actual stream, including chunked requests, before multipart parsing.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_MULTIPART_BYTES:
            raise AnalysisError("IMAGE_TOO_LARGE", "Слишком большой запрос загрузки")
        body.extend(chunk)

    async def receive():
        return {"type":"http.request", "body":bytes(body), "more_body":False}

    bounded_request = Request(request.scope, receive)
    try:
        async with bounded_request.form(max_files=1, max_fields=2, max_part_size=64 * 1024) as form:
            if len(form.multi_items()) != 3 or set(form) != {"equipment_id", "source", "image"}:
                raise AnalysisError("VALIDATION_ERROR", "Нужны equipment_id, source и один файл image")
            fields = PreviewForm.model_validate({"equipment_id":form["equipment_id"], "source":form["source"]})
            image = form["image"]
            if not isinstance(image, UploadFile):
                raise AnalysisError("VALIDATION_ERROR", "Поле image должно содержать файл")
            if image.size is not None and image.size > MAX_IMAGE_BYTES:
                raise AnalysisError("IMAGE_TOO_LARGE", "Фотография превышает 10 МиБ")
            content = await image.read(MAX_IMAGE_BYTES + 1)
            if len(content) > MAX_IMAGE_BYTES:
                raise AnalysisError("IMAGE_TOO_LARGE", "Фотография превышает 10 МиБ")
            return fields, content
    except (HTTPException, ValidationError, MultipartParseError):
        raise AnalysisError("VALIDATION_ERROR", "Некорректная multipart-загрузка") from None


PREVIEW_REQUEST_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type":"object", "required":["equipment_id", "source", "image"],
            "properties": {
                "equipment_id":{"type":"integer", "minimum":1, "description":"ID выбранного оборудования своего цеха из GET /equipment.", "example":125},
                "source":{"type":"string", "enum":["CAMERA", "GALLERY"], "description":"Фото с камеры или из галереи.", "example":"CAMERA"},
                "image":{"type":"string", "format":"binary", "description":"Один JPEG/PNG до 10 МиБ и 20 млн пикселей. Формат проверяется по байтам; EXIF-поворот нормализуется."},
            },
        }}},
    },
}
