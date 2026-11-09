class DomainError(Exception): pass
class Conflict(DomainError): pass
class InvalidInput(DomainError): pass
class Missing(DomainError): pass
