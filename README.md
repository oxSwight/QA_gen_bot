# QA Gen Bot

**OpenAPI 3.x / Swagger 2.0 → production-checked Java Maven API test frameworks**, delivered as a ZIP via Telegram or local CLI.

The engine combines a **deterministic scaffold** (build files, base tests, API client, request DTOs) with **model-generated** response DTOs, JSON Schema assets, and JUnit 5 tests. Every deliverable passes a **static quality gate** and **`mvn test` inside Docker** before it is marked production-ready.

---

## Architecture & workflow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Telegram   │     │  run_local   │     │  OpenAPI JSON   │
│  .json doc  │     │  CLI --spec  │     │  (+ base URL)   │
└──────┬──────┘     └──────┬───────┘     └────────┬────────┘
       │                   │                      │
       └───────────────────┼──────────────────────┘
                           ▼
                  ┌────────────────┐
                  │  spec_parser   │  validate JSON, ops, package hint
                  └────────┬───────┘
                           ▼
                  ┌────────────────┐
                  │ build_scaffold │  pom, ConfigManager, BaseTest,
                  │  (protected)   │  WireMock base, *ApiClient, DTOs
                  └────────┬───────┘
                           ▼
                  ┌────────────────┐
                  │   generator    │  LLM: tests, response DTOs, schemas
                  └────────┬───────┘
                           ▼
                  ┌────────────────┐
                  │ merge +        │  strip LLM overrides of protected paths
                  │ structure_fixer│  imports, DTO suffix, WireMock/Hamcrest
                  └────────┬───────┘
                           ▼
                  ┌────────────────┐
                  │  quality_gate  │  JUnit5, schemas, client/DTO closure
                  └────────┬───────┘
                           ▼
                  ┌────────────────┐
                  │ maven_validator│  Docker: mvn test (wiremock profile)
                  └────────┬───────┘
                           ▼
              ┌────────────┴────────────┐
              ▼                         ▼
     BUILD SUCCESS + tests>0      FAILURE → LLM retry / reports-only ZIP
              ▼
     *-qa-framework.zip + GENERATION_REPORT.txt
```

**Deterministic vs probabilistic boundary**

| Layer | Source | Examples |
|-------|--------|----------|
| Scaffold (always) | Templates + OpenAPI graph | `pom.xml`, `PostApiClient.submitTestData()`, nested `MetricDetailsDto` |
| LLM zone | Anthropic API | `*IntegrationTest`, `*WireMockTest`, response DTOs, `schemas/*.json` |

Protected paths cannot be overwritten by the model (`pom.xml`, `client/`, `dto/request/`, base test classes).

---

## Core features

- **Operation-centric or CRUD API clients** derived from the spec (e.g. httpbin `POST /post` + `GET /get` vs Petstore `/pet/{id}`).
- **Transitive request DTO closure** for nested `$ref` in OpenAPI `components.schemas`.
- **Static gate** before Maven: forbidden stacks (TestNG, Allure), JSON Schema usage, `getById` type checks, Surefire-safe test naming.
- **Docker-isolated Maven** with Surefire profiles: default **wiremock** (fast CI slice), optional **live** (`*IntegrationTest` only).
- **Honest delivery**: failed Maven/static gate → ZIP contains reports only, not broken sources.
- **LLM response cache** under `fixtures/*-llm-cache.json` for cheap local regression (`--use-cache --cheap`).
- **Structure fixers** without extra API calls (WireMock/Hamcrest clash, package alignment, integration test rename).

---

## Tech stack

| Area | Technology |
|------|------------|
| Bot / CLI | Python 3.11+, aiogram 3, asyncio |
| Generation | Anthropic Messages API |
| Generated tests | Java 17, JUnit 5, RestAssured 5, WireMock 3, Lombok, Jackson |
| Build verification | Maven 3.9 (Eclipse Temurin 17 Docker image) |
| Config | `python-dotenv`, `src/main/resources/config.properties` in ZIP |

---

## Production setup

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (daemon running) for `mvn test` validation
- Telegram bot token ([@BotFather](https://t.me/BotFather)) if using the bot
- Anthropic API key for generation

### Install

```bash
git clone <your-repo-url>
cd TEST_BOT
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional: pytest
```

### Environment

Copy the template and fill in secrets (never commit `.env`):

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `TG_TOKEN` | Telegram bot | Bot token from BotFather |
| `ANTHROPIC_KEY` | Generation | Anthropic API key |
| `ANTHROPIC_MODEL` | No | Default `claude-sonnet-4-6` |
| `MAVEN_VALIDATION_ENABLED` | No | `true` — run Docker Maven |
| `MAVEN_VALIDATION_STRICT` | No | `true` — warn when ZIP is not production-ready |
| `MAVEN_DOCKER_IMAGE` | No | Default `maven:3.9-eclipse-temurin-17` |
| `MAVEN_TIMEOUT_SEC` | No | Default `300` |
| `MAVEN_MAX_RETRIES` | No | LLM regen attempts after Maven failure |
| `USE_SCAFFOLD` | No | `true` — recommended |

### Run Telegram bot

```bash
python run_bot.py
```

### Run locally (no Telegram)

```bash
# Full pipeline
python run_local.py --spec fixtures/httpbin-live-testing-api.json --base-url https://httpbin.org

# Cached LLM output (no API cost)
python run_local.py --spec fixtures/httpbin-live-testing-api.json \
  --use-cache --cache fixtures/httpbin-llm-cache.json --base-url https://httpbin.org --cheap

# Scaffold + gate + Maven only
python run_local.py --spec fixtures/httpbin-nested-object-ref.json --scaffold-only
```

Output: `out_local/<package>-qa-framework.zip`

### Generated project test profiles

Inside each ZIP:

```bash
mvn test              # wiremock (default): WireMock tests, excludes *IntegrationTest
mvn test -Plive       # live *IntegrationTest against base.url in config.properties
```

Override timeouts for slow public APIs: `-Dread.timeout=90000` (also set in the `live` Maven profile).

---

## Bot commands

| Command / action | Behavior |
|------------------|----------|
| `/start`, `/help` | Usage instructions |
| Send `.json` | Parse OpenAPI; prompt for **base URL** |
| Reply with URL | e.g. `https://api.example.com/v1` |
| `/skip` | Use `servers[0].url` from the spec |
| `/cancel` | Cancel pending URL prompt |
| *(wait)* | Pipeline runs; ZIP sent with status caption |

**Status captions**

- **Production-ready** — static gate OK and Docker `mvn test` succeeded with `Tests run > 0`.
- **Partial** — static gate OK, Maven failed or Docker unavailable (see `MAVEN_BUILD_REPORT.txt`).
- **Failed** — static gate failed; ZIP may contain reports only.

---

## Repository layout

| Path | Role |
|------|------|
| `qa_gen_bot/pipeline.py` | End-to-end orchestration |
| `qa_gen_bot/scaffold.py` | Deterministic project skeleton |
| `qa_gen_bot/generator.py` | LLM file generation |
| `qa_gen_bot/quality_gate.py` | Pre-Maven static validation |
| `qa_gen_bot/maven_validator.py` | Docker `mvn test` |
| `qa_gen_bot/structure_fixer.py` | Deterministic post-processing |
| `fixtures/` | Sample OpenAPI specs and LLM caches |
| `docs/` | Maintainer audit prompts (optional) |

---

## Development

```bash
python -m pytest tests/ -q
```

---

## Security

- Secrets load from environment variables only (`config.py`, `.env`).
- `.env` and `out_local/` are gitignored.
- Do not commit API keys, bot tokens, or customer OpenAPI files with real credentials.

See `.env.example` for the full variable list.

## License

MIT — see [LICENSE](LICENSE). The software is provided **as is**, without warranty.
