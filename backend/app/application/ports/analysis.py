from typing import Protocol
from app.application.dtos.analysis import NormalizedImage, Observation


class ImageDecoder(Protocol):
    def normalize(self, content: bytes) -> NormalizedImage: ...


class ModelAdapter(Protocol):
    def analyze(self, image: NormalizedImage) -> Observation: ...
