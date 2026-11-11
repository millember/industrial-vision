"""Interactive account provisioning; never accept passwords in argv."""
import argparse
import getpass
import sys
from .infrastructure.database import database_url, make_engine, migrate, sessions
from .infrastructure.repository import Repository
from .infrastructure.passwords import Passwords

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["create-admin", "seed-demo"])
    parser.add_argument("--login",default="niyaz")
    args=parser.parse_args()
    if args.command == "seed-demo":
        import json
        from .infrastructure.demo import seed_demo
        password = getpass.getpass("Пароль демонстрационных сотрудников (от 12 символов): ")
        if password != getpass.getpass("Повторите пароль: "):
            parser.error("Пароли не совпадают")
        engine = make_engine(database_url())
        try:
            migrate(engine)
            result = seed_demo(sessions(engine), password)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            engine.dispose()
        return
    import re
    login=args.login.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{1,80}",login):parser.error("Invalid login")
    password=getpass.getpass("Пароль администратора (от 12 символов): ")
    if len(password)<12 or len(password)>256:parser.error("Пароль: 12–256 символов")
    if password!=getpass.getpass("Повторите пароль: "):parser.error("Пароли не совпадают")
    engine=make_engine(database_url())
    try:
        migrate(engine);repo=Repository(sessions(engine))
        if repo.find_user(login):parser.error("Пользователь уже существует")
        repo.create_user({"login":login,"full_name":login,"role":"ADMIN","password_hash":Passwords().hash(password),"workshop_id":None,"active":True})
        print("Администратор создан:",login)
    finally:engine.dispose()

if __name__=="__main__":main()
