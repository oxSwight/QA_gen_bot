# Security

## Reporting

If you discover a vulnerability, open a private security advisory on GitHub or contact the maintainers directly. Do not open public issues for undisclosed credentials or exploits.

## Secrets

- Store `TG_TOKEN` and `ANTHROPIC_KEY` only in `.env` (gitignored).
- Never commit customer OpenAPI files that embed production API keys or personal data.
- Generated ZIPs may contain `config.properties` with a **public** API base URL you provide; review before sharing artifacts.

## Dependencies

Keep Python and Docker base images updated. Run `pip audit` and refresh `MAVEN_DOCKER_IMAGE` periodically.
