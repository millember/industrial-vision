import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from threading import Semaphore
from typing import Protocol
from .contracts import AuthStore, Account

SESSION_TTL = timedelta(hours=24)
SESSION_TTL_SECONDS = int(SESSION_TTL.total_seconds())

class Passwords(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, hashed: str) -> bool: ...

def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

class InvalidLogin(Exception): pass
class LoginLimited(Exception): pass

class AuthService:
    def __init__(self, store: AuthStore, passwords: Passwords):
        self.store, self.passwords = store, passwords
        self.workers = Semaphore(2)
        self.dummy = passwords.hash(secrets.token_urlsafe(32))

    def login(self, login: str, password: str) -> tuple[Account, str]:
        now = datetime.now(timezone.utc)
        if self.store.login_blocked(login, now): raise LoginLimited()
        user = self.store.find_user(login)
        with self.workers:
            valid = self.passwords.verify(password, user.password_hash if user else self.dummy)
        if not user or not valid:
            self.store.failed_login(login, now)
            raise InvalidLogin()
        self.store.reset_attempts(login)
        raw = "iv_s_" + secrets.token_urlsafe(40)
        self.store.add_session(user.id, digest(raw), now + SESSION_TTL)
        return user, raw

    def authenticate(self, raw: str, kind: str) -> Account | None:
        prefix = "iv_s_" if kind == "session" else "iv_k_"
        if not raw.startswith(prefix) or len(raw) > 128: return None
        now = datetime.now(timezone.utc)
        return self.store.identify(digest(raw), kind, now, now + SESSION_TTL)

    def logout(self, raw: str) -> None:
        self.store.remove_session(digest(raw))
