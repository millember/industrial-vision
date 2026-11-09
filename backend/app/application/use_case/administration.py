import secrets
from datetime import datetime, timedelta, timezone
from app.application.auth import digest, Passwords
from app.application.contracts import Account
from app.application.ports.admin import AdminRepositoryPort, AdminQueryPort
from app.domain.errors import InvalidInput, Missing

class CreateUserUseCase:
    def __init__(self, *, users: AdminRepositoryPort, passwords: Passwords):
        self.users, self.passwords = users, passwords

    def execute(self, *, actor_id: int, login: str, password: str, full_name: str, role: str, workshop_id: int | None):
        if role != "ADMIN" and workshop_id is None:
            raise InvalidInput("Укажите цех сотрудника")
        values = {"login":login.strip().lower(),"password_hash":self.passwords.hash(password),
                  "full_name":full_name.strip(),"role":role,"workshop_id":workshop_id,"active":True}
        return {"id": self.users.create_user(values,actor_id)}

class IssueKeyUseCase:
    def __init__(self, *, keys: AdminRepositoryPort):
        self.keys=keys
    def execute(self, *, actor_id: int, name: str, days: int):
        raw="iv_k_"+secrets.token_urlsafe(40)
        expires=datetime.now(timezone.utc)+timedelta(days=days)
        key_id=self.keys.new_key(actor_id,name.strip(),raw[:12],digest(raw),expires)
        return {"id":key_id,"key":raw,"expires_at":expires}

class RevokeKeyUseCase:
    def __init__(self, *, keys: AdminRepositoryPort): self.keys=keys
    def execute(self, *, actor_id: int, key_id: int):
        if not self.keys.revoke_key(actor_id,key_id): raise Missing("Ключ не найден")

class CatalogueCreateUseCase:
    def __init__(self, *, records: AdminRepositoryPort): self.records=records
    def execute(self, *, actor_id: int, kind: str, values: dict):
        for field in ("name","inventory_number","recommendation"):
            if field in values:
                values[field]=values[field].strip()
                if not values[field]:raise InvalidInput("Заполните обязательные поля")
        return {"id":self.records.add_catalogue(kind,values,actor_id)}

class AdminQueriesUseCase:
    def __init__(self, *, queries: AdminQueryPort): self.queries=queries
    def keys(self, *, actor_id: int): return self.queries.keys(actor_id)
    def users(self): return self.queries.users()
    def catalogue(self, *, kind: str, actor: Account): return self.queries.catalogue(kind,actor)
