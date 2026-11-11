from datetime import datetime, timedelta
from sqlalchemy import select, delete, case, update, func
from sqlalchemy.dialects.postgresql import insert
from app.application.contracts import Account
from .models import User, BrowserSession, ApiKey, LoginAttempt, Audit, Workshop, EquipmentType, Equipment, DefectType

from .catalogue import CATALOGUE

def account(row):
    return Account(row.id, row.login, row.full_name, row.role, row.workshop_id, row.password_hash)

class Repository:
    def __init__(self, sessions):
        self.sessions = sessions

    def find_user(self, login):
        with self.sessions() as db:
            row = db.scalar(select(User).where(User.login == login, User.active.is_(True)))
            return account(row) if row else None

    def login_blocked(self, login, now):
        with self.sessions() as db:
            row = db.get(LoginAttempt, login)
            return bool(row and row.failures >= 5 and row.updated_at > now - timedelta(minutes=5))

    def failed_login(self, login, now):
        with self.sessions.begin() as db:
            stmt = insert(LoginAttempt).values(login=login, failures=1, updated_at=now)
            stmt = stmt.on_conflict_do_update(index_elements=["login"], set_={
                "failures": case((LoginAttempt.updated_at < now-timedelta(minutes=5), 1), else_=LoginAttempt.failures+1),
                "updated_at": now,
            })
            db.execute(stmt)

    def reset_attempts(self, login):
        with self.sessions.begin() as db: db.execute(delete(LoginAttempt).where(LoginAttempt.login == login))

    def add_session(self, user_id, digest, expires):
        with self.sessions.begin() as db:
            db.execute(delete(BrowserSession).where(BrowserSession.expires_at < datetime.now(expires.tzinfo)))
            db.add(BrowserSession(user_id=user_id, digest=digest, expires_at=expires))
            db.add(Audit(user_id=user_id, action="login"))

    def remove_session(self, digest):
        with self.sessions.begin() as db:
            db.execute(delete(BrowserSession).where(BrowserSession.digest == digest))

    def identify(self, digest: str, kind: str, now: datetime, renew_until: datetime) -> Account | None:
        if kind == "session":
            with self.sessions.begin() as db:
                user_id = db.scalar(
                    update(BrowserSession)
                    .where(
                        BrowserSession.digest == digest,
                        BrowserSession.expires_at > now,
                        BrowserSession.user_id.in_(select(User.id).where(User.active.is_(True))),
                    )
                    .values(expires_at=func.greatest(BrowserSession.expires_at, renew_until))
                    .returning(BrowserSession.user_id)
                )
                row = db.get(User, user_id) if user_id is not None else None
                return account(row) if row else None
        token = BrowserSession if kind == "session" else ApiKey
        query = select(User).join(token, token.user_id == User.id).where(token.digest == digest, token.expires_at > now, User.active.is_(True))
        if kind != "session": query = query.where(ApiKey.revoked.is_(False))
        with self.sessions() as db:
            row = db.scalar(query)
            return account(row) if row else None


    def new_key(self, user_id, name, prefix, digest, expires):
        with self.sessions.begin() as db:
            row=ApiKey(user_id=user_id, name=name, prefix=prefix, digest=digest, expires_at=expires)
            db.add(row); db.flush()
            db.add(Audit(user_id=user_id, action="key_created", entity_id=row.id))
            return row.id

    def revoke_key(self, user_id, key_id):
        with self.sessions.begin() as db:
            row=db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
            if not row: return False
            row.revoked=True
            db.add(Audit(user_id=user_id, action="key_revoked", entity_id=row.id))
            return True


    def add_catalogue(self, kind, values, user_id):
        model,_=CATALOGUE[kind]
        with self.sessions.begin() as db:
            row=model(**values);db.add(row);db.flush()
            db.add(Audit(user_id=user_id, action="create_"+kind, entity_id=row.id))
            return row.id

    def create_user(self, values, user_id=None):
        with self.sessions.begin() as db:
            row=User(**values); db.add(row);db.flush()
            db.add(Audit(user_id=user_id, action="user_created", entity_id=row.id))
            return row.id
