# Industrial Vision — шаг 2

FastAPI + PostgreSQL 17 + React/TypeScript. Зависимости backend — uv, frontend — npm lock.

## Структура

- backend/app/domain — ошибки и правила.
- backend/app/application — use cases, Protocol-порты, frozen DTO; без FastAPI/SQLAlchemy.
- backend/app/infrastructure — PostgreSQL-репозитории, отдельные queries и Argon2.
- backend/app/presentation — Pydantic-схемы, HTTP, права, dependency factory.
- backend/migrations — Alembic-миграции.
- frontend/src/app — UI и query lifecycle; composition подключает реализации.
- frontend/src/domain — модели и интерфейс CabinetRepository.
- frontend/src/data — HTTP и реализация репозитория. UI не импортирует data напрямую.

Подход взят из RS, фреймворк backend — FastAPI, ORM — SQLAlchemy. Миграции выполняются под PostgreSQL advisory lock.

## Доступ

Веб-кабинет /industrial-vision/, API-ключи, пользователи и Swagger доступны только администратору после входа.
POST /api/v1/auth/login создаёт HttpOnly/Secure/SameSite=Strict cookie на 24 часа с продлением при авторизованных запросах.
Операции браузера требуют Origin и X-IV-Client: browser. Вход ограничен после пяти неверных попыток на пять минут.
Пароли — Argon2, токены и ключи хранятся только в SHA-256-хешах. Новый API-ключ показывается один раз, действует 1–365 дней, немедленно отзывается.

Обычный сотрудник получает токен через POST /api/v1/auth/token и использует Android/API. Он не входит в веб-кабинет, не видит ключи/Swagger и читает оборудование только своего цеха.
Токен действует 24 часа (`expires_in: 86400`). Каждый запрос с действующим токеном продлевает его ещё на 24 часа; значение токена не меняется. После суток без активности нужен повторный вход. Истёкшие сессии не восстанавливаются; срок API-ключей не продлевается.
Минимальный /healthz открыт для Docker healthcheck; /api/v1/health требует авторизацию.

Администратор добавляет пользователей (логин, пароль от 12 символов, имя, роль, цех), цеха, типы оборудования, оборудование и виды неисправностей. Наблюдения/фото/ИИ — следующие шаги.

## Сервер

Страница: https://pet.oppennec.ru/industrial-vision/
Swagger после входа: https://pet.oppennec.ru/industrial-vision/docs
Схема после входа: https://pet.oppennec.ru/industrial-vision/openapi.json

Подготовленный релиз запускается на сервере:

```bash
sudo ~/services/industrial-vision/start
```

Первого администратора niyaz создать в терминале сервера:

```bash
sudo ~/services/industrial-vision/start admin
```

Пароль вводится интерактивно и не передаётся в командной строке. Затем войдите на странице. Новые пользователи создаются из кабинета.
Данные PostgreSQL сохраняются в volume industrial-vision-postgres-data. Порты БД не публикуются, backend работает с отдельным несуперпользователем iv_app.
Пароли БД генерирует start только на сервере в закрытом private/database.env; повторный запуск их не меняет. Не удаляйте volume при обновлении.

## Разработка

```bash
uv sync --directory backend --locked
```

Задайте DATABASE_URL для отдельной PostgreSQL-БД разработки, ROOT_PATH=/industrial-vision, COOKIE_SECURE=false, ALLOWED_ORIGIN=http://127.0.0.1:5173.

```bash
uv run --directory backend uvicorn app.main:app --reload
npm ci --prefix frontend
npm run dev --prefix frontend
```

Dev frontend проксирует API на 127.0.0.1:8000. Production образ собирает frontend и backend из корня проекта. Серверный Compose требует сгенерированные start настройки БД и существующую сеть proxy.

## Проверки

backend/tests/test_access.py запускается только с IV_TEST_DATABASE_URL, указывающим на изолированную БД iv_step2_test (таблицы очищаются перед тестами).

```bash
uv run --directory backend python -m pytest tests/test_access.py -q
npm run build --prefix frontend
go test -parallel 4 deploy/start.go deploy/start_test.go
go vet deploy/start.go
```

## Телефон

В кабинете есть раздел «Телефон» с адресом API, примером входа сотрудника, Bearer-заголовком и примером Java. HTTPS используется без отключения проверки сертификата. Ключи и пароли не встраиваются в APK и не пишутся в логи.
