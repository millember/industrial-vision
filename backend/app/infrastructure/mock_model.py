from app.application.dtos.analysis import NormalizedImage, Observation


class MockModelAdapter:
    def analyze(self, image: NormalizedImage) -> Observation:
        return Observation("UNDETERMINED", image.width, image.height,
                           "Режим MOCK: распознавание не выполнялось")
