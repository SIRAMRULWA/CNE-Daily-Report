# API Architecture and Governance Standard

## 1. Scope

This standard governs every HTTP API exposed by ITIL Group Reports. The only public application base path is `/api/v1`.

## 2. Resource design

- Use lowercase plural nouns: `/users`, `/divisions`, `/daily-reports`.
- Use path segments for identity or containment: `/users/{user_id}` and `/divisions/{division}/groups`.
- Do not put UI areas in resource paths. Use `/operational-records`, not `/workspace/records`.
- Do not put verbs in ordinary CRUD paths. Command-style paths are permitted only when the operation cannot be represented as resource state, such as a password reset or maintenance job.
- Keep historical Daily Report snapshots separate from current operational records because they have different freshness and retention semantics.

## 3. HTTP methods and status codes

| Method | Meaning | Normal success status |
|---|---|---|
| `GET` | Read a resource or collection; no side effects | `200` |
| `POST` | Create a resource or processing job | `201` |
| `PUT` | Replace the client-controlled representation | `200` |
| `PATCH` | Partially update a resource | `200` |
| `DELETE` | Delete or revoke and return the resulting state | `200` |

Use `400` for malformed requests, `401` for missing or invalid authentication, `403` for insufficient authorization, `404` for missing resources, `409` for state conflicts, `422` for field or semantic validation, `502` for upstream-provider failures, and `503` for unavailable required dependencies.

## 4. Requests and validation

- JSON fields and query parameters use `snake_case`.
- Dates use ISO 8601 `YYYY-MM-DD`; timestamps include an explicit timezone.
- Use Pydantic models with length, range, enum, and cross-field rules.
- Trim identifiers and user-entered names at the boundary.
- Reject unknown enum values and invalid combinations with `422`.
- Collection endpoints use `limit` and `offset`. New endpoints return `limit`, `offset`, and `count`; add `total` when it is inexpensive to calculate.
- Never accept audit actor, authorization identity, or ownership from the request when it can be derived from the access token.

## 5. Responses

- Preserve one stable representation per resource across list and detail APIs.
- Collection data uses a named plural property plus `count` and pagination metadata.
- Never return credentials, password hashes, token identifiers, or provider secrets.
- `null` means known but unavailable; an omitted expansion means the client did not request it.
- Every v1 response carries `API-Version: 1`; the observability layer supplies `X-Request-ID`.

## 6. Error contract

Every error uses this shape:

```json
{
  "message": "User-facing explanation",
  "detail": "User-facing explanation",
  "error_code": "STABLE_MACHINE_CODE",
  "request_id": "support-correlation-id",
  "details": [{ "field": "email", "message": "Invalid value" }]
}
```

`message` is canonical and `detail` provides the matching FastAPI error value. Clients branch on HTTP status and `error_code`, not English text. Unexpected-error UI displays `request_id` as the support reference.

## 7. Authentication and authorization

- Bearer tokens are required except for session creation and service health.
- Approved machine-to-machine endpoints use a dedicated named API-key security
  scheme, constant-time secret comparison, and mandatory idempotency keys.
- Authorization is enforced server-side at router and endpoint boundaries.
- Current-user operations live under `/users/current`; session operations live under `/auth/sessions` or `/sessions` for security administration.
- Login failures do not reveal whether an email exists. Account-state errors are returned only after valid credentials are supplied.
- Sensitive changes and provider operations create audit events without passwords, tokens, full report data, or secrets.

## 8. Versioning

- Major breaking changes require a new path version such as `/api/v2`.
- Additive fields and new endpoints may be introduced within v1.
- Removing or renaming fields, changing meaning, tightening accepted input in a breaking way, or changing success/error structures requires a major version.
- A future version is introduced only through an approved consumer migration plan. Unsupported unversioned aliases must not be added.

## 9. OpenAPI and documentation

- `/api/openapi.json` is the machine-readable contract.
- `/docs` and `/redoc` are interactive views.
- Every route needs a unique summary, domain tag, auth rule, request model, success status, and documented error responses.
- Examples use placeholders and never contain real credentials, tokens, or production personal information.

## 10. Review checklist

An API change cannot ship until reviewers confirm:

1. Resource name and method follow this standard.
2. Authentication and minimum role are explicit.
3. Validation and error codes are deterministic.
4. OpenAPI is accurate and has no route or operation-ID collision.
5. Logs and audits contain no secrets or excessive record content.
6. Compatibility is additive, or a versioned migration is documented.
7. Frontend contract types and integration tests are updated.
8. Syntax, OpenAPI, database, and provider checks appropriate to the change pass.
