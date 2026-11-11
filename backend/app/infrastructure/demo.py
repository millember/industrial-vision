"""Explicit synthetic MOCK fixtures for an operator-run demonstration, not recognition."""
from dataclasses import asdict
from io import BytesIO
import hashlib
from uuid import uuid5, NAMESPACE_URL
from PIL import Image
from sqlalchemy import select
from app.application.dtos.analysis import PreviewResult, ImageSize
from .models import Workshop, EquipmentType, Equipment, DefectType, User
from .passwords import Passwords
from .inspections import PostgresInspectionRepository
from .photo_storage import photo_storages

DEMO_USERS = (("demo_worker", "ДЕМО · Рабочий", "WORKER", 1),
              ("demo_master", "ДЕМО · Мастер", "MASTER", 1),
              ("demo_engineer", "ДЕМО · Инженер", "ENGINEER", 1),
              ("demo_foreign", "ДЕМО · Другой цех", "WORKER", 2))


def seed_demo(session_factory, password: str) -> dict:
    import os
    if os.getenv("ANALYSIS_MODE", "disabled") != "mock":
        raise ValueError("Для демоданных требуется явно включить ANALYSIS_MODE=mock")
    if not 12 <= len(password) <= 256:
        raise ValueError("Демонстрационный пароль: 12–256 символов")
    passwords = Passwords()
    with session_factory() as db:
        existing = tuple(db.scalars(select(User).where(User.login.in_([entry[0] for entry in DEMO_USERS]))))
    for user in existing:
        if not passwords.verify(password, user.password_hash):
            raise ValueError("Пароль существующего демопользователя не совпадает; учётные записи не изменены")
    hashes = {login:passwords.hash(password) for login, _, _, _ in DEMO_USERS}
    with session_factory.begin() as db:
        workshops = {}
        for number in (1, 2):
            name = f"ДЕМО · Цех {number}"
            row = db.scalar(select(Workshop).where(Workshop.name == name))
            if row is None:
                row = Workshop(name=name)
                db.add(row)
                db.flush()
            workshops[number] = row.id
        typ = db.scalar(select(EquipmentType).where(EquipmentType.name == "ДЕМО · Крепёж"))
        if typ is None:
            typ = EquipmentType(name="ДЕМО · Крепёж")
            db.add(typ)
            db.flush()
        equipment = {}
        for number in (1, 2):
            inventory = f"DEMO-IV-{number:03}"
            row = db.scalar(select(Equipment).where(Equipment.inventory_number == inventory))
            name = f"ДЕМО · Макет {number}"
            if row is None:
                row = Equipment(name=name, inventory_number=inventory, workshop_id=workshops[number], type_id=typ.id,
                                passport="Синтетический демонстрационный макет крепления; не реальное оборудование.")
                db.add(row)
                db.flush()
            elif (row.name, row.workshop_id, row.type_id) != (name, workshops[number], typ.id):
                raise ValueError("Демонстрационный инвентарный номер уже занят другой записью")
            equipment[number] = row.id
        defects = {}
        for status, name in (("WARNING", "ДЕМО · Недокручен"), ("CRITICAL", "ДЕМО · Отсутствует")):
            row = db.scalar(select(DefectType).where(DefectType.name == name))
            if row is None:
                row = DefectType(name=name, status=status, recommendation="Проверить крепление на безопасном демонстрационном макете.")
                db.add(row)
                db.flush()
            elif row.status != status:
                raise ValueError("Демонстрационный дефект уже имеет другую серьёзность")
            defects[status] = (row.id, row.name, row.recommendation)
        users = {}
        for login, name, role, number in DEMO_USERS:
            row = db.scalar(select(User).where(User.login == login))
            if row is None:
                row = User(login=login, full_name=name, role=role, workshop_id=workshops[number], password_hash=hashes[login], active=True)
                db.add(row)
                db.flush()
            elif (row.full_name, row.role, row.workshop_id, row.active) != (name, role, workshops[number], True):
                raise ValueError("Демонстрационный логин занят другой или отключённой учётной записью")
            users[login] = row.id
    output = BytesIO()
    with Image.new("RGB", (320, 240), (60, 80, 100)) as image:
        image.save(output, format="PNG")
    content = output.getvalue()
    backend, storages = photo_storages()
    storage = storages[backend]
    records = PostgresInspectionRepository(session_factory)
    inspections = {}
    for scenario, number, status in (("normal", 1, "OK"), ("warning", 1, "WARNING"), ("critical", 1, "CRITICAL"), ("foreign", 2, "WARNING")):
        author = users["demo_foreign" if number == 2 else "demo_worker"]
        key = str(uuid5(NAMESPACE_URL, f"industrial-vision:seed-demo:v1:{equipment[number]}:{author}:{scenario}"))
        request_hash = hashlib.sha256(f"seed-demo:v1:{scenario}".encode() + content).hexdigest()
        record, created = records.reserve(equipment_id=equipment[number], workshop_id=workshops[number], author_id=author,
                                         source="GALLERY", key=key, request_hash=request_hash, storage_backend=backend)
        if not created:
            if record.request_hash != request_hash or record.processing_status != "COMPLETED":
                raise ValueError("Демонстрационный осмотр уже существует с другим содержимым или не завершён; требуется проверка оператором")
            inspections[scenario] = record.id
            continue
        defect = defects.get(status)
        result = PreviewResult(equipment[number], f"ДЕМО · Макет {number}", "GALLERY", record.created_at, ImageSize(320, 240),
            "Синтетическое демосостояние задано командой seed-demo. Распознавание не выполнялось.",
            status=status, color={"OK":"GREEN", "WARNING":"ORANGE", "CRITICAL":"RED"}[status],
            defect=defect[1] if defect else "Норма (синтетический пример)",
            recommendation=defect[2] if defect else "Демонстрационный пример нормы; не результат модели.",
            defect_id=defect[0] if defect else None, defect_code=f"DEMO_{status}" if defect else None)
        from datetime import timezone
        body = {**asdict(result), "created_at":record.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "inspection_id":record.id, "photo_id":record.id, "author_id":author, "workshop_id":workshops[number]}
        try:
            storage.put(record.photo_key, content, "image/png")
            if not records.complete(record.id, body, "image/png", hashlib.sha256(content).hexdigest()):
                raise RuntimeError("Резервирование демонстрационного осмотра истекло")
        except Exception:
            records.fail(record.id, {"error":{"code":"ANALYSIS_INTERRUPTED", "message":"Подготовка демоснимка прервана"}}, 503, True)
            raise
        inspections[scenario] = record.id
    return {"analysis_source":"MOCK", "synthetic":True, "users":users, "workshops":workshops, "equipment":equipment,
            "inspections":inspections, "note":"Пароли не выводятся. Обычная загрузка фото по-прежнему возвращает UNKNOWN."}
