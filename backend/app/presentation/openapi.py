"""Russian API guide and examples; runtime validation remains in HTTP schemas/use cases."""
from copy import deepcopy
from app.application.auth import SESSION_TTL_SECONDS

API_DESCRIPTION = """
API осмотров промышленного оборудования. **Модель ИИ пока не подключена.**
Новые снимки анализируются только при явно включённом `MOCK`; демонстрационные результаты не являются распознаванием.

### Как начать с Android
1. Получите логин и пароль у администратора.
2. Вызовите `POST /api/v1/auth/token`, скопируйте `access_token` в **Authorize → AccessToken** (без слова Bearer).
3. Получите `/me`, список оборудования и карточку. Передайте ID выбранного оборудования при загрузке фото.
4. Для каждого нового действия генерируйте UUID в `Idempotency-Key`. При сетевом повторе сохраняйте тот же UUID и содержимое.

Токен действует **24 часа** и продлевается при авторизованных запросах. После суток без активности нужен повторный вход.
Браузерный кабинет, пользователи, API-ключи и сама документация доступны только администратору.
Кабинет использует защищённую HttpOnly-cookie; входите в него обычным способом, браузер передаст cookie автоматически.
Для запросов изменения через cookie нужны `X-IV-Client: browser` и разрешённый `Origin` (браузер задаёт Origin сам).

### Доступ и этапы работы
Сотрудник видит только свой цех. Чужой и несуществующий ID возвращают одинаковый 404.
Рабочий сообщает о возможной неисправности; **инженер** отдельно проверяет оценку;
**мастер или инженер** закрывает проблему после проверки ремонта либо как ошибочную тревогу.
Подтверждение дефекта само по себе не означает ремонт.

### Форматы
Время — UTC, ISO 8601 с `Z`. ID назначает сервер. Примеры ниже — вымышленные данные, не готовые учётные записи.
Префикс установки на сервере — `/industrial-vision`; Swagger добавляет его через поле **Servers**.
Новые операции возвращают ошибки `error.code/message`; старые справочники и вход используют `detail`.
Списки истории, проверок и уведомлений имеют `items/total/limit/offset`; справочники пока возвращают массив до 500 записей.
"""

TAGS = [
    {"name":name, "description":description} for name, description in (
        ("Авторизация", "Вход сотрудника по токену и вход администратора через cookie."),
        ("Профиль", "Текущий пользователь, роль и серверная привязка к цеху."),
        ("Оборудование", "Доступные экземпляры оборудования и текстовые паспорта."),
        ("Справочники", "Цеха, типы оборудования и база знаний с рекомендациями."),
        ("Осмотры", "Загрузка JPEG/PNG, предварительный результат, сохранение и история."),
        ("Сообщения", "Сообщение о возможной неисправности по доступному осмотру."),
        ("Проверка инженером", "Отдельные решения инженера, версии и неизменяемая история."),
        ("Проблемы", "Открытая проблема и её отдельное закрытие после ремонта или ошибочной тревоги."),
        ("Уведомления", "Внутренний список активных мастеров и инженеров своего цеха. FCM пока нет."),
        ("Пользователи", "Создание сотрудников и просмотр списка. Только администратор."),
        ("API-ключи", "Ключи интеграций администратора. Новый секрет показывается один раз."),
        ("Состояние сервера", "Авторизованная проверка доступности API."),
    )
]

OPERATIONS = {
    ("post", "/api/v1/auth/login"):("Авторизация", "Войти в кабинет администратора", "Проверяет логин и пароль администратора и устанавливает HttpOnly/Secure/SameSite=Strict cookie на 24 часа. Возвращает профиль, а не Bearer-токен. Обычный сотрудник получает 403. После пяти неверных паролей вход ограничивается на пять минут."),
    ("post", "/api/v1/auth/token"):("Авторизация", "Получить токен для Android или API", "Доступно без предварительного входа. Возвращает access_token, тип bearer, expires_in в секундах и профиль. Сохраняйте токен на устройстве, передавайте Authorization: Bearer <токен>. Это непрозрачный токен, его не нужно декодировать как JWT. Автоматическое продление сохраняет значение токена."),
    ("post", "/api/v1/auth/logout"):("Авторизация", "Завершить браузерный вход", "Удаляет текущую cookie-сессию на сервере и в браузере. Bearer-токен Android эта операция не отзывает. Нужны браузерные заголовки. Ответ без тела."),
    ("get", "/api/v1/auth/me"):("Профиль", "Получить профиль администратора", "Только вход через cookie администратора. Секреты и хеш пароля не возвращаются."),
    ("get", "/api/v1/me"):("Профиль", "Получить свой профиль", "По токену определяет сотрудника, роль и цех. Передавать или самостоятельно выбирать чужой author_id не требуется."),
    ("get", "/api/v1/health"):("Состояние сервера", "Проверить доступность API", "Требует действующий токен, API-ключ или cookie. Минимальный контейнерный /healthz не входит в эту схему."),
    ("get", "/api/v1/keys"):("API-ключи", "Получить свои API-ключи", "Только администратор через cookie. Возвращает префикс, сроки и отзыв, без значения секрета и хеша. Сам секрет показывается только при создании."),
    ("post", "/api/v1/keys"):("API-ключи", "Выпустить API-ключ", "Только администратор. Срок days — от 1 до 365 дней. Полное значение key доступно только в этом ответе: сохраните его сразу. Фиксированный срок API-ключа не продлевается при запросах."),
    ("delete", "/api/v1/keys/{key_id}"):("API-ключи", "Отозвать свой API-ключ", "Только администратор-владелец ключа. Отзыв действует сразу, значение ключа после этого не авторизует запросы. Ответ без тела."),
    ("get", "/api/v1/users"):("Пользователи", "Получить список сотрудников", "Только администратор. До 500 пользователей; пароли и хеши исключены."),
    ("post", "/api/v1/users"):("Пользователи", "Создать сотрудника", "Только администратор. Логин уникален, пароль от 12 символов. Для любой роли кроме ADMIN обязателен workshop_id. Самостоятельная регистрация и выдача роли отсутствуют."),
    ("get", "/api/v1/workshops"):("Справочники", "Получить доступные цеха", "Сотрудник получает свой цех, администратор — все. Ответ — массив, до 500 записей."),
    ("post", "/api/v1/workshops"):("Справочники", "Создать цех", "Только администратор. Непустое уникальное имя, сервер возвращает назначенный ID."),
    ("get", "/api/v1/equipment-types"):("Справочники", "Получить типы оборудования", "Общий справочник для авторизованных пользователей, до 500 записей."),
    ("post", "/api/v1/equipment-types"):("Справочники", "Создать тип оборудования", "Только администратор. Название уникально."),
    ("get", "/api/v1/equipment"):("Оборудование", "Получить доступное оборудование", "Сотрудник получает оборудование своего цеха, администратор — всех цехов. До 500 записей, обычный массив. Фильтр workshop_id пока не реализован."),
    ("get", "/api/v1/equipment/{equipment_id}"):("Оборудование", "Получить карточку и паспорт", "Возвращает серверные ID, название, инвентарный номер и сохранённый текст паспорта. Пустой паспорт возвращается пустой строкой. Результаты осмотров доступны отдельно через историю."),
    ("post", "/api/v1/equipment"):("Оборудование", "Добавить оборудование", "Только администратор. Укажите существующие цех и тип. Инвентарный номер уникален; паспорт — текст, до 10 000 символов."),
    ("get", "/api/v1/defect-types"):("Справочники", "Получить каталог дефектов и рекомендаций", "Общая база знаний с предварительной серьёзностью WARNING/CRITICAL. Рекомендации вводит администратор. Фильтра по типу оборудования пока нет."),
    ("post", "/api/v1/defect-types"):("Справочники", "Добавить вид неисправности", "Только администратор. Укажите уникальное имя, серьёзность и непустую рекомендацию. Запись справочника сама по себе не означает дефект конкретного оборудования."),
    ("post", "/api/v1/inspections/preview"):("Осмотры", "Проверить фото без сохранения", "Multipart: equipment_id, source и один image. JPEG/PNG до 10 МиБ и 20 млн пикселей; проверяются байты, целостность и EXIF-поворот. Общий запрос ограничен 10 МиБ + 64 КиБ. Включение ANALYSIS_MODE=mock даёт MOCK/UNKNOWN, без ID осмотра и фото. При выключенном анализе — 503; настоящая модель пока отсутствует."),
    ("post", "/api/v1/inspections"):("Осмотры", "Сохранить фото и результат осмотра", "Те же правила фото, что в preview. Обязателен Idempotency-Key (UUID). Сохраняются нормализованное фото, автор, цех и исходный результат. Один осмотр — одно фото, photo_id равен inspection_id. При одинаковом ключе и содержимом возвращаются исходные 201 и JSON; при изменении оборудования, source или байтов — 409. Имя файла и multipart-boundary не учитываются. Новый mock остаётся UNKNOWN: это не распознавание."),
    ("get", "/api/v1/inspections/{inspection_id}"):("Осмотры", "Получить результат и текущую проверку", "До инженерной проверки возвращает сохранённый результат. После неё верхние status/color/review_status отражают решение инженера, latest_review содержит его данные, original_result — неизменённый исходный анализ. PROCESSING даёт 409; FAILED — сохранённую ошибку. Прерванная обработка старше пяти минут переводится в FAILED при обращении или запуске."),
    ("get", "/api/v1/photos/{photo_id}"):("Осмотры", "Скачать защищённое фото", "Выдаёт именно нормализованное изображение осмотра, без исходных EXIF. Проверяет цех и SHA-256. Фото не публикуется по статической ссылке. Ответ — бинарный JPEG/PNG с Cache-Control: no-store; отсутствие или повреждение файла даёт 503."),
    ("get", "/api/v1/equipment/{equipment_id}/inspections"):("Осмотры", "Получить историю оборудования", "Страницы по 1–100 записей, новые первыми (created_at DESC, id DESC). Видны PROCESSING/COMPLETED/FAILED, текущая инженерная оценка и исходный результат. Доступ только к разрешённому цеху."),
    ("post", "/api/v1/inspections/{inspection_id}/reports"):("Сообщения", "Сообщить о возможной неисправности", "Разрешено только для завершённого WARNING/CRITICAL с известным defect_id и неотклонённой оценкой. Комментарий необязателен, до 2000 символов. Сообщение, аудит, проблема и внутренние уведомления создаются одной транзакцией. Получатели — активные мастера и инженеры своего цеха; повторные сообщения группируются. MOCK и MODEL разделены. После закрытия проблемы для нового сообщения нужен новый осмотр. FCM не вызывается."),
    ("get", "/api/v1/reports/{report_id}"):("Сообщения", "Прочитать сообщение", "Автор читает своё сообщение; мастер, инженер и начальник — сообщения своего цеха, администратор — всех цехов. Ответ — снимок данных на момент сообщения, не текущая инженерная оценка."),
    ("get", "/api/v1/notifications"):("Уведомления", "Получить свои внутренние уведомления", "Только конкретный получатель с действующей ролью мастера/инженера в своём цехе. Даже администратор не читает чужие уведомления этим маршрутом. unread_only=true оставляет непрочитанные. Новые первыми; текст обозначает возможную неисправность и явно помечает MOCK."),
    ("patch", "/api/v1/notifications/{notification_id}"):("Уведомления", "Отметить прочтение уведомления", "is_read принимает boolean true/false. Повторное true сохраняет первое read_at, false сбрасывает его. Только своё уведомление; чужой ID скрывается как 404."),
    ("post", "/api/v1/inspections/{inspection_id}/reviews"):("Проверка инженером", "Подтвердить или отклонить оценку", "Только ENGINEER своего цеха. CONFIRMED допускает OK/WARNING/CRITICAL; REJECTED требует UNKNOWN. Непустой комментарий обязателен. expected_review_id: null для первой проверки, иначе ID последнего решения. Устаревшая версия даёт REVIEW_CONFLICT. Решения добавляются в историю, исходный анализ не меняется. Подтверждение дефекта не закрывает проблему и не означает ремонт."),
    ("get", "/api/v1/inspections/{inspection_id}/reviews"):("Проверка инженером", "Получить историю решений инженеров", "Все решения доступного осмотра, новые ID первыми. previous_review_id связывает последовательные версии. Для следующего изменения используйте ID последней записи."),
    ("get", "/api/v1/issues/{issue_id}"):("Проблемы", "Получить проблему и версию сообщения", "Автор сообщения читает свою проблему; ответственные сотрудники — проблемы своего цеха, администратор — все. latest_report_id нужен для безопасного закрытия. closed_at=null означает открытую проблему."),
    ("post", "/api/v1/issues/{issue_id}/close"):("Проблемы", "Закрыть после ремонта или ошибочной тревоги", "Только MASTER/ENGINEER своего цеха. Нужны reason, verification_review_id и expected_report_id из актуальной проблемы. REPAIRED требует нового осмотра того же оборудования, созданного после последнего сообщения, и последней проверки CONFIRMED/OK. FALSE_ALARM требует последнего REJECTED/UNKNOWN; все сообщения группы должны относиться к этому осмотру. MOCK-проверка не закрывает MODEL-проблему. Новое сообщение или устаревшая проверка дают 409. Операция записывается в аудит; обычный повтор с тем же ключом возвращает исходный 200."),
}

ACCOUNT = {"id":7, "login":"worker01", "full_name":"Иванов И.И.", "role":"WORKER", "workshop_id":1}
ADMIN = {**ACCOUNT, "id":1, "login":"admin", "role":"ADMIN", "workshop_id":None}
EQUIPMENT = {"id":125, "name":"Макет узла", "inventory_number":"DEMO-125", "workshop_id":1, "type_id":1, "passport":"Демонстрационный макет, крепление М6."}
PREVIEW = {"equipment_id":125, "object":"Макет узла", "source":"CAMERA", "created_at":"2026-11-11T09:00:00Z", "image":{"width":720,"height":1280},
           "reason":"Режим MOCK: распознавание не выполнялось", "status":"UNKNOWN", "color":"GRAY", "defect":"Не удалось определить",
           "recommendation":"Демонстрационный ответ. Модель не подключена; требуется проверка специалистом.", "analysis_source":"MOCK",
           "review_status":"UNREVIEWED", "model_version":None, "defect_id":None, "defect_code":None, "box":None, "confidence":None}
INSPECTION = {**PREVIEW, "inspection_id":501, "photo_id":501, "author_id":7, "workshop_id":1}
REVIEW = {"review_id":71, "inspection_id":501, "decision":"CONFIRMED", "status":"WARNING", "comment":"На демонстрационном макете подтверждено неплотное прилегание.", "author_id":9, "author_name":"Петров П.П.", "previous_review_id":None, "created_at":"2026-11-11T09:05:00Z"}
ISSUE = {"issue_id":18, "equipment_id":125, "workshop_id":1, "defect_id":2, "analysis_source":"MOCK", "created_at":"2026-11-11T09:02:00Z", "latest_report_id":91, "closed_at":None, "closed_by":None, "close_review_id":None, "close_reason":None, "resolution":None}
REPORT = {"report_id":91, "inspection_id":501, "issue_id":18, "author_id":7, "author_name":"Иванов И.И.", "workshop_id":1, "equipment_id":125, "created_at":"2026-11-11T09:02:00Z", "comment":"Прошу проверить крепление на макете.", "status":"WARNING", "defect_id":2, "analysis_source":"MOCK", "review_status":"UNREVIEWED", "notification_status":"CREATED", "notification_count":2}
NOTIFICATION = {"id":303, "report_id":91, "issue_id":18, "created_at":"2026-11-11T09:02:00Z", "is_read":False, "read_at":None, "message":"ДЕМО MOCK. Иванов И.И. сообщил о возможной неисправности: Макет узла. Нужна проверка.", "analysis_source":"MOCK"}

SCHEMA_EXAMPLES = {
    "Login":{"login":"worker01", "password":"Demo-Password-2026!"},
    "NewUser":{"login":"worker01", "password":"Demo-Password-2026!", "full_name":"Иванов И.И.", "role":"WORKER", "workshop_id":1},
    "Named":{"name":"Цех 1"}, "NamedOut":{"id":1,"name":"Цех 1"},
    "NewKey":{"name":"Демонстрационная интеграция", "days":30},
    "NewEquipment":{key:value for key,value in EQUIPMENT.items() if key != "id"},
    "NewDefect":{"name":"Недокручен", "status":"WARNING", "recommendation":"На демонстрационном макете проверить крепление."},
    "DefectOut":{"id":2, "name":"Недокручен", "status":"WARNING", "recommendation":"На демонстрационном макете проверить крепление."},
    "AccountOut":ACCOUNT, "UserOut":{**ACCOUNT,"active":True}, "EquipmentOut":EQUIPMENT,
    "KeyOut":{"id":11,"name":"Демонстрационная интеграция","prefix":"iv_k_DEMO", "created_at":"2026-11-11T09:00:00Z", "expires_at":"2026-12-11T09:00:00Z", "revoked":False},
    "IssuedKeyOut":{"id":11,"key":"iv_k_DEMO_REPLACE_WITH_REAL_KEY", "expires_at":"2026-12-11T09:00:00Z"},
    "IdOut":{"id":125}, "HealthOut":{"status":"ok"},
    "MobileTokenOut":{"access_token":"iv_s_DEMO_REPLACE_WITH_REAL_TOKEN", "token_type":"bearer", "expires_in":SESSION_TTL_SECONDS,"user":ACCOUNT},
    "ImageSizeOut":PREVIEW["image"], "PreviewOut":PREVIEW, "InspectionOut":INSPECTION, "InspectionDetailOut":INSPECTION,
    "ReviewOut":REVIEW, "IssueOut":ISSUE, "ReportOut":REPORT, "NotificationOut":NOTIFICATION,
    "NewReport":{"comment":"Прошу проверить крепление на макете."}, "NotificationUpdate":{"is_read":True},
    "NewReview":{"decision":"CONFIRMED", "status":"WARNING", "comment":"Подтверждено неплотное прилегание на макете.", "expected_review_id":None},
    "CloseIssue":{"reason":"Крепление проверено после ремонта.", "verification_review_id":72, "expected_report_id":91, "resolution":"REPAIRED"},
    "AnalysisErrorOut":{"code":"NOT_FOUND", "message":"Осмотр не найден"},
    "ErrorEnvelope":{"error":{"code":"NOT_FOUND", "message":"Осмотр не найден"}},
}
SCHEMA_EXAMPLES.update({
    "ReviewsOut":{"items":[REVIEW],"total":1,"limit":20,"offset":0},
    "NotificationsOut":{"items":[NOTIFICATION],"total":1,"limit":20,"offset":0},
    "HistoryItemOut":{"inspection_id":501,"equipment_id":125,"author_id":7,"workshop_id":1,"source":"CAMERA","created_at":INSPECTION["created_at"],"processing_status":"COMPLETED","result":INSPECTION,"error":None},
})
SCHEMA_EXAMPLES["HistoryOut"] = {"items":[SCHEMA_EXAMPLES["HistoryItemOut"]],"total":1,"limit":20,"offset":0}

DEMO_WARNING = {**INSPECTION,"status":"WARNING","color":"ORANGE","defect_id":2,"defect_code":"DEMO_FASTENER",
                "defect":"Недокручен","reason":"Синтетический пример MOCK для документации, не результат распознавания.",
                "recommendation":"На демонстрационном макете проверить крепление."}
REVIEWED_WARNING = {**DEMO_WARNING,"review_status":"CONFIRMED","latest_review":REVIEW,"original_result":DEMO_WARNING}

FIELD_DESCRIPTIONS = {
    "id":"Идентификатор записи, назначенный сервером.", "login":"Логин: латинские буквы, цифры, _, точка и дефис. Уникален.",
    "password":"Пароль. Передаётся только при входе или создании сотрудника, в ответах не возвращается.",
    "full_name":"ФИО сотрудника для отображения.", "role":"Роль: ADMIN — администратор, WORKER — рабочий, MASTER — мастер, ENGINEER — инженер, HEAD — начальник цеха.",
    "workshop_id":"Серверный ID цеха. Цех сотрудника задаёт администратор; для ADMIN может быть null.",
    "equipment_id":"ID конкретного экземпляра оборудования из доступного списка, не результат распознавания фото.",
    "type_id":"ID записи справочника типов оборудования.", "inventory_number":"Уникальный инвентарный номер оборудования.",
    "passport":"Текст паспорта из БД. Пустая строка означает, что паспорт не заполнен.", "name":"Отображаемое название записи.",
    "days":"Фиксированный срок API-ключа, в днях (1–365).", "key":"Секрет нового API-ключа. Показывается один раз.",
    "prefix":"Публичный префикс ключа для поиска; не заменяет полный секрет.", "revoked":"Отозван ли ключ. Отзыв применяется немедленно.",
    "created_at":"Время создания на сервере, UTC в ISO 8601.", "expires_at":"Фиксированный срок окончания API-ключа, UTC.",
    "access_token":"Непрозрачный Bearer-токен. Не JWT; храните защищённо и не записывайте в логи.",
    "token_type":"Схема авторизации: bearer.", "expires_in":"Срок токена в секундах от входа; при авторизованном запросе срок продлевается на 24 часа.",
    "user":"Профиль пользователя, которому выдан токен.", "active":"Разрешён ли вход сотрудника.",
    "source":"Источник фото: CAMERA — камера, GALLERY — галерея.", "image":"Размеры нормализованного снимка после EXIF-поворота.",
    "width":"Ширина изображения в пикселях.", "height":"Высота изображения в пикселях.",
    "object":"Название выбранного оборудования на момент осмотра.",
    "status":"Оценка: OK — норма, WARNING — требует внимания, CRITICAL — предварительно критично, UNKNOWN — недостаточно данных.",
    "color":"Цвет оценки: GREEN/ORANGE/RED/GRAY соответственно OK/WARNING/CRITICAL/UNKNOWN.",
    "defect":"Отображаемая подпись наблюдения.", "defect_id":"ID известного вида дефекта; null при норме или неопределённости.",
    "defect_code":"Код наблюдения; null при отсутствии определённого дефекта.",
    "box":"[x, y, width, height] в пикселях нормализованного фото, начало координат слева сверху; null без области.",
    "confidence":"Уверенность модели от 0 до 1, не вероятность исправности агрегата. У mock и текущей ручной оценки — null.",
    "recommendation":"Сохранённая рекомендация; не свободный ответ ИИ. В mock явно обозначен демонстрационный характер.",
    "analysis_source":"MOCK — явная заглушка; MODEL — результат настоящего адаптера. Сейчас модель не подключена.",
    "model_version":"Версия модели; у MOCK — null.", "review_status":"UNREVIEWED — не проверено; CONFIRMED — подтверждено инженером; REJECTED — оценка отклонена.",
    "reason":"Объяснение результата или непустая причина закрытия, в зависимости от операции.",
    "inspection_id":"ID осмотра. Для MVP его единственная фотография имеет такой же photo_id.", "photo_id":"ID защищённого фото для /photos/{photo_id}.",
    "author_id":"Автор из проверенной авторизации; клиент его не назначает.", "author_name":"ФИО автора на момент записи.",
    "latest_review":"Последнее решение инженера. Появляется после первой проверки.", "original_result":"Неизменённый исходный результат анализа до решений инженера.",
    "review_id":"ID отдельной записи проверки инженера.", "previous_review_id":"Предыдущее решение в цепочке; null у первой проверки.",
    "expected_review_id":"Обязательное поле: null при первой проверке, иначе ID последнего решения. Защищает от перезаписи чужого изменения.",
    "decision":"CONFIRMED подтверждает оценку, REJECTED отклоняет её. Отклонение требует status=UNKNOWN.",
    "comment":"Комментарий: при сообщении необязателен, при проверке инженера обязателен и не пустой; до 2000 символов.",
    "processing_status":"Обработка: PROCESSING, COMPLETED или FAILED; отличается от технической оценки status.",
    "result":"Результат завершённого осмотра либо null.", "error":"Ошибка error.code/message либо null в успешной истории.",
    "code":"Стабильный код ошибки для обработки клиентом.", "message":"Текст для пользователя, без путей хранения и секретов.",
    "items":"Записи страницы.", "total":"Общее число доступных записей до применения limit/offset.",
    "limit":"Размер страницы: 1–100, по умолчанию 20.", "offset":"Число пропускаемых записей, от 0.",
    "unread_only":"true — только непрочитанные, false — все свои уведомления (по умолчанию).",
    "report_id":"ID отдельного сообщения о возможной неисправности.", "issue_id":"ID группы сообщений об открытой проблеме.",
    "notification_status":"CREATED — созданы внутренние уведомления; GROUPED — без повторных уведомлений; NO_RECIPIENTS — активных получателей нет. Не доставка FCM.",
    "notification_count":"Количество новых внутренних уведомлений этого сообщения.",
    "is_read":"Прочитано ли своё уведомление. Строгий boolean, не строка.", "read_at":"UTC-время первого прочтения; null до прочтения или после сброса.",
    "latest_report_id":"ID последнего сообщения проблемы; передайте как expected_report_id при закрытии.",
    "expected_report_id":"Последний известный report_id проблемы. Новое сообщение блокирует закрытие по устаревшей версии.",
    "verification_review_id":"ID актуальной инженерной проверки, служащей основанием закрытия. Для ремонта нужна CONFIRMED/OK нового осмотра.",
    "closed_at":"UTC-время закрытия; null у открытой проблемы.", "closed_by":"ID мастера или инженера, закрывшего проблему.",
    "close_review_id":"Конкретная неизменяемая проверка, по которой закрыли проблему.", "close_reason":"Сохранённая причина закрытия.",
    "resolution":"REPAIRED — проверено после ремонта; FALSE_ALARM — ошибочная тревога. Не смешивает ремонт и отклонение оценки.",
}

BUSINESS_ERRORS = {
    "NOT_FOUND":"Объект не найден или недоступен в вашем цехе", "IDEMPOTENCY_CONFLICT":"Ключ уже использован для другого запроса",
    "REQUEST_IN_PROGRESS":"Операция ещё выполняется", "REPORT_NOT_APPLICABLE":"Сообщение недопустимо для текущей оценки",
    "REVIEW_CONFLICT":"Решение уже изменилось. Обновите осмотр.", "REVIEW_NOT_APPLICABLE":"Проверять можно только завершённый осмотр",
    "ISSUE_CONFLICT":"Появилось новое сообщение. Обновите проблему.", "ISSUE_NOT_VERIFIED":"Нужна актуальная проверка оборудования",
    "ISSUE_ALREADY_CLOSED":"Проблема уже закрыта", "STORAGE_UNAVAILABLE":"Хранилище фотографий недоступно",
    "MODEL_UNAVAILABLE":"Модель не подключена или анализ выключен", "MODEL_INVALID_RESPONSE":"Некорректный ответ адаптера",
    "ANALYSIS_INTERRUPTED":"Обработка осмотра прервана", "IMAGE_TOO_LARGE":"Превышен лимит байтов или пикселей",
    "UNSUPPORTED_IMAGE_TYPE":"Поддерживаются только JPEG и PNG", "INVALID_IMAGE":"Фотография повреждена",
    "VALIDATION_ERROR":"Некорректные поля запроса", "UNAUTHENTICATED":"Требуется авторизация", "FORBIDDEN":"Недостаточно прав или недопустимый источник браузерного запроса",
}


def _sample(schema: dict):
    if "$ref" in schema:
        return deepcopy(SCHEMA_EXAMPLES.get(schema["$ref"].rsplit("/", 1)[1]))
    if schema.get("type") == "array":
        item = _sample(schema["items"])
        return [item] if item is not None else []
    return None


def enrich_schema(schema: dict) -> None:
    for name, component in schema.get("components", {}).get("schemas", {}).items():
        component.setdefault("description", f"Схема {name}. Поля и ограничения приведены ниже; ID в примерах вымышлены.")
        if name in SCHEMA_EXAMPLES:
            component["examples"] = [deepcopy(SCHEMA_EXAMPLES[name])]
        for field, value in component.get("properties", {}).items():
            if field in FIELD_DESCRIPTIONS:
                value.setdefault("description", FIELD_DESCRIPTIONS[field])
            if field == "password":
                value.update(writeOnly=True, format="password")
        if name == "HealthOut":
            component["properties"]["status"]["description"] = "ok — приложение отвечает на авторизованный запрос."
        if name == "NewDefect":
            component["properties"]["status"]["description"] = "Предварительная серьёзность вида дефекта: WARNING или CRITICAL."
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            tag, summary, description = OPERATIONS[(method, path)]
            operation.update(tags=[tag], summary=summary, description=description)
            modern = tag in ("Осмотры", "Сообщения", "Проверка инженером", "Проблемы", "Уведомления")
            for parameter in operation.get("parameters", []):
                name = parameter["name"]
                parameter["description"] = FIELD_DESCRIPTIONS.get(name, "UUID нового действия; при сетевом повторе не менять." if name == "Idempotency-Key" else "Серверный идентификатор доступной записи.")
                if name == "Idempotency-Key":
                    parameter["example"] = "f84bba5e-a356-4c72-b917-7da0d6b54332"
                elif name.endswith("_id"):
                    parameter["example"] = {"equipment_id":125,"inspection_id":501,"photo_id":501,"report_id":91,"issue_id":18,"notification_id":303,"key_id":11}.get(name, 1)
                elif name in ("limit", "offset", "unread_only"):
                    parameter["example"] = {"limit":20, "offset":0, "unread_only":False}[name]
            if method in ("post", "patch", "delete") and path != "/api/v1/auth/token":
                for name, example, text in (("Origin", "https://pet.oppennec.ru", "Для cookie-запросов должен совпадать с разрешённым Origin; браузер задаёт его автоматически."),
                                            ("X-IV-Client", "browser", "Обязателен при входе в кабинет и изменениях через cookie. Для Bearer-запросов не требуется.")):
                    operation.setdefault("parameters", []).append({"name":name,"in":"header","required":tag in ("API-ключи","Пользователи","Справочники","Оборудование") or path in ("/api/v1/auth/login","/api/v1/auth/logout"),"description":text,"schema":{"type":"string"},"example":example})
            request_media = operation.get("requestBody", {}).get("content", {}).get("application/json")
            if request_media:
                sample = _sample(request_media.get("schema", {}))
                if sample is not None:
                    if path == "/api/v1/auth/login":
                        sample = {**sample,"login":"admin"}
                    elif path == "/api/v1/equipment-types":
                        sample = {"name":"Крепёж"}
                    request_media["examples"] = {"Обычный запрос":{"summary":"Учебный пример, значения замените своими", "value":sample}}
                    if path.endswith("/reviews"):
                        request_media["examples"].update({
                            "Отклонить оценку":{"value":{"decision":"REJECTED","status":"UNKNOWN","comment":"На снимке дефект не подтверждён.","expected_review_id":71}},
                            "Подтвердить норму после ремонта":{"value":{"decision":"CONFIRMED","status":"OK","comment":"На новом осмотре крепление проверено.","expected_review_id":None}}})
                    if path.endswith("/close"):
                        request_media["examples"]["Ошибочная тревога"] = {"value":{**sample,"resolution":"FALSE_ALARM","verification_review_id":73,"reason":"Первичная оценка отклонена инженером."}}
            success = "201" if "201" in operation["responses"] else "204" if "204" in operation["responses"] else "200"
            response = operation["responses"][success]
            response["description"] = "Операция выполнена, тело ответа отсутствует." if success == "204" else "Успешный ответ. Пример содержит вымышленные ID."
            for media in response.get("content", {}).values():
                sample = _sample(media.get("schema", {}))
                if path in ("/api/v1/auth/login", "/api/v1/auth/me"):
                    sample = ADMIN
                if path == "/api/v1/equipment-types" and method == "get":
                    sample = [{"id":1,"name":"Крепёж"}]
                if sample is not None:
                    media["examples"] = {"Успешный ответ":{"value":sample}}
                    if path == "/api/v1/inspections/{inspection_id}":
                        media["examples"]["После проверки инженером"] = {"summary":"Синтетический MOCK-пример подтверждённого дефекта", "value":REVIEWED_WARNING}
            errors = {401:["UNAUTHENTICATED"], 422:["VALIDATION_ERROR"]}
            if method != "get" or tag in ("API-ключи", "Пользователи") or path == "/api/v1/auth/me":
                errors[403] = ["FORBIDDEN"]
            if "{" in path:
                errors[404] = ["NOT_FOUND"]
            if path in ("/api/v1/auth/login", "/api/v1/auth/token"):
                errors[429] = ["LOGIN_LIMITED"]
            if method == "post" and tag in ("Справочники", "Оборудование", "Пользователи"):
                errors[409] = ["CONFLICT"]
            if path in ("/api/v1/inspections", "/api/v1/inspections/preview"):
                errors.update({413:["IMAGE_TOO_LARGE"],415:["UNSUPPORTED_IMAGE_TYPE"],422:["VALIDATION_ERROR","INVALID_IMAGE"],503:["MODEL_UNAVAILABLE","STORAGE_UNAVAILABLE"] if path.endswith("inspections") else ["MODEL_UNAVAILABLE"],502:["MODEL_INVALID_RESPONSE"]})
                if path.endswith("inspections"):
                    errors[409] = ["IDEMPOTENCY_CONFLICT","REQUEST_IN_PROGRESS"]
            if path == "/api/v1/inspections/{inspection_id}" or tag == "Осмотры" and path.startswith("/api/v1/photos/"):
                errors[503] = ["STORAGE_UNAVAILABLE"] if "/photos/" in path else ["ANALYSIS_INTERRUPTED","MODEL_UNAVAILABLE","STORAGE_UNAVAILABLE"]
                if "/inspections/" in path:
                    errors[409] = ["REQUEST_IN_PROGRESS"]
            if method == "post" and tag in ("Сообщения", "Проверка инженером", "Проблемы"):
                errors[409] = ["IDEMPOTENCY_CONFLICT","REQUEST_IN_PROGRESS"] + ({"Сообщения":["REPORT_NOT_APPLICABLE"],"Проверка инженером":["REVIEW_CONFLICT","REVIEW_NOT_APPLICABLE"],"Проблемы":["ISSUE_CONFLICT","ISSUE_NOT_VERIFIED","ISSUE_ALREADY_CLOSED"]}[tag])
            for code, names in errors.items():
                if path == "/api/v1/auth/token" and code == 403 or path == "/api/v1/auth/logout" and code in (401,422):
                    continue
                examples = {}
                for name in names:
                    message = BUSINESS_ERRORS.get(name, "Вход временно ограничен" if code == 429 else "Конфликт данных")
                    if code == 401 and path in ("/api/v1/auth/login", "/api/v1/auth/token"):
                        message = "Неверный логин или пароль"
                    value = {"error":{"code":name,"message":message}} if modern else {"detail":message}
                    if not modern and code == 422:
                        value = {"detail":[{"type":"missing","loc":["body","login"],"msg":"Field required","input":{}}]}
                    examples[name] = {"summary":message,"value":value}
                operation["responses"][str(code)] = {"description":" / ".join(example["summary"] for example in examples.values()),"content":{"application/json":{"examples":examples}}}
                if code == 429:
                    operation["responses"][str(code)]["headers"] = {"Retry-After":{"description":"Число секунд до следующей попытки входа.","schema":{"type":"integer"},"example":300}}
            if path.startswith("/api/v1/photos/"):
                operation["responses"]["200"] = {"description":"Бинарный JPEG/PNG нормализованного снимка. Cache-Control: no-store.","content":{mime:{"schema":{"type":"string","format":"binary"}} for mime in ("image/jpeg","image/png")}}


def configure_openapi(app) -> None:
    original = app.openapi
    def documented_schema():
        if app.openapi_schema is None:
            result = original()
            enrich_schema(result)
        return app.openapi_schema
    app.openapi = documented_schema
