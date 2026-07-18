# Authoritative sources

- Last verified: 2026-07-19
- Review cadence: every 3 months
- Refresh triggers: PostgreSQL, PostGIS, GEOS, PROJ, or DuckDB Spatial major release

## Canonical sources

- [PostGIS reference manual](https://postgis.net/docs/) — spatial types, predicates, functions, indexes, and version behavior.
- [PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/using-explain.html) — query-plan interpretation.
- [DuckDB Spatial overview](https://duckdb.org/docs/stable/core_extensions/spatial/overview.html) — extension types, functions, and limitations.

Record server and extension versions plus `PostGIS_Full_Version()`. Verify predicates and plans against the deployed version, because current online docs may differ from production.
