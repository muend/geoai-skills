# Tool routing

Use this reference to map an ArcGIS Pro task to the smallest bridge tool sequence.
The connected MCP server's live schemas override this snapshot; never guess a
payload from the name alone.

## Start with inspection

| Need | Prefer |
|---|---|
| Server/worker configuration | `health_check` |
| File GDB contents | `list_layers` |
| Dataset schema, type, CRS, extent, fields | `describe_dataset`, `get_field_info`, `get_extent` |
| Counts before and after | `get_feature_count` |
| CRS definition lookup | `get_spatial_reference` |
| Saved project structure | `list_maps`, `list_layers_in_map`, `list_layouts` |
| Geometry defects | `check_geometry`, `topology_check` |

`health_check` is not an ArcPy import or license check. Follow it with one of the
read-only ArcPy-backed tools above.

## Catalog by task

| Task family | Tools |
|---|---|
| Projection | `get_spatial_reference`, `project_features`, `project_raster`, `define_projection` |
| Data management | `create_file_gdb`, `create_feature_class`, `copy_features`, `describe_dataset`, `add_field`, `add_fields_batch`, `calculate_field`, `delete_field`, `delete_dataset`, `rename_dataset`, `compact_gdb`, `get_feature_count`, `get_field_info`, `get_extent`, `add_xy_coordinates`, `calculate_geometry` |
| Exchange | `excel_to_table`, `table_to_excel`, `import_from_geojson`, `export_to_geojson`, `export_to_shapefile`, `feature_to_csv` |
| Overlay and geometry | `intersect_features`, `union_features`, `erase_features`, `identity_features`, `symmetrical_difference`, `clip_raster`, `dissolve_features`, `merge_features`, `spatial_join`, `summarize_within`, `tabulate_intersection` |
| Selection and proximity | `select_by_attribute`, `select_by_location`, `near_analysis`, `generate_near_table` |
| Derived geometry | `create_fishnet`, `feature_to_point`, `feature_vertices_to_points`, `minimum_bounding_geometry`, `multipart_to_singlepart`, `simplify_features`, `smooth_features` |
| Tables and summaries | `frequency_analysis`, `statistics_analysis` |
| Raster | `extract_by_mask`, `raster_calculator`, `zonal_statistics`, `zonal_statistics_as_table`, `slope_analysis`, `aspect_analysis`, `hillshade`, `contour_lines`, `fill_sinks`, `flow_direction`, `resample_raster`, `mosaic_to_new_raster`, `raster_to_polygon`, `polygon_to_raster`, `clip_raster` |
| Network | `service_area`, `route_analysis`, `od_cost_matrix`, `closest_facility` |
| Spatial statistics | `mean_center`, `directional_distribution`, `kernel_density`, `hotspot_analysis`, `spatial_autocorrelation` |
| Editing and topology | `append_features`, `check_geometry`, `repair_geometry`, `delete_identical`, `detect_feature_changes`, `eliminate_polygon_part`, `topology_check` |
| Saved map project | `list_maps`, `list_layers_in_map`, `add_layer_to_map`, `remove_layer_from_map`, `set_layer_visibility`, `move_layer_order`, `rename_layer`, `zoom_to_layer`, `set_layer_symbology`, `save_project` |
| Layout and export | `list_layouts`, `set_map_extent_from_layer`, `set_map_scale`, `update_text_element`, `update_legend`, `set_layout_size`, `export_layout_pdf`, `export_layout_png`, `export_map_as_image` |
| Sketch to GIS | `extract_sketch_to_gis` |

Some names appear in more than one family because the intent decides the workflow.
Inspect the live description for exact read/write roles, parameters, extensions,
and confirmation requirements.

## Decision rules that prevent silent GIS errors

- Use `define_projection` only when coordinates are already in the named CRS but
  metadata is absent or wrong. Use `project_features` or `project_raster` to
  transform coordinates. Defining a CRS never reprojects data.
- Inspect source and target datums and choose a valid geographic transformation
  when they differ. Do not rely on a same-EPSG-looking name.
- Prefer `generate_near_table` when proximity results should be a new artifact.
  `near_analysis` mutates the input with NEAR fields.
- Run `check_geometry` before `repair_geometry`; preserve the report and operate on
  a copy unless the user explicitly authorizes in-place repair.
- Inspect fields and counts before `append_features` or `calculate_field`; verify
  schema mapping and counts afterward.
- Separate cartographic design decisions from `.aprx` mechanics. Decide symbology,
  classification, accessibility, and projection with `cartography-geoviz`, then
  implement and export through the bridge.
- Use the relevant domain skill to choose methods for terrain, raster science,
  networks, statistics, and remote sensing; use this skill to execute that method
  safely in ArcGIS Pro.

## Reusable sequences

### Reproject a feature class

1. `describe_dataset` source.
2. `get_spatial_reference` target WKID.
3. Resolve the geographic transformation if datums differ.
4. `project_features` to a new path.
5. `describe_dataset` and `get_feature_count` output; compare extent and count.

### Update and export a saved project

1. `list_maps`, `list_layers_in_map`, and `list_layouts`.
2. Add or style layers; set extent, scale, text, legend, and page size.
3. Save only when the requested `.aprx` target is explicit.
4. Export PDF or PNG.
5. Verify the saved project structure and exported file properties.

### Commit a photographed sketch

1. Inspect the basemap/layout envelope and target feature-class geometry and CRS.
2. Preserve the source photo and target count.
3. Run `extract_sketch_to_gis` only with required vision dependencies and explicit
   authorization to append to the exact target.
4. Verify registration residuals or control alignment, geometry validity, count
   delta, CRS, and overlay against the reference map.
