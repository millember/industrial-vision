# Industrial Vision

Серверная часть проекта хакатона «Кибер 102»: состояние промышленного оборудования, осмотры и интеграция компьютерного зрения.

## Первый шаг

Реализован каркас FastAPI с проверкой работоспособности и Swagger. Подготовлены контракты Android и модели.
БД, авторизация, приём фотографий и реальный анализ добавляются на следующих шагах.

После публикации:

- Страница проекта: https://pet.oppennec.ru/industrial-vision/
- Проверка API: https://pet.oppennec.ru/industrial-vision/api/v1/health
- Swagger: https://pet.oppennec.ru/industrial-vision/docs
- OpenAPI: https://pet.oppennec.ru/industrial-vision/openapi.json

Страница и карточки используют существующий React-каталог home-server. API — отдельный сервис этого репозитория.
При недоступном API страница показывает отсутствие связи, без фиктивного успешного результата.

## Стек

Python 3.12, FastAPI, Uvicorn, uv, Docker Compose. Зависимости объявлены в backend/pyproject.toml и зафиксированы в backend/uv.lock.

## Локальный запуск через uv

Из корня проекта:

```bash
uv sync --directory backend --locked
uv run --directory backend --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health: http://127.0.0.1:8000/api/v1/health, Swagger: http://127.0.0.1:8000/docs.

## Локальный Docker

```bash
cp .env.example .env
docker compose up --build
```

Это режим разработки с reload и bind mount исходников. API_PORT в .env задаёт порт ноутбука, по умолчанию 8000.
Остановка: `docker compose down`.

## Сервер

`compose.server.yaml` использует сеть proxy существующего Traefik. Порты хоста и исходники не монтируются, reload отключён.
Образ собирается через `uv sync --frozen --no-dev`, работает от UID/GID 10001 с read-only корневой ФС.
ROOT_PATH=/industrial-vision обеспечивает корректные ссылки Swagger после удаления префикса маршрутизатором.

Релиз хранится в ~/services/industrial-vision/releases/<commit>/. REVISION и SHA256SUMS проверяются до запуска.
release.env задаёт RELEASE_ID для тега образа и его revision label. Это генерируемые метаданные релиза, не файл с секретами.
Точный путь релиза выбирается при публикации; из него на сервере запускается:

```bash
sudo docker compose -p industrial-vision --env-file release.env -f compose.server.yaml up -d --build --wait
```

Запуск требует отсутствия чужой блокировки ~/services/.home-server-deploy-lock и выполняется под этой общей блокировкой.
После готовности контейнера deploy/traefik.yaml атомарно устанавливается как отдельный dynamic/industrial-vision.yaml.
Карточки и страница публикуются штатной сборкой/синхронизацией каталога; публикация фронтенда не запускает backend.

## Документы

- [Архитектура](docs/architecture.md)
- [Общий план команды](INDUSTRIAL_VISION_PLAN.md)
- [План Нияза](INDUSTRIAL_VISION_BACKEND_NIYAZ.md)
- [Контракт Android](docs/api_contract.md)
- [Контракт модели](docs/model_contract.md)
- [Критерии первого запуска](docs/steps/01-bootstrap.md)

## Текущий API

```http
GET /api/v1/health
```

Ответ: `{"status": "ok"}`. /docs и /openapi.json генерирует FastAPI.
