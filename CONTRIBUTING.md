# Contributing

## Branch and commit rules

- `main` must stay runnable.
- Use short-lived branches for substantial changes.
- Commit messages use `type(scope): summary`, for example `feat(api): add camera probe endpoint`.
- Do not commit secrets, model weights, real camera URLs, phone numbers, or private monitoring footage.

## Definition of done

A change is complete only when it includes the relevant implementation, contract update, tests, migration/configuration, and documentation.

## Required checks

- Web: typecheck, unit tests, production build.
- API: unit/integration tests and Flyway validation.
- Inference: schema tests and deterministic replay tests.
- Contracts: JSON Schema validation and OpenAPI parse.

