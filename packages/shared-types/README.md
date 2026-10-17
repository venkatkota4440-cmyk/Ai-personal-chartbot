# shared-types

Hand-written TypeScript types that mirror the API's Pydantic schemas
(`apps/api/app/schemas/`). When a schema changes, update the matching type
here in the same commit. The web app imports these as `@shared/types`.

Generating these from the OpenAPI document (`/api/openapi.json`) is planned
once the API surface stabilises; see `docs/DECISIONS.md` (D-007).
