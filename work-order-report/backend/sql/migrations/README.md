# Schema migrations

`sql/001_schema.sql` is migration 1 and is now frozen.

Add each future database change as a new forward-only SQL file:

```text
V002__short_lowercase_description.sql
V003__another_additive_change.sql
```

Rules:

- Never edit or rename an applied migration.
- Use the next unused integer version.
- Prefer additive, backward-compatible changes.
- Deploy application code that can tolerate both old and new shapes when a
  rollout spans multiple runtime instances.
- Run `python -m app_core.migrations` before dbt and application startup.
- Do not manually insert or update `config.schema_migrations`.

The runner serializes deployments with a PostgreSQL advisory lock and rejects
checksum changes to applied files.
