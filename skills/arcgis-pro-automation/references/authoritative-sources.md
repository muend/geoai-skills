# Authoritative sources

- Last verified: 2026-07-20
- Review cadence: every 3 months
- Refresh triggers: arcgis-mcp-bridge release or tool-catalog change, ArcGIS Pro major release, ArcPy licensing change, or MCP transport change

## Canonical sources

- [arcgis-mcp-bridge repository](https://github.com/muend/arcgis-mcp-bridge) — bridge architecture, live tool contracts, PathGuard, confirmation gates, setup, and release state. Source snapshot reviewed: commit `c4415d8851ada2dfa5ebd5e2d47544a1d2694914`.
- [ArcGIS Pro ArcPy reference](https://pro.arcgis.com/en/pro-app/latest/arcpy/main/arcgis-pro-arcpy-reference.htm) — primary ArcPy API and geoprocessing documentation.
- [ArcGIS Pro Python environments](https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/what-is-conda.htm) — Esri-supported conda environment model and package management.
- [CheckExtension](https://pro.arcgis.com/en/pro-app/latest/arcpy/functions/checkextension.htm) — extension availability semantics.
- [Introduction to arcpy.mp](https://pro.arcgis.com/en/pro-app/latest/arcpy/mapping/introduction-to-arcpy-mp.htm) — saved project, map, layer, layout, and export automation boundaries.
- [ArcGIS Pro system requirements](https://pro.arcgis.com/en/pro-app/latest/get-started/arcgis-pro-system-requirements.htm) — supported operating systems and runtime requirements.

Use the connected MCP server's live schemas for payload fields. Record the bridge
version or commit, ArcGIS Pro and ArcPy versions, worker interpreter, license level
and extensions, allowed roots, scratch GDB, and checked date with each execution.
