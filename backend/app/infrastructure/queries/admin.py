from sqlalchemy import select
from app.application.dtos.rows import UserRow, KeyRow, NamedRow, EquipmentRow, DefectRow
from app.application.contracts import Account
from app.infrastructure.models import User,ApiKey,Workshop,Equipment,DefectType
from app.infrastructure.catalogue import CATALOGUE

class AdminQueries:
    def __init__(self, sessions):self.sessions=sessions
    def equipment(self, equipment_id: int, user: Account) -> EquipmentRow | None:
        query = select(Equipment).where(Equipment.id == equipment_id)
        if user.role != "ADMIN":
            query = query.where(Equipment.workshop_id == user.workshop_id)
        with self.sessions() as db:
            row = db.scalar(query)
            return EquipmentRow(row.id, row.name, row.inventory_number, row.workshop_id, row.type_id, row.passport) if row else None

    def keys(self, user_id:int)->tuple[KeyRow,...]:
        with self.sessions() as db:
            return tuple(KeyRow(r.id,r.name,r.prefix,r.created_at,r.expires_at,r.revoked)
                for r in db.scalars(select(ApiKey).where(ApiKey.user_id==user_id).order_by(ApiKey.id.desc())))
    def users(self)->tuple[UserRow,...]:
        with self.sessions() as db:
            return tuple(UserRow(r.id,r.login,r.full_name,r.role,r.workshop_id,r.active)
                for r in db.scalars(select(User).order_by(User.id).limit(500)))
    def catalogue(self,kind:str,user:Account)->tuple[NamedRow|EquipmentRow|DefectRow,...]:
        model,fields=CATALOGUE[kind]
        query=select(model).order_by(model.id)
        if user.role!="ADMIN" and kind in ("workshops","equipment"):
            query=query.where((Workshop.id if kind=="workshops" else Equipment.workshop_id)==user.workshop_id)
        dto=EquipmentRow if kind=="equipment" else DefectRow if kind=="defect-types" else NamedRow
        with self.sessions() as db:
            return tuple(dto(**{f:getattr(row,f) for f in fields}) for row in db.scalars(query.limit(500)))
