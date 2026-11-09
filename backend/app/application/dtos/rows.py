from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class UserRow:
    id:int
    login:str
    full_name:str
    role:str
    workshop_id:int|None
    active:bool

@dataclass(frozen=True)
class KeyRow:
    id:int
    name:str
    prefix:str
    created_at:datetime
    expires_at:datetime
    revoked:bool

@dataclass(frozen=True)
class NamedRow:
    id:int
    name:str

@dataclass(frozen=True)
class EquipmentRow:
    id:int
    name:str
    inventory_number:str
    workshop_id:int
    type_id:int
    passport:str

@dataclass(frozen=True)
class DefectRow:
    id:int
    name:str
    status:str
    recommendation:str
