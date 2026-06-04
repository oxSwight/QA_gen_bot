# ADR: Mode B — Repo / `target/generated-sources`

## Status

Accepted (foundation implemented in `qa_gen_bot/codegen`, `pipeline_mode_b.py`).

## Context

Mode A (Quick Start) ships a self-contained ZIP with hand-crafted `*ApiClient` in `src/test/java/client/`.

Enterprise teams often already use **openapi-generator** → classes under `target/generated-sources/openapi/` and keep tests in `src/test/java`.

## Decision

- **Mode A (`quick_start`)**: current Telegram ZIP flow via `run_pipeline` / `core.run_quick_start`.
- **Mode B (`repo`)**: scaffold `openapi.json` + `pom.xml` with `openapi-generator-maven-plugin`; generation API writes **only** `src/test/java` (+ optional schemas); Maven runs `generate-sources test` in Docker.

## Layout (Mode B)

```
pom.xml                          # openapi-generator-maven-plugin
src/main/resources/openapi/openapi.json
src/main/java/.../config/ConfigManager.java
src/test/java/.../base/BaseTest.java
src/test/java/.../tests/*IntegrationTest.java   # generated tests
target/generated-sources/openapi/               # after mvn generate-sources (not in ZIP source tree)
```

## API entry

```python
request = GenerationRequest(..., mode="repo")
result = await run_generation(client, request, settings)
```

## Out of scope (v1)

- Patching an existing corporate monorepo in-place (PR mode).
- Gradle generator.
- Multi-module Maven reactors.

## Follow-up (done in codebase)

- Repo-specific prompts (`prompts.py`, `repo_mode=True` in generator).
- `filter_repo_generated_files` — only `src/test/` + schemas from API output.
- WireMock scaffold in repo mode when `contract-mocks`.
- Maven retry + autofix in `pipeline_mode_b.py`.
- CLI: `run_local.py --mode repo`.
- Telegram: profile → mode → URL flow.

## Remaining (enterprise)

- In-place monorepo PR mode.
- Gradle generator.
- CI e2e with Docker + real OpenAPI fixtures (nightly).
