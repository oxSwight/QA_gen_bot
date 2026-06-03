# Фикстуры для проверки QA Gen Bot

## Реальные публичные API

| Файл | Источник | Base URL (для бота или `/skip`) |
|------|----------|----------------------------------|
| `jsonplaceholder-api.json` | [JSONPlaceholder](https://jsonplaceholder.typicode.com) — OpenAPI 3, упрощённый | `https://jsonplaceholder.typicode.com` |
| `petstore-swagger-api.json` | [Swagger Petstore](https://petstore.swagger.io/v2/swagger.json) — Swagger 2.0, официальная спека | `https://petstore.swagger.io/v2` |
| `httpbin-live-testing-api.json` | Httpbin-like: nested `TestPayload`, POST `/post` + GET `/get` | `https://httpbin.org` |
| `httpbin-nested-object-ref.json` | Минимальная спека для nested `$ref` (compile-only) | `https://httpbin.org` |

**Рекомендация для первого прогона:** `jsonplaceholder-api.json` — простой CRUD `/posts`, стабильные ответы, без OAuth.

Petstore богаче (20 операций, вложенные `Pet`/`Category`), но сложнее для Maven/LLM.

## Telegram

1. Отправь боту `.json` из этой папки.
2. На запрос base URL пришли URL из таблицы (или `/skip`, если URL уже в `servers` / `host`).

## Локально (без Telegram)

```bash
python run_local.py --spec fixtures/jsonplaceholder-api.json --base-url https://jsonplaceholder.typicode.com
```

Petstore **без Claude** (кэш LLM + Maven):

```bash
python scripts/build_petstore_llm_cache.py   # если обновился out_local ZIP
python run_local.py --spec fixtures/petstore-swagger-api.json --use-cache --cache fixtures/petstore-llm-cache.json --base-url https://petstore.swagger.io/v2 --cheap
```

Httpbin (после успешного `run_local` с полным ZIP):

```bash
python run_local.py --spec fixtures/httpbin-live-testing-api.json --base-url https://httpbin.org --save-cache
python scripts/build_httpbin_llm_cache.py
python run_local.py --spec fixtures/httpbin-live-testing-api.json --use-cache --cache fixtures/httpbin-llm-cache.json --base-url https://httpbin.org --cheap
```

Сгенерированные проекты: `mvn test` (WireMock, default) · `mvn test -Plive` (только `*IntegrationTest`).

### LLM cache files (`*-llm-cache.json`)

Optional: pre-recorded model output for `run_local.py --use-cache --cheap` (no API cost). Safe to commit; they contain generated Java/tests only, no secrets.

### Not in the repo (gitignored)

- `out_local/` — ZIPs and local `llm_cache.json` from your runs
- `.env` — tokens and API keys
