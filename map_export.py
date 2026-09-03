"""CRS refinement + third-party-ready PNG map export.

This is the part of v1 that is fully real and testable inside QGIS today —
it does not depend on the V-World DEM source (see datasource.py), it works
on whatever layer(s) are already loaded in the QGIS project.

CRS reprojection uses QGIS's own QgsCoordinateReferenceSystem /
QgsCoordinateTransform (PROJ-backed, on-the-fly reprojection) rather than
custom coordinate math, per this project's explicit "don't reinvent the
wheel" guidance and the CRS architecture already verified in
qgis-architecture-study/docs/06_crs_coordinate_systems.md (same PROJ engine
that backs QGIS's srs.db).

The print-layout export pattern (QgsPrintLayout + QgsLayoutItemMap +
QgsLayoutItemScaleBar + QgsLayoutItemLegend + QgsLayoutItemLabel +
QgsLayoutExporter) follows the official PyQGIS Developer Cookbook's
"Print Layout" chapter:
https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/composer.html
Exact method signatures should be re-checked against the installed QGIS
version's API docs (api.qgis.org) if this raises a TypeError — the cookbook
example was fetched and adapted, not executed inside QGIS in this session
(no way to run the QGIS application headlessly in this environment), so
treat this as structurally-correct-per-official-docs, not end-to-end tested.
"""

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
)


def export_dem_heightmap_png(dem_path: str, output_path: str) -> None:
    """Convert a DEM GeoTIFF (elevation values) into a 16-bit grayscale
    heightmap PNG, for Twinmotion's native landscape-import feature (see
    twinmotion-architecture-study/docs/11 §6 — Twinmotion natively imports
    heightmap images without any plugin, so this is the qgis-terrain-
    assistant side of that bridge).

    Normalizes elevation to the FULL 0-65535 range of the exported area
    (min elevation -> 0, max -> 65535) rather than embedding real-world
    meters — Twinmotion applies its own vertical "Amplitude" scaling on
    import (per Epic's official docs), so only the RELATIVE height
    ordering within the area needs to survive this conversion, not
    absolute units.

    Chose 16-bit (not 8-bit) deliberately: Twinmotion's exact accepted bit
    depth for heightmap PNGs is NOT stated in Epic's official docs (see
    docs/11 §6's "확인 안 됨" note) — 16-bit avoids visible terracing on
    real terrain and is the safer default. If Twinmotion turns out to
    need 8-bit, that's a one-line change deferred to whenever this is
    actually format-verified against the real Twinmotion Import dialog.

    Uses GDAL's Python bindings + numpy — both already bundled with
    QGIS 4.2.1's own Python environment (confirmed installed at
    apps/Python312/Lib/site-packages/{GDAL-3.13.2-py3.12.egg-info,numpy},
    checked directly 2026-09-03) — no new dependency added. The MEM-driver
    -> WriteArray() -> PNG-driver CreateCopy() pattern below follows
    GDAL's documented Python Raster API shape (grade b — corroborated via
    web search of GDAL's own docs and multiple independent examples, not
    a single official worked example fetched in full this session).

    NOT execution-tested end-to-end in this session (no live QGIS/GDAL
    environment available here) — same documented limitation as
    export_map_png/export_3d_scene in this module.

    Raises:
        ValueError: dem_path isn't openable by GDAL, has no valid
            elevation data, or is perfectly flat (zero range — can't
            normalize).
        RuntimeError: the PNG driver fails to write output_path.
    """
    from osgeo import gdal
    import numpy as np

    dataset = gdal.Open(dem_path)
    if dataset is None:
        raise ValueError(f"GDAL could not open {dem_path!r} as a raster")

    band = dataset.GetRasterBand(1)
    elevation = band.ReadAsArray().astype(np.float64)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        elevation = np.where(elevation == nodata, np.nan, elevation)

    valid = elevation[~np.isnan(elevation)]
    if valid.size == 0:
        raise ValueError(f"{dem_path!r} has no valid elevation data")

    min_elev, max_elev = float(valid.min()), float(valid.max())
    if max_elev == min_elev:
        raise ValueError(
            f"{dem_path!r} is perfectly flat (elevation range is zero) — "
            "cannot normalize to a heightmap"
        )

    normalized = (elevation - min_elev) / (max_elev - min_elev)
    normalized = np.nan_to_num(normalized, nan=0.0)  # missing pixels -> lowest point
    heightmap = (normalized * 65535).astype(np.uint16)

    mem_dataset = gdal.GetDriverByName("MEM").Create(
        "", dataset.RasterXSize, dataset.RasterYSize, 1, gdal.GDT_UInt16
    )
    mem_dataset.GetRasterBand(1).WriteArray(heightmap)

    png_driver = gdal.GetDriverByName("PNG")
    out_dataset = png_driver.CreateCopy(output_path, mem_dataset, strict=0)
    if out_dataset is None:
        raise RuntimeError(f"GDAL's PNG driver failed to write {output_path!r}")


def export_dem_heightmap_r16(dem_path: str, output_path: str) -> tuple[int, int]:
    """Convert a DEM GeoTIFF into Twinmotion's native `.r16` heightmap
    format — a headerless raw dump of 16-bit unsigned little-endian
    integers in row-major order (VERIFIED 2026-09-03, grade a: the user
    directly confirmed live in Twinmotion 2026.2's own Import file-type
    dropdown that "Heightmaps" accepts exactly `*.r16;*.png` — screenshot
    checked; format spec cross-confirmed via multiple independent
    community/tooling sources describing `.r16` as 16-bit unsigned,
    little-endian, headerless, row-major, values 0-65535).

    Prefer this over export_dem_heightmap_png() when bit-depth certainty
    matters: `.r16` is UNAMBIGUOUSLY 16-bit by definition of the format,
    whereas a `.png`'s bit depth (8 vs 16) is a choice PNG allows either
    way — this session could not confirm which one Twinmotion's PNG path
    actually honors, so `.r16` sidesteps that open question entirely.
    Keep export_dem_heightmap_png() too — PNG is still useful for a quick
    visual preview outside Twinmotion, which `.r16` (no viewer opens it
    directly) is not.

    Same normalization as export_dem_heightmap_png(): elevation is scaled
    to the full 0-65535 range of the exported area (relative height, not
    absolute meters) since Twinmotion applies its own vertical scaling on
    import.

    IMPORTANT — unlike PNG, `.r16` stores NO width/height metadata at all
    (confirmed by the format's own definition, not just this DEM's case).
    Twinmotion's heightmap importer needs the resolution entered manually
    when importing a raw file, so the caller MUST track/report the
    returned (width, height) alongside the file — losing that pairing
    makes the .r16 file unusable.

    NOT execution-tested end-to-end in this session (no live QGIS/GDAL
    environment here) — same documented limitation as this module's other
    QGIS-dependent functions.

    Returns:
        (width, height) in pixels — must be recorded/shown to the user
        alongside output_path, since the file itself doesn't carry it.

    Raises:
        ValueError: dem_path isn't openable by GDAL, has no valid
            elevation data, or is perfectly flat (zero range).
    """
    from osgeo import gdal
    import numpy as np

    dataset = gdal.Open(dem_path)
    if dataset is None:
        raise ValueError(f"GDAL could not open {dem_path!r} as a raster")

    band = dataset.GetRasterBand(1)
    elevation = band.ReadAsArray().astype(np.float64)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        elevation = np.where(elevation == nodata, np.nan, elevation)

    valid = elevation[~np.isnan(elevation)]
    if valid.size == 0:
        raise ValueError(f"{dem_path!r} has no valid elevation data")

    min_elev, max_elev = float(valid.min()), float(valid.max())
    if max_elev == min_elev:
        raise ValueError(
            f"{dem_path!r} is perfectly flat (elevation range is zero) — "
            "cannot normalize to a heightmap"
        )

    normalized = (elevation - min_elev) / (max_elev - min_elev)
    normalized = np.nan_to_num(normalized, nan=0.0)
    heightmap = (normalized * 65535).astype("<u2")  # explicit little-endian uint16

    heightmap.tofile(output_path)
    return dataset.RasterXSize, dataset.RasterYSize


def refine_crs(geometry_or_extent, source_epsg: int, target_epsg: int):
    """Reproject a QgsRectangle (or anything QgsCoordinateTransform accepts)
    from source_epsg to target_epsg using QGIS's built-in PROJ transform.

    Raises:
        ValueError: either EPSG code is not a CRS QGIS recognizes locally
            (its srs.db doesn't have an entry for it).
    """
    project = QgsProject.instance()
    src_crs = QgsCoordinateReferenceSystem(f"EPSG:{source_epsg}")
    dst_crs = QgsCoordinateReferenceSystem(f"EPSG:{target_epsg}")
    if not src_crs.isValid():
        raise ValueError(f"EPSG:{source_epsg} not found in QGIS's CRS database")
    if not dst_crs.isValid():
        raise ValueError(f"EPSG:{target_epsg} not found in QGIS's CRS database")
    transform = QgsCoordinateTransform(src_crs, dst_crs, project)
    return transform.transformBoundingBox(geometry_or_extent)


def export_map_png(
    output_path: str,
    map_extent: QgsRectangle,
    title: str,
    dpi: int = 300,
) -> None:
    """Compose a title + map + scale bar + legend layout from the current
    QGIS project's layers and export it to a PNG file for handing to a
    third party.
    """
    project = QgsProject.instance()
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()

    map_item = QgsLayoutItemMap(layout)
    map_item.attemptMove(QgsLayoutPoint(10, 20, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(250, 180, QgsUnitTypes.LayoutMillimeters))
    map_item.setExtent(map_extent)
    layout.addLayoutItem(map_item)

    title_label = QgsLayoutItemLabel(layout)
    title_label.setText(title)
    title_label.attemptMove(QgsLayoutPoint(10, 5, QgsUnitTypes.LayoutMillimeters))
    title_label.adjustSizeToText()
    layout.addLayoutItem(title_label)

    scale_bar = QgsLayoutItemScaleBar(layout)
    scale_bar.setLinkedMap(map_item)
    scale_bar.applyDefaultSize()
    scale_bar.attemptMove(QgsLayoutPoint(10, 205, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(scale_bar)

    legend = QgsLayoutItemLegend(layout)
    legend.setLinkedMap(map_item)
    legend.setTitle("")
    legend.attemptMove(QgsLayoutPoint(265, 20, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(legend)

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = dpi
    result = exporter.exportToImage(output_path, settings)
    if result != QgsLayoutExporter.ExportResult.Success:
        raise RuntimeError(f"QgsLayoutExporter.exportToImage failed with code {result}")
