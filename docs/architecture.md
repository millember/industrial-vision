# Архитектура Industrial Vision

Backend: presentation → dependency factory → application/use_case → Protocol-port → infrastructure/repository (команды) или infrastructure/queries → frozen DTO (чтения).
Domain/application не импортируют FastAPI, Pydantic или SQLAlchemy. ORM и транзакции портовых операций — в infrastructure; HTTP-схемы и права — в presentation. Сессии и токены отделены от HTTP. AuthService получает AuthStore/Passwords через конструктор.

Frontend: app → domain ← data. Компоненты получают CabinetRepository через контекст; только app/composition создаёт HttpCabinetRepository. Domain содержит модели и контракт, data — fetch и сериализацию.

Стек RS не копируется: FastAPI/Pydantic + SQLAlchemy/Alembic/psycopg, PostgreSQL 17, React/TanStack Query. Данные предметной области и permission-коды RS не используются.

Образ собирается из отдельных backend/ и frontend/. Traefik направляет /industrial-vision на backend, который отдаёт frontend и API. Порты хоста не публикуются. БД подключена только к внутренней сети data, постоянный volume независим от релизов.

Разделение ролей: администратор — кабинет, ключи, пользователи, справочники и документация; сотрудники — вход /auth/token и API своего цеха. Схема и кабинет не открываются по токену сотрудника. Пароли Argon2, cookie HttpOnly/Secure/Strict, только хеши токенов/ключей в БД. Минимальный healthz используется контейнером.
