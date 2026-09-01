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
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"QgsLayoutExporter.exportToImage failed with code {result}")
