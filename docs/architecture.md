# Архитектура Industrial Vision

Backend: presentation → dependency factory → application/use_case → Protocol-port → infrastructure/repository (команды) или infrastructure/queries → frozen DTO (чтения).
Domain/application не импортируют FastAPI, Pydantic или SQLAlchemy. ORM и транзакции портовых операций — в infrastructure; HTTP-схемы и права — в presentation. Сессии и токены отделены от HTTP. AuthService получает AuthStore/Passwords через конструктор.

Frontend: app → domain ← data. Компоненты получают CabinetRepository через контекст; только app/composition создаёт HttpCabinetRepository. Domain содержит модели и контракт, data — fetch и сериализацию.

Стек RS не копируется: FastAPI/Pydantic + SQLAlchemy/Alembic/psycopg, PostgreSQL 17, React/TanStack Query. Данные предметной области и permission-коды RS не используются.

Образ собирается из отдельных backend/ и frontend/. Traefik направляет /industrial-vision на backend, который отдаёт frontend и API. Порты хоста не публикуются. БД подключена только к внутренней сети data, постоянный volume независим от релизов.

Осмотры: InspectionsUseCase → Protocol-порты команд, queries и PhotoStorage. Короткие PostgreSQL-транзакции резервируют ключ повтора и фиксируют результат; анализ и запись фото выполняются вне транзакции. Таблица inspections хранит снимок автора/цеха, исходный hash запроса, состояние обработки, JSON результата/ошибки и метаданные единственного фото. В MVP photo_id совпадает с inspection_id. История отделяет processing_status от оценки оборудования.

PhotoStorage имеет локальную и Nextcloud WebDAV реализации; выбор новых загрузок задаётся PHOTO_STORAGE. Backend и серверный случайный ключ сохраняются с осмотром. Фото выдаются только защищённым API с проверкой цеха и контрольной суммы. Локальные фото находятся в отдельном постоянном volume, не в образе или /tmp. После аварии просроченные PROCESSING переводятся в FAILED с cleanup_pending; активные файлы автоматически не удаляются. Настоящая модель пока не подключена.

Разделение ролей: администратор — кабинет, ключи, пользователи, справочники и документация; сотрудники — вход /auth/token и API своего цеха. Схема и кабинет не открываются по токену сотрудника. Пароли Argon2, cookie HttpOnly/Secure/Strict, только хеши токенов/ключей в БД. Минимальный healthz используется контейнером.
