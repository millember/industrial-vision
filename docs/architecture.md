# Архитектура Industrial Vision

Backend: presentation → dependency factory → application/use_case → Protocol-port → infrastructure/repository (команды) или infrastructure/queries → frozen DTO (чтения).
Domain/application не импортируют FastAPI, Pydantic или SQLAlchemy. ORM и транзакции портовых операций — в infrastructure; HTTP-схемы и права — в presentation. Сессии и токены отделены от HTTP. AuthService получает AuthStore/Passwords через конструктор.

Frontend: app → domain ← data. Компоненты получают CabinetRepository через контекст; только app/composition создаёт HttpCabinetRepository. Domain содержит модели и контракт, data — fetch и сериализацию.

Стек RS не копируется: FastAPI/Pydantic + SQLAlchemy/Alembic/psycopg, PostgreSQL 17, React/TanStack Query. Данные предметной области и permission-коды RS не используются.

Образ собирается из отдельных backend/ и frontend/. Traefik направляет /industrial-vision на backend, который отдаёт frontend и API. Порты хоста не публикуются. БД подключена только к внутренней сети data, постоянный volume независим от релизов.

Осмотры: InspectionsUseCase → Protocol-порты команд, queries и PhotoStorage. Короткие PostgreSQL-транзакции резервируют ключ повтора и фиксируют результат; анализ и запись фото выполняются вне транзакции. Таблица inspections хранит снимок автора/цеха, исходный hash запроса, состояние обработки, JSON результата/ошибки и метаданные единственного фото. В MVP photo_id совпадает с inspection_id. История отделяет processing_status от оценки оборудования.

PhotoStorage имеет локальную и Nextcloud WebDAV реализации; выбор новых загрузок задаётся PHOTO_STORAGE. Backend и серверный случайный ключ сохраняются с осмотром. Фото выдаются только защищённым API с проверкой цеха и контрольной суммы. Локальные фото находятся в отдельном постоянном volume, не в образе или /tmp. После аварии просроченные PROCESSING переводятся в FAILED с cleanup_pending; активные файлы автоматически не удаляются. Настоящая модель пока не подключена.

ReportingUseCase использует порты команд и queries; правила допустимого осмотра и ролей находятся в domain/reporting. PostgreSQL-транзакция создаёт Report, Audit, Issue, Notification и сохранённый ответ ReportRequest. Ключ повтора ограничен автором и осмотром; PostgreSQL transaction advisory lock защищает параллельные повторы. Частичный уникальный индекс группирует открытые проблемы по оборудованию, цеху, дефекту и источнику MOCK/MODEL. Уникальная пара issue/recipient предотвращает повторное внутреннее уведомление. Получатели до появления назначений — активные мастера и инженеры своего цеха. Queries проверяют автора/роль/цех сообщения, а уведомления — конкретного получателя, его текущую роль и цех. FCM пока не подключён.

ReviewUseCase → порты ReviewRepository/ReviewQueries. Review — отдельная добавляемая запись; Inspection.result неизменяем. Domain/reviews строит текущую оценку, сохраняя original_result и latest_review. Последние решения читаются пакетно, без запроса на каждый осмотр. expected_review_id проверяется под блокировкой строки осмотра; WorkflowRequest хранит ответы повторов отдельно для review/close. Закрытие требует актуальной проверки и expected_report_id, сохраняет основание и аудит. Порядок блокировок команд: осмотр → общая advisory-блокировка группы проблемы → строка Issue. Эту блокировку используют и новые сообщения, и закрытие, включая переход к новой группе после ремонта. MOCK и MODEL не смешиваются. FALSE_ALARM отличается от REPAIRED.

Русские описания, теги и примеры OpenAPI находятся в presentation/openapi.py, отдельно от доменных правил и runtime-валидации. Схемы ответа и безопасности формируются FastAPI; документация обогащает их примерами и описанием прав. Примеры проверяются теми же Pydantic-схемами, что HTTP, а ссылки OpenAPI — на разрешимость.

Разделение ролей: администратор — кабинет, ключи, пользователи, справочники и документация; сотрудники — вход /auth/token и API своего цеха. Схема и кабинет не открываются по токену сотрудника. Пароли Argon2, cookie HttpOnly/Secure/Strict, только хеши токенов/ключей в БД. Минимальный healthz используется контейнером.
