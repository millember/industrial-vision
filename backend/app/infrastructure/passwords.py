from pwdlib import PasswordHash

class Passwords:
    def __init__(self):
        self.hasher = PasswordHash.recommended()
    def hash(self, password: str) -> str:
        return self.hasher.hash(password)
    def verify(self, password: str, hashed: str) -> bool:
        return self.hasher.verify(password, hashed)
