# Промпт: аудит Maven / компиляции QA Gen Bot

Скопируй блок ниже в ваш LLM-редактор (с `@workspace` или всем репозиторием в контексте).

---

## Промпт (копировать отсюда)

```
Ты — Principal Build Engineer + Staff QA Architect. Задача: провести жёсткий аудит репозитория QA Gen Bot и улучшить всё, что влияет на компиляцию Java, `mvn test` в Docker, Surefire и доставку production-ready ZIP.

### Контекст пайплайна

OpenAPI JSON → `spec_parser.py` → `generator.py` (Claude, XML) → `xml_parser.py` →
`strip_llm_protected` + `merge_with_scaffold` (`scaffold.py`) →
`apply_all_structure_fixes` (`structure_fixer.py`) →
`validate_generated_project` (`quality_gate.py`) →
`validate_maven_project` (`maven_validator.py`, Docker `mvn -B test`) →
опционально regen Claude по `MAVEN_RETRY_HINT`.

Локальный прогон без Telegram: `run_local.py` (флаги `--use-cache`, `--save-cache`, `--cheap`, `--no-maven`).

### Scope (ТОЛЬКО это)

- Компиляция `main` и `test` (javac, Lombok, пакеты, imports, missing classes).
- `pom.xml` / Surefire excludes / dependency scopes.
- Scaffold: DTO из OpenAPI (`_build_request_dto_files`, `_collect_component_schemas_for_dto`, `nested_component_dto_name`, protected `/dto/request/`).
- Merge LLM + scaffold (`PROTECTED_FRAGMENTS`, перезапись pom/client/base).
- Structure fixers: DTO suffix, rename BaseTest → *IntegrationTest, WireMock/Hamcrest, client sync.
- Парсинг лога Maven (`_parse_maven_output`, Tests run / Failures / Errors, BUILD SUCCESS vs exit_code).
- Static gate: что должен ловить ДО Maven, но сейчас пропускает.

### Вне scope

- UI Telegram, pending jobs, стоимость API, дизайн промптов «в целом» (только если влияют на compile/Maven).
- Реальная доступность внешних API (httpbin.org, production-env.com) — только как причина Errors, не как «починить интернет».

### Известные классы сбоев (проверь, закрыты ли в коде)

1. Nested DTO: поле `MetricDetailsDto` в `PostInputDto`, но нет `.java` (object `$ref`, не только array `items.$ref`).
2. `OrderItem` vs `OrderItemDto` — рассинхрон имён LLM и scaffold.
3. `OrdersPositiveTest` на `BaseTest` → `UnknownHost` на URL из OpenAPI; Surefire исключает только `*IntegrationTest`.
4. Защита `/dto/request/` vs вырезание `dto/response` от LLM.
5. `tests_run=None` при compile failure; ложный pass при BUILD SUCCESS без `Tests run:`.
6. `sync_client_dto_type` / protected scaffold DTO vs LLM `OrderRequest`.
7. ApiClient: `getById(long)` vs UUID `orderId` String.
8. Regen Claude не чинит compile, если protected scaffold перетирает фиксы.

### Файлы — обязательный проход

- `qa_gen_bot/scaffold.py`, `scaffold_hints.py`, `templates/pom.xml`, `templates/ApiClient.java`, `templates/DtoInput.java`
- `qa_gen_bot/structure_fixer.py`, `quality_gate.py`, `maven_validator.py`, `pipeline.py`
- `qa_gen_bot/generator.py`, `xml_parser.py`, `prompts.py` (MAVEN_RETRY_HINT, SYSTEM_PROMPT)
- `tests/test_scaffold.py`, `tests/test_maven_validator.py`, `tests/test_component_dto_suffix.py`, `tests/test_rename_integration_tests.py`
- `run_local.py`, `fixtures/order-management-api.json`, `scripts/build_order_llm_cache.py`

### Что сделать (пошагово)

1. **Карта рисков** — таблица: симптом в логе Maven → корневая причина → файл/функция → severity P0/P1/P2.
2. **Gap analysis static gate** — список проверок, которые должны быть до Docker (missing DTO class, import несуществующего типа, package ≠ path, тест на BaseTest без Integration в имени при Docker profile).
3. **Gap analysis fixers** — детерминированные патчи без LLM; где fixer может ухудшить код.
4. **Gap analysis maven_validator** — полнота парсинга (compile error vs test error vs UnknownHost); предложи надёжный критерий `passed`.
5. **Конкретные патчи** — минимальные diff’ы с кодом (не «переписать всё»). Для каждого P0: тест в `tests/` воспроизводящий баг.
6. **Регрессионные фикстуры** — какие OpenAPI JSON добавить в `fixtures/` (httpbin с object $ref, order с array $ref, minimal 1-path).
7. **Чеклист локальной верификации** — команды:
   - `python -m pytest tests/ -q`
   - `python run_local.py --spec fixtures/order-management-api.json --use-cache --cache fixtures/order-management-llm-cache.json`
   - scaffold-only + maven для новых фикстур

### Формат ответа

## Executive summary (5–10 строк)

## P0 / P1 / P2 (каждый пункт)
- **Симптом**
- **Repro** (спека или команда)
- **Root cause** (файл:строка)
- **Fix** (конкретная логика)
- **Test** (имя нового test_*)

## Предлагаемые изменения
(готовые патчи или pseudocode)

## Что НЕ трогать и почему

### Ограничения при правках

- Не ломать `USE_SCAFFOLD=true` по умолчанию.
- Не ослаблять protected paths (pom, base, client, dto/request) без compensating gate.
- Surefire в Docker должен гонять только WireMock-local тесты; интеграционные — исключены или переименованы.
- Минимальный scope diff; следовать стилю существующих модулей.
- Каждый P0 fix → unit test; по возможности один integration test с `validate_maven_project` (mock или skip if no Docker).

Начни с чтения кода и тестов, затем выдай отчёт и патчи. Не задавай уточняющих вопросов — если неясно, задокументируй assumption.
```

---

## Как использовать

1. Открой репозиторий `TEST_BOT` в вашей IDE.
2. Новый чат → вставь промпт → добавь `@workspace` или `@qa_gen_bot`.
3. При необходимости приложи последний `MAVEN_BUILD_REPORT.txt` из ZIP и путь к `.json` спеки.
4. Попроси в конце: «примени все P0 патчи и прогони pytest».

## Быстрый промпт (короткая версия)

```
Аудит @workspace: всё, что влияет на javac compile и Docker mvn test в QA Gen Bot.
Фокус: scaffold DTO/refs, structure_fixer, quality_gate gaps, maven_validator parsing, pom surefire excludes.
Выдай P0/P1 с repro, file:line, minimal fix + pytest. Затем внедри P0.
Известные баги: MetricDetailsDto missing, OrderItemDto suffix, BaseTest hits fake URL, compile vs tests_run=None.
```
