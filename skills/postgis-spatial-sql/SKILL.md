---
name: postgis-spatial-sql
description: >-
  Invoke whenever spatial SQL or its execution backend is the decision:
  PostGIS, DuckDB Spatial, SpatiaLite, ST_* functions, recurring spatial
  joins, concurrent/growing workloads, or large GeoParquet queries. Covers
  backend selection, schemas, GiST/BRIN indexes, KNN, geometry versus
  geography, correctness benchmarks, and EXPLAIN optimization. Use PostGIS
  for managed concurrent services and embedded engines for bounded local
  analytics when evidence supports that choice. Use geo-data-engineering for
  acquisition, conversion, and file-based ETL without spatial SQL.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# PostGIS & Spatial SQL

Purpose: correct-and-fast spatial SQL. The two recurring failure modes are
semantic (geometry vs geography, SRID mismatches → wrong answers) and
performance (missing index usage → hour-long joins); this skill guards
both.

## When the database is the right tool

Move from files/GeoPandas to PostGIS when any of: features > a few
million, concurrent readers/writers, repeated ad-hoc querying, a serving
API on top, or transactional integrity needs. For single-shot analytical
scans over GeoParquet, **DuckDB Spatial** is often the fastest
zero-install path — same SQL mindset, no server.

When requirements are incomplete, do not turn this heuristic into a final
recommendation. First obtain current and forecast data volume, concurrency,
delivery and mutation pattern, latency/SLA, serving needs, and operational
ownership (including backup and recovery). Define representative ingestion,
join, and read queries for both viable backends; compare runtime and resource
use only after row counts, join cardinality, SRID, geometry validity, and sample
outputs agree. Include this benchmark and correctness plan in the current
response; do not merely offer to draft it later.

## Schema fundamentals

This runnable example assumes the data is contained in UTM zone 33N. Replace
EPSG:32633 with a projected CRS verified for the actual area of interest.

```sql
CREATE TABLE parcels (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parcel_no   text NOT NULL,
  landuse     text,
  area_m2     double precision,          -- unit in the name, always
  geom        geometry(MultiPolygon, 32633) NOT NULL
);
CREATE INDEX parcels_geom_gix ON parcels USING gist (geom);
ANALYZE parcels;
```

- **Type the geometry column fully**: `geometry(MultiPolygon, SRID)` — an
  untyped `geometry` column happily accepts mixed garbage.
- Promote to Multi* on load (`ST_Multi`) so Polygon/MultiPolygon mixing
  never bites.
- **geometry vs geography**: geometry in a projected SRID for regional
  analysis (fast, full function set); geography (SRID 4326) when the
  extent is global/cross-zone and you want meters without picking a
  projection (slower, smaller function set). Never store in 4326 geometry
  and call `ST_Area` expecting m² — that's square degrees.
- Never use EPSG:3857/Web Mercator for area or length measurement. When the
  analysis CRS is not yet known, either use 4326 geography for a geodesic
  result or stop and select a verified local/equal-area CRS; do not present a
  known-distorting CRS as a runnable measurement alternative.
- GiST index on every geometry column, `ANALYZE` after bulk loads; BRIN
  only for huge, spatially-ordered, append-only tables.
- Load paths: `ogr2ogr -f PostgreSQL`, `shp2pgsql`, or GeoPandas
  `to_postgis` (small/medium). `COPY` beats INSERT by orders of magnitude.

## Correct spatial predicates

- `ST_Intersects` for "touches at all", `ST_Contains`/`ST_Within` for
  containment, `ST_DWithin(a, b, dist)` for proximity — **never**
  `ST_Distance(a,b) < dist` (that form can't use the index).
- The classic point-in-polygon join:

```sql
SELECT p.id, a.district
FROM points p
JOIN admin a ON ST_Intersects(a.geom, p.geom);   -- GiST on both sides
```

- KNN nearest-neighbor with the distance operator (index-assisted):

```sql
SELECT h.id, h.name
FROM hospitals h
ORDER BY h.geom <-> (SELECT geom FROM incident WHERE id = 42)
LIMIT 3;
```

`<->` gives true-distance ordering on modern PostGIS for geometry; wrap
with `ST_DWithin` to bound the search when tables are huge.

## Performance playbook

1. `EXPLAIN (ANALYZE, BUFFERS)` first — confirm the GiST index is used
   (look for "Index Scan ... _gix"); a Seq Scan on a big spatial join
   means a rewrite, not a bigger server.
2. Same SRID on both sides of every predicate — `ST_Transform` inside a
   join predicate kills index use; store a transformed, indexed copy
   instead.
3. Big-polygon problem: country/basin-sized geometries make index bboxes
   useless → `ST_Subdivide` into a work table (typical 10-100× speedup on
   joins against them).

The following example assumes `countries(country_id, geom)`.

```sql
CREATE TABLE country_parts AS
SELECT c.country_id, part.geom
FROM countries AS c
CROSS JOIN LATERAL ST_Subdivide(c.geom, 256) AS part(geom);

CREATE INDEX country_parts_geom_gix ON country_parts USING gist (geom);
ANALYZE country_parts;
```

`ST_Subdivide` is a set-returning function; do not access its result as
`(ST_Subdivide(...)).geom`.

4. Validity in-database: `ST_IsValid` audit, `ST_MakeValid` repair, add a
   `CHECK (ST_IsValid(geom))` if writers are untrusted.
5. Simplify for serving, not for analysis: keep full-resolution geometry;
   generate `ST_SimplifyPreserveTopology` copies or vector tiles
   (`ST_AsMVT`) for the web tier.
6. Batch updates in transactions; `VACUUM ANALYZE` after churn.

## Common analytical patterns

```sql
-- Area-weighted aggregation (e.g., population into custom zones)
SELECT z.zone_id,
       SUM(b.pop * ST_Area(ST_Intersection(z.geom, b.geom)) / ST_Area(b.geom)) AS pop_est
FROM zones z JOIN blocks b ON ST_Intersects(z.geom, b.geom)
GROUP BY z.zone_id;

-- Dissolve with attribute
SELECT landuse, ST_Multi(ST_Union(geom))::geometry(MultiPolygon, 32633) AS geom
FROM parcels GROUP BY landuse;
```

Area-weighted interpolation assumes uniform density within source units —
state that assumption when reporting. Validity repair is `ST_MakeValid`,
never `ST_Buffer(geom, 0)`.

## DuckDB Spatial quick path

```sql
INSTALL spatial; LOAD spatial;
SELECT a.name, count(*)
FROM 'admin.parquet' a, 'points.parquet' p
WHERE ST_Intersects(a.geom, p.geom)
GROUP BY a.name;
```

Reads GeoParquet/Shapefile/GPKG directly, parallel by default — ideal for
one-off large joins and pipeline steps without a server. No GiST; it plans
its own joins — benchmark, don't assume.

## Verification protocol

1. Row-count accounting query after each join/overlay CTE.
2. `SELECT DISTINCT ST_SRID(geom), GeometryType(geom)` on every table
   touched — one query kills two classic bug families.
3. Sample 5 output features rendered over a basemap (QGIS connects
   directly) — numbers can pass while geometries are garbage.
4. Treat every `sql` fence presented as runnable as a syntax and alias
   boundary: it must execute top-to-bottom after stated schema assumptions.
   Never put angle-bracket placeholders, ellipses, pseudocode, abandoned joins,
   or incomplete aliases inside it. If a schema value such as an SRID is
   unknown, ask for it or keep the template in a labeled `text` block.

## Pitfalls checklist

- `ST_Area`/`ST_Length` on 4326 geometry (square degrees).
- EPSG:3857/Web Mercator for area or length measurement (systematic distortion).
- `ST_Distance < x` instead of `ST_DWithin` (no index).
- `ST_Transform` in join predicates.
- Untyped geometry columns with mixed SRIDs.
- Country-sized polygons joined without `ST_Subdivide`.
- `buffer(0)` as validity repair (silent part loss) — `ST_MakeValid`.
- Serving full-resolution geometries to web clients.

## Execution contract

- **Workflow:** inspect schema, SRID, geometry type, size, and query goal; choose predicates and indexes; write auditable CTEs; inspect the plan; reconcile results; operationalize safely.
- **Decision rules:** use PostGIS for concurrent, repeated, or transactional spatial workloads; use file pipelines or DuckDB Spatial for bounded one-off transformations when a server adds no value.
- **Verification protocol:** assert SRID and geometry invariants, account for rows at each join, compare indexed plans and timings, sample geometries on a map, and test boundary semantics.
- **Failure modes:** block release for mixed SRIDs, accidental many-to-many explosion, invalid geometries, non-indexable predicates, geography/geometry unit confusion, or unexplained plan regressions.
- **Deliverables:** self-contained parameterized SQL or migration with consistent CTE/table aliases, indexes and rationale, query plan evidence, row accounting, sample validation, expected schema, performance notes, and rollback guidance.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) for the deployed database and extension versions before selecting functions or plans.
