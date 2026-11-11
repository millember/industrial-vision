class DomainError(Exception): pass
class Conflict(DomainError): pass
class InvalidInput(DomainError): pass
class Missing(DomainError): pass


class AnalysisError(DomainError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
