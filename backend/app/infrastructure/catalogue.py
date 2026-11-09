from .models import Workshop,EquipmentType,Equipment,DefectType

CATALOGUE = {
    "workshops": (Workshop, ("id", "name")),
    "equipment-types": (EquipmentType, ("id", "name")),
    "equipment": (Equipment, ("id", "name", "inventory_number", "workshop_id", "type_id", "passport")),
    "defect-types": (DefectType, ("id", "name", "status", "recommendation")),
}
