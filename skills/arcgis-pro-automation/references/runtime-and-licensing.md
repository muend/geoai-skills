# Runtime and licensing

Use this reference before the first bridge execution and when diagnosing setup,
worker, ArcPy, or extension failures.

## Execution architecture

`arcgis-mcp-bridge` uses two processes:

1. The MCP server validates Pydantic contracts, applies PathGuard, enforces
   confirmation gates, and dispatches jobs. It deliberately does not import ArcPy.
2. A worker runs under `ARCPY_PYTHON_PATH`, imports ArcPy for catalog tools, and
   returns structured results and ArcPy geoprocessing messages.

The bridge is local and stdio-based. It is not a hosted ArcPy service, an ArcGIS
Pro add-in, or a controller for an already-open desktop session.

## Required runtime

- Windows with ArcGIS Pro installed and licensed.
- A Python interpreter that can import both `arcpy` and `arcgis_mcp.worker`.
- `arcgis-mcp-bridge` installed in the MCP host environment.
- Existing allowed-root directories and an existing scratch file geodatabase.

Install the bridge in the host environment and discover an ArcGIS-capable worker:

```powershell
pip install arcgis-mcp-bridge
arcgis-mcp-setup
```

Use the setup result for `ARCPY_PYTHON_PATH`. Prefer a cloned ArcGIS Pro conda
environment when bridge dependencies should not alter Esri's default environment.

## Configuration contract

| Variable | Meaning | Safety rule |
|---|---|---|
| `ARCPY_PYTHON_PATH` | Worker `python.exe` | Must exist and import ArcPy plus bridge dependencies |
| `ARCGIS_MCP_ALLOWED_ROOTS` | `os.pathsep`-separated read/write roots | Keep narrow; never expose a drive, home, or unrelated archive |
| `ARCGIS_MCP_SCRATCH_GDB` | Existing default output GDB | Keep inside an allowed root; create it before server startup |
| `ARCGIS_MCP_MAX_WORKERS` | Concurrent ArcPy subprocess ceiling | Bound by memory and available license seats |
| `ARCGIS_MCP_TOOL_TIMEOUT` | Per-tool wall-clock timeout | Increase only for known long jobs, not to hide hangs |
| `ARCGIS_MCP_LOG_FILE` | Optional rotating log | Keep outside sensitive data or sanitize access |
| `ARCGIS_MCP_LOG_LEVEL` | Logging verbosity | Avoid debug logs around sensitive datasets unless necessary |

When allowed roots are omitted, the bridge falls back to the user's ArcGIS
Projects directory. Do not assume that fallback is appropriate; inspect the
`health_check` response.

## Two-stage preflight

1. Call `health_check`. Confirm `server=ok`, the expected worker interpreter,
   narrow allowed roots, the intended scratch GDB, timeout, and worker ceiling.
2. Remember that `health_check` sends a worker `ping` and does **not** import ArcPy.
3. Run a non-mutating ArcPy-backed call appropriate to the task:
   `get_spatial_reference`, `describe_dataset`, `get_feature_count`, `list_layers`,
   or `list_maps`.
4. For extension-dependent work, let the first relevant call check out the named
   extension. Do not infer extension availability from base ArcPy import success.

Never describe the runtime as ArcPy-ready after `health_check` alone.

## Extension behavior

The bridge checks extension availability before licensed operations and checks the
seat back in inside `finally`.

| Work | Typical extension gate |
|---|---|
| Slope, aspect, hydrology, zonal statistics, map algebra | Spatial Analyst |
| Service area, route, OD cost matrix, closest facility | Network Analyst |
| Some catalog tools | Base ArcGIS Pro license only |

Tool licensing can evolve. Use the live tool description and current Esri product
documentation as the authority. If a license is unavailable, report it as a
capability boundary; do not substitute a different algorithm silently.

## Environment truthfulness

- A mocked unit test result validates contracts and guards, not real ArcPy output.
- A cloud MCP listing proves discoverability, not access to licensed local data.
- A saved `.aprx` can be edited headlessly, but an unsaved open GUI session is not
  the same state.
- Never claim an output exists until the call returned its path and a follow-up
  read verified it.
