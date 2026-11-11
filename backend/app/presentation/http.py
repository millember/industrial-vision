import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from typing import Annotated, Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Security
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from .schemas import Login, NewUser, Named, NewKey, NewEquipment, NewDefect, AccountOut, UserOut, KeyOut, IssuedKeyOut, NamedOut, EquipmentOut, DefectOut
from sqlalchemy.exc import IntegrityError
from app.application.auth import AuthService, InvalidLogin, LoginLimited, digest, SESSION_TTL_SECONDS
from app.application.contracts import Account
from app.infrastructure.database import make_engine, migrate, sessions, database_url
from app.infrastructure.passwords import Passwords
from .dependencies import create_services
from app.domain.errors import InvalidInput, Missing
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool
from app.domain.errors import AnalysisError
from .uploads import read_photo, PREVIEW_REQUEST_SCHEMA
from .schemas import PreviewOut

COOKIE = "iv_admin_session"
bearer = HTTPBearer(auto_error=False, scheme_name="AccessToken")

def public_user(user: Account):
    result = asdict(user)
    result.pop("password_hash")
    return result







def create_app(url: str | None = None, *, secure: bool | None = None, origin: str | None = None):
    root_path = os.getenv("ROOT_PATH", "")
    cookie_secure = secure if secure is not None else os.getenv("COOKIE_SECURE", "true").lower() == "true"
    allowed_origin = origin or os.getenv("ALLOWED_ORIGIN", "https://pet.oppennec.ru")
    @asynccontextmanager
    async def lifespan(app):
        engine = make_engine(url or database_url())
        try:
            migrate(engine)
            app.state.services = create_services(session_factory=sessions(engine), analysis_mode=os.getenv("ANALYSIS_MODE", "disabled"))
            yield
        finally:
            engine.dispose()
    app = FastAPI(title="Industrial Vision API", root_path=root_path, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(AnalysisError)
    async def analysis_error(request, exc):
        status = {"VALIDATION_ERROR":422, "INVALID_IMAGE":422, "UNSUPPORTED_IMAGE_TYPE":415,
                  "IMAGE_TOO_LARGE":413, "NOT_FOUND":404, "MODEL_UNAVAILABLE":503,
                  "MODEL_INVALID_RESPONSE":502}[exc.code]
        return JSONResponse({"error":{"code":exc.code, "message":str(exc)}}, status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if request.url.path.endswith("/api/v1/inspections/preview") and exc.status_code in (401, 403):
            code = "UNAUTHENTICATED" if exc.status_code == 401 else "FORBIDDEN"
            return JSONResponse({"error":{"code":code, "message":exc.detail}}, status_code=exc.status_code, headers=exc.headers)
        return await http_exception_handler(request, exc)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse({"detail":"Такая запись уже есть или связанная запись не найдена"},status_code=409)
    @app.exception_handler(InvalidInput)
    async def invalid_input(request, exc):
        return JSONResponse({"detail":str(exc)},status_code=422)
    @app.exception_handler(Missing)
    async def missing(request, exc):
        return JSONResponse({"detail":str(exc)},status_code=404)

    @app.middleware("http")
    async def private_cache(request, call_next):
        response = await call_next(request)
        renewed_cookie = getattr(request.state, "renewed_cookie", None)
        if renewed_cookie and response.status_code < 400:
            response.set_cookie(COOKIE, renewed_cookie, max_age=SESSION_TTL_SECONDS, httponly=True, secure=cookie_secure, samesite="strict", path=(root_path or "")+"/")
        if request.url.path != "/healthz":
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def csrf(request: Request):
        if request.headers.get("x-iv-client") != "browser" or request.headers.get("origin") != allowed_origin:
            raise HTTPException(403, "Недопустимый источник запроса")

    def administrator(request: Request) -> Account:
        user = request.app.state.services.auth.authenticate(request.cookies.get(COOKIE, ""), "session")
        if not user: raise HTTPException(401, "Войдите как администратор")
        if user.role != "ADMIN": raise HTTPException(403, "Требуется администратор")
        request.state.renewed_cookie = request.cookies[COOKIE]
        return user

    def principal(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)]) -> Account:
        if credentials:
            raw = credentials.credentials
            user = request.app.state.services.auth.authenticate(raw, "key" if raw.startswith("iv_k_") else "session")
        else:
            user = request.app.state.services.auth.authenticate(request.cookies.get(COOKIE, ""), "session")
        if not user: raise HTTPException(401, "Требуется авторизация", headers={"WWW-Authenticate":"Bearer"})
        if not credentials:
            request.state.renewed_cookie = request.cookies[COOKIE]
        return user

    Admin = Annotated[Account, Depends(administrator)]
    Member = Annotated[Account, Depends(principal)]

    def do_login(request, body):
        try:
            return request.app.state.services.auth.login(body.login.strip().lower(), body.password)
        except InvalidLogin:
            raise HTTPException(401, "Неверный логин или пароль") from None
        except LoginLimited:
            raise HTTPException(429, "Слишком много попыток. Повторите через 5 минут", headers={"Retry-After":"300"}) from None

    @app.get("/healthz", include_in_schema=False)
    def liveness(): return {"status":"ok"}

    @app.post("/api/v1/auth/login", dependencies=[Depends(csrf)])
    def login(body: Login, request: Request, response: Response):
        user, token = do_login(request, body)
        if user.role != "ADMIN":
            request.app.state.services.auth.logout(token)
            raise HTTPException(403, "Веб-кабинет доступен только администратору")
        old = request.cookies.get(COOKIE)
        if old: request.app.state.services.auth.logout(old)
        response.set_cookie(COOKIE, token, max_age=SESSION_TTL_SECONDS, httponly=True, secure=cookie_secure, samesite="strict", path=(root_path or "")+"/")
        return public_user(user)

    @app.post("/api/v1/auth/token")
    def mobile_login(body: Login, request: Request):
        user, token = do_login(request, body)
        return {"access_token":token,"token_type":"bearer","expires_in":SESSION_TTL_SECONDS,"user":public_user(user)}

    @app.get("/api/v1/auth/me", response_model=AccountOut)
    def admin_me(user: Admin): return public_user(user)

    @app.get("/api/v1/me", response_model=AccountOut)
    def me(user: Member): return public_user(user)

    @app.post("/api/v1/auth/logout", status_code=204, dependencies=[Depends(csrf)])
    def logout(request: Request, response: Response):
        request.app.state.services.auth.logout(request.cookies.get(COOKIE, ""))
        response.delete_cookie(COOKIE, path=(root_path or "")+"/", secure=cookie_secure, httponly=True, samesite="strict")

    @app.get("/api/v1/health")
    def health(user: Member): return {"status":"ok"}

    @app.post("/api/v1/inspections/preview", response_model=PreviewOut, openapi_extra=PREVIEW_REQUEST_SCHEMA)
    async def preview(request: Request, user: Member):
        if getattr(request.state, "renewed_cookie", None):
            csrf(request)
        fields, content = await read_photo(request)
        return await run_in_threadpool(request.app.state.services.preview.execute,
                                       equipment_id=fields.equipment_id, source=fields.source,
                                       content=content, actor=user)

    @app.get("/api/v1/keys", response_model=list[KeyOut])
    def keys(request: Request, user: Admin): return request.app.state.services.queries.keys(actor_id=user.id)

    @app.post("/api/v1/keys", response_model=IssuedKeyOut, status_code=201, dependencies=[Depends(csrf)])
    def new_key(body: NewKey, request: Request, user: Admin):
        return request.app.state.services.issue_key.execute(actor_id=user.id, name=body.name, days=body.days)

    @app.delete("/api/v1/keys/{key_id}", status_code=204, dependencies=[Depends(csrf)])
    def revoke(key_id: int, request: Request, user: Admin):
        request.app.state.services.revoke_key.execute(actor_id=user.id,key_id=key_id)

    @app.get("/api/v1/users", response_model=list[UserOut])
    def users(request: Request, user: Admin): return request.app.state.services.queries.users()

    @app.post("/api/v1/users", status_code=201, dependencies=[Depends(csrf)])
    def add_user(body: NewUser, request: Request, user: Admin):
        return request.app.state.services.users.execute(actor_id=user.id, **body.model_dump())

    def insert(kind, values, request, user):
        return request.app.state.services.catalogue.execute(actor_id=user.id,kind=kind,values=values)


    @app.get("/api/v1/workshops", response_model=list[NamedOut])
    def workshops(request: Request, user: Member): return request.app.state.services.queries.catalogue(kind="workshops",actor=user)
    @app.get("/api/v1/equipment-types", response_model=list[NamedOut])
    def types(request: Request, user: Member): return request.app.state.services.queries.catalogue(kind="equipment-types",actor=user)
    @app.get("/api/v1/equipment", response_model=list[EquipmentOut])
    def equipment(request: Request, user: Member): return request.app.state.services.queries.catalogue(kind="equipment",actor=user)
    @app.get("/api/v1/equipment/{equipment_id}", response_model=EquipmentOut)
    def equipment_card(equipment_id: int, request: Request, user: Member):
        return request.app.state.services.queries.equipment(equipment_id=equipment_id, actor=user)
    @app.get("/api/v1/defect-types", response_model=list[DefectOut])
    def defects(request: Request, user: Member): return request.app.state.services.queries.catalogue(kind="defect-types",actor=user)
    @app.post("/api/v1/workshops", status_code=201, dependencies=[Depends(csrf)])
    def add_workshop(body: Named, request: Request, user: Admin): return insert("workshops",body.model_dump(),request,user)
    @app.post("/api/v1/equipment-types", status_code=201, dependencies=[Depends(csrf)])
    def add_type(body: Named, request: Request, user: Admin): return insert("equipment-types",body.model_dump(),request,user)
    @app.post("/api/v1/equipment", status_code=201, dependencies=[Depends(csrf)])
    def add_equipment(body: NewEquipment, request: Request, user: Admin): return insert("equipment",body.model_dump(),request,user)
    @app.post("/api/v1/defect-types", status_code=201, dependencies=[Depends(csrf)])
    def add_defect(body: NewDefect, request: Request, user: Admin): return insert("defect-types",body.model_dump(),request,user)

    @app.get("/openapi.json", include_in_schema=False)
    def schema(user: Admin):
        result=app.openapi()
        result["servers"]=[{"url":root_path or "/"}]
        return result
    @app.get("/docs", include_in_schema=False)
    def docs(user: Admin): return get_swagger_ui_html(openapi_url=root_path+"/openapi.json",title="Industrial Vision API")
    @app.get("/redoc", include_in_schema=False)
    def redoc(user: Admin): return get_redoc_html(openapi_url=root_path+"/openapi.json",title="Industrial Vision API")

    frontend = Path(os.getenv("FRONTEND_DIR", "/app/frontend"))
    if frontend.is_dir():
        app.mount("/assets",StaticFiles(directory=frontend/"assets"),name="assets")
        @app.get("/", include_in_schema=False)
        def index(): return FileResponse(frontend/"index.html")
    return app
