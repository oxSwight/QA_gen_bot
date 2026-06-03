# Промпт: аудит результата генерации QA Gen Bot

Скопируй блок ниже в ваш LLM-редактор. В контекст приложи **артефакты прогона**, а не только исходники бота.

---

## Что приложить к промпту

| Артефакт | Зачем |
|----------|--------|
| `*-qa-framework.zip` (распакованный или `@` папка) | Фактический deliverable |
| Исходная OpenAPI/Swagger `.json` | Эталон контракта |
| `GENERATION_REPORT.txt` или `GENERATION_FAILED.txt` | Лог пайплайна |
| `MAVEN_BUILD_REPORT.txt` (если есть) | Хвост Maven |
| Caption/статус из бота: ✅ production-ready / ⚠️ partial | Заявленное качество |
| (опционально) `fixtures/*-llm-cache.json` | Что дала модель до scaffold |

**Минимум:** ZIP + spec JSON. Без ZIP анализ будет теоретическим — так и укажи в отчёте.

---

## Промпт (копировать отсюда)

```
Ты — Staff QA Architect + Java build reviewer. Задача: **оценить уже сгенерированный** тестовый фреймворк (ZIP от QA Gen Bot), а не переписывать сам бот.

### Что должен был сделать бот (эталон)

Telegram/CLI получил OpenAPI 3.x или Swagger 2.0 и выдал Maven-проект:

1. **Детерминированный scaffold (всегда):** `pom.xml`, `ConfigManager`, `BaseTest`, `WireMockBaseTest`, `WireMock405Test`, `*ApiClient` на primary resource, request DTO в `dto/request/`, `config.properties` с `base.url`.
2. **Зона LLM:** response DTO, JSON Schema в `src/test/resources/schemas/`, тесты в `com.{package}.tests.*`.
3. **Проверки перед ZIP:** static gate (`quality_gate`) → Docker `mvn -B test` (профиль `wiremock` по умолчанию: Surefire исключает `*IntegrationTest`, `*NegativeTest`, `*SchemaTest`). Live: `mvn test -Plive`.
4. **Маркировка:** «Production-ready» только если static gate OK **и** Maven BUILD SUCCESS с `Tests run: N > 0`. При Maven FAIL в ZIP только отчёты (исходники не включаются).

Бот **не обязан** покрыть все path/методы спеки — ожидается **репрезентативный** CRUD+WireMock+интеграционный каркас на primary resource.

### Твоя роль

Сравни **факт** (файлы в ZIP) с **контрактом** (OpenAPI) и с **заявленным статусом** (отчёты). Ответь: можно ли отдать ZIP QA-инженеру «как есть», что сломается на реальном стенде, что не соответствует спеке.

### Scope анализа

**Включить:**
- Структура проекта, пакеты, соответствие путей и `package`.
- Scaffold vs LLM: дубли, protected paths, рассинхрон имён (`*InputDto`, `*Dto`, `*ApiClient`).
- Компиляция: признаки в коде (типы id `long`/`String`, builder, imports, DTO closure).
- Тестовая стратегия: WireMock vs live (`BaseTest` / `*IntegrationTest`), JSON Schema, негатив 405, ≥3 test classes.
- Соответствие OpenAPI: primary resource, POST body, path params, игнорированные теги/модули (store, user, multipart, oneOf).
- Отчёты: согласованы ли `GENERATION_REPORT`, `MAVEN_BUILD_REPORT` и содержимое ZIP.
- Практическая ценность: README, `config.properties`, можно ли запустить `mvn test` локально без Docker бота.

**Исключить (если не видно в артефактах):**
- Рефакторинг исходников `qa_gen_bot/*.py`.
- Стоимость API, очереди Telegram, инфраструктура VPS.
- Починку недоступного внешнего API — только отметь риск UnknownHost для `*IntegrationTest`.

### Известные классы расхождений (проверь в этом ZIP)

1. **Чужой package в тестах** — кэш/merge от другой спеки (`microserviceautomationap` в petstore).
2. **Swagger 2 vs OAS3** — `definitions` + `parameters[in=body]`; nested `Category`/`Tag`/`Order`/`User` DTO.
3. **LLM тесты на Store/User** при одном `PetApiClient` — RestAssured `given()` на `/store/*`, `/user/*`.
4. **int64 vs Integer vs long literals** — `.id(1)` vs `.id(1L)` vs `getById(1)`.
5. **Response DTO в `src/test/.../dto/response`** вместо `src/main/...`.
6. **JSON Schema** — есть ли файлы, совпадают ли с `matchesJsonSchemaInClasspath("schemas/...")`.
7. **Ложный production-ready** — Maven OK только на WireMock; интеграционные тесты не гонялись в Docker.
8. **Спека богаче генерации** — Petstore 20 ops, в ZIP только `/pet` client.

### Метод (обязательный порядок)

1. **Inventory** — таблица: путь → роль (scaffold/LLM) → краткое назначение.
2. **Spec mapping** — таблица: 5–15 ключевых operations из OpenAPI → покрыт ли тестом/client/DTO (да/частично/нет).
3. **Build & gate forensics** — по отчётам и коду: compile risks, Surefire profile, что реально запускалось.
4. **QA engineer walkthrough** — 5 шагов: распаковать → `config.properties` → `mvn test` → что упадёт на live → что править 5–15 мин.
5. **Вердикт** — одна из меток:
   - **SHIP** — можно отдавать команде;
   - **SHIP with caveats** — compile OK, live/покрытие ограничены;
   - **HOLD** — compile/gate риск или вводит в заблуждение;
   - **REJECT** — не компилируется или неверный проект.

### Self-correction (перед финалом)

- Не путай «Maven прошёл в Docker» с «все тесты валидны на production API».
- Не требуй 100% покрытия OpenAPI, если бот честно сделал primary-resource framework.
- Если нет ZIP — вердикт **INSUFFICIENT INPUT**, не выдумывай файлы.
- Отдели дефекты **генерации** от дефектов **целевого API** (demo petstore, fake URL).

### Формат ответа

## Executive summary
(вердикт SHIP/HOLD/…, 1 абзац)

## Соответствие заявлению бота
| Заявление | Факт в ZIP | OK? |

## Inventory артефактов
(таблица файлов)

## OpenAPI → покрытие
(таблица operations)

## Scaffold ↔ LLM seam
(имена, DTO, client, типичные рассинхроны)

## Тесты и исполняемость
(WireMock / Integration / Surefire / Schema)

## Риски на реальном стенде
(bullet list)

## P0 / P1 / P2 для доработки ZIP вручную
(конкретные файлы и правки, без переписывания бота)

## Рекомендации для следующей генерации
(1–3 предложения: какая спека, base URL, флаги CLI)

## Assumptions
(что не было в контексте)

Начни с inventory и spec mapping. Не задавай уточняющих вопросов — если данных мало, перечисли assumptions и снизь уверенность.
```

---

## Как использовать

1. Распакуй ZIP в папку или укажи `@out_local/swaggerpetstore-qa-framework.zip`.
2. Добавь `@fixtures/petstore-swagger-api.json` (или твою спеку).
3. Вставь промпт + `@GENERATION_REPORT.txt` из архива.
4. Для сравнения двух прогонов: два ZIP + «сравни SHIP/HOLD и регрессии».

## Быстрый промпт (короткая версия)

```
Аудит **результата** QA Gen Bot (не кода бота): распакованный ZIP + OpenAPI JSON + GENERATION_REPORT + MAVEN_BUILD_REPORT.

Оцени: inventory, spec→coverage, scaffold/LLM seam, compile/Surefire честность, вердикт SHIP|SHIP with caveats|HOLD|REJECT.

Проверь: чужой package, PetApiClient vs /store|/user tests, int64/Long, missing schemas, ложный production-ready (только WireMock в Docker).

Формат: executive summary → таблицы → P0/P1 ручные правки ZIP → assumptions.
```

## Пример вызова (Petstore)

```
[вставь полный промпт]

Контекст:
- Spec: @fixtures/petstore-swagger-api.json
- ZIP: @out_local/swaggerpetstore-qa-framework.zip
- base.url: https://petstore.swagger.io/v2
- Статус последнего run_local: OK Production-ready, 29 files, 43s
```
