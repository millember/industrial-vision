# Industrial Vision — шаг 7 backend

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

Администратор добавляет пользователей (логин, пароль от 12 символов, имя, роль, цех), цеха, типы оборудования, оборудование и виды неисправностей. Фото и осмотры сохраняются; настоящая модель пока не подключена, анализ доступен только в явно включённом mock-режиме.

## Оборудование и база знаний

Все маршруты требуют авторизации (для Android — `Authorization: Bearer <access_token>`).

- `GET /api/v1/equipment` — список доступного оборудования.
- `GET /api/v1/equipment/{equipment_id}` — карточка: `id`, `name`, `inventory_number`, `workshop_id`, `type_id`, `passport`.
- `GET /api/v1/defect-types` — общий каталог: `id`, `name`, `status`, `recommendation`.

Паспорт — текст, введённый администратором при создании оборудования; если он не заполнен, возвращается пустая строка. Рекомендации также заполняет администратор. Каталог общий, привязки дефектов к типу оборудования пока нет. Списки возвращаются JSON-массивами (до 500 записей).

Сотрудник читает карточки только своего цеха, администратор — всех цехов. Чужой и несуществующий ID дают одинаковый `404` с `{"detail":"Оборудование не найдено"}`; без авторизации — `401`.
Карточка не содержит результатов осмотров: они выдаются отдельными маршрутами результата и истории.

## Предварительный анализ фото — шаг 5

`POST /api/v1/inspections/preview` принимает multipart `equipment_id`, `source` (`CAMERA`/`GALLERY`) и один файл `image`. Нужен Bearer-токен; для входа через cookie нужны также `Origin` и `X-IV-Client: browser`. Проверяются права на цех, фактический формат JPEG/PNG, целостность, размер до 10 МиБ и до 20 млн пикселей. EXIF-поворот применяется перед адаптером, метаданные удаляются. Многокадровые изображения не принимаются. Общий multipart-запрос ограничен 10 МиБ + 64 КиБ, в том числе без Content-Length.

Для демонстрации явно задайте `ANALYSIS_MODE=mock` в окружении backend (для Compose — в `.env`). По умолчанию `disabled`: API возвращает `503 MODEL_UNAVAILABLE`. Другие значения останавливают запуск с ошибкой конфигурации.

В mock-режиме ответ preview `200` содержит `analysis_source: MOCK`, `model_version: null`, `status: UNKNOWN`, `color: GRAY`, размеры нормализованного снимка и объяснение заглушки. Распознавание не выполняется. Этот маршрут не сохраняет фото и осмотры; для сохранения используется `POST /api/v1/inspections`.

Ошибки preview возвращаются как `{"error":{"code":"…","message":"…"}}`: 401 — авторизация, 403 — источник браузерного запроса, 404 — оборудование не найдено или чужой цех, 413 — превышение лимита, 415 — неподдерживаемый формат, 422 — повреждённое фото или неверные поля. Шаг 6 с настоящей моделью отложен.

## Сохранение и история — шаг 7

- `POST /api/v1/inspections` — те же multipart-поля, обязательный `Idempotency-Key` (UUID); ответ `201` с сохранённым результатом, `inspection_id`, `photo_id`, `author_id`, `workshop_id` и серверным временем UTC.
- `GET /api/v1/inspections/{id}` — сохранённый результат (`200`) либо сохранённая ошибка.
- `GET /api/v1/photos/{id}` — нормализованное JPEG/PNG после проверки прав, с `Cache-Control: no-store`.
- `GET /api/v1/equipment/{id}/inspections?limit=20&offset=0` — `items/total/limit/offset`, максимум 100 записей на страницу; новые записи первыми. Каждый элемент содержит метаданные, `processing_status`, `result` и `error`.

Для MVP один осмотр содержит одно фото, поэтому `photo_id` равен `inspection_id`. Обе ссылки проверяют цех, в том числе сохранённый на момент осмотра. Сотрудник своего цеха может читать осмотры коллег; администратор читает все цеха.

Ключ повтора ограничен автором и операцией создания осмотра. Повтор с теми же оборудованием, источником и байтами фото возвращает исходные тело и статус; имя файла и multipart-boundary не учитываются. Изменённый запрос с прежним ключом получает `409 IDEMPOTENCY_CONFLICT`, незавершённый — `409 REQUEST_IN_PROGRESS`. Ошибки после резервирования осмотра сохраняются как `FAILED`; для новой попытки нужен новый ключ. Некорректный multipart и отсутствие прав отклоняются до резервирования.

Состояния обработки: `PROCESSING`, `COMPLETED`, `FAILED`. Транзакция БД не удерживается во время анализа или записи файла. Незавершённая обработка старше пяти минут при запуске или следующем обращении переводится в `FAILED/ANALYSIS_INTERRUPTED`. Возможный файл остаётся учтённым по ключу с `cleanup_pending`; при штатном отказе записи выполняется попытка удаления. Автоматическая фоновая очистка после аварии пока не запускается.

## Хранение фото

По умолчанию `PHOTO_STORAGE=local`. В Docker файлы находятся в постоянном volume `industrial-vision-photos-data`, БД — в `industrial-vision-postgres-data`. Для запуска без Docker путь задаётся через `PHOTO_ROOT` (по умолчанию `var/photos`). Не удаляйте volumes при обновлении; резервная копия должна включать БД и фото.

Для новых загрузок можно выбрать `PHOTO_STORAGE=nextcloud`. Укажите `NEXTCLOUD_WEBDAV_URL` — HTTPS WebDAV-адрес заранее созданной закрытой папки, `NEXTCLOUD_USERNAME` и `NEXTCLOUD_APP_PASSWORD`. Подключение использует [WebDAV Nextcloud](https://docs.nextcloud.com/server/stable/developer_manual/client_apis/WebDAV/basic.html). Проверка сертификата включена, перенаправления отключены; таймаут подключения — 10 секунд, ожидания сетевых операций — 30 секунд. Секреты хранятся только в закрытом `.env` сервера.

Выбор backend хранится у каждого осмотра. Смена `.env` требует пересоздания контейнера и влияет на новые фото; старые локальные фото продолжают читаться из прежнего volume. Для старых файлов Nextcloud нужно сохранить его адрес и учётные данные. Автоматического переноса файлов между хранилищами нет. Ошибка выбранного хранилища даёт `503 STORAGE_UNAVAILABLE`, без fallback. Целостность выдаваемого файла проверяется по SHA-256. Nextcloud-клиент протестирован с имитацией WebDAV; подключение к реальному Nextcloud пока не проверялось.

При обычном `docker compose` настройки читаются из `.env`. Серверный `start` явно использует `~/services/industrial-vision/private/database.env` и проверенный `release.env`: параметры приложения добавляйте в закрытый `private/database.env`, затем запускайте `sudo ~/services/industrial-vision/start`. Повторный запуск не перезаписывает этот файл; `release.env` менять нельзя, он фиксирует версию релиза. Сейчас выбор по умолчанию — `PHOTO_STORAGE=local`.

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
uv run --directory backend python -m pytest tests -q
npm run build --prefix frontend
go test -parallel 4 deploy/start.go deploy/start_test.go
go vet deploy/start.go
```

## Телефон

В кабинете есть раздел «Телефон» с адресом API, примером входа сотрудника, Bearer-заголовком и примером Java. HTTPS используется без отключения проверки сертификата. Ключи и пароли не встраиваются в APK и не пишутся в логи.
