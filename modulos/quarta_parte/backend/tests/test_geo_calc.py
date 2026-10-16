import math

import pytest

from app.schemas.geo_schema import MemorialExtraction, TopoVertex
from app.services.geo_calc_service import analyze_geometry, parse_azimuth


@pytest.mark.parametrize(
    "text,expected",
    [
        ("45°30'00\"", 45.5),
        ("72°15'30,00\"", 72.258333),
        ("341°39'10.84\"", 341.653011),
        ("90.25", 90.25),
        ("N 45°00' E", 45.0),
        ("S 30°00' E", 150.0),
        ("S30°W", 210.0),
        ("N 10°30' O", 349.5),
    ],
)
def test_parse_azimuth(text, expected):
    assert parse_azimuth(text) == pytest.approx(expected, abs=1e-5)


def square_traverse(close_error: float = 0.0) -> MemorialExtraction:
    return MemorialExtraction(
        vertices=[
            TopoVertex(point_name="V-01", azimuth="90°00'00\"", distance_meters=30, confrontant="Rua A"),
            TopoVertex(point_name="V-02", azimuth="180°00'00\"", distance_meters=50, confrontant="Lote 12, matrícula nº 1.234"),
            TopoVertex(point_name="V-03", azimuth="270°00'00\"", distance_meters=30 + close_error),
            TopoVertex(point_name="V-04", azimuth="0°00'00\"", distance_meters=50),
        ],
        declared_area_m2=1500,
    )


def test_traverse_closed_without_georef():
    g = analyze_geometry(square_traverse())
    assert g.is_closed and g.gap_meters == pytest.approx(0, abs=1e-9)
    assert g.calculated_area == pytest.approx(1500)
    assert g.perimeter_m == pytest.approx(160)
    assert not g.is_georeferenced and g.location_geojson is None
    assert g.confrontants[1].registry == "1.234"


def test_traverse_not_closing():
    g = analyze_geometry(square_traverse(close_error=2.5))
    assert not g.is_closed
    assert g.gap_meters == pytest.approx(2.5)


def test_area_divergence_percent():
    m = square_traverse()
    m.declared_area_m2 = 1400
    g = analyze_geometry(m)
    assert g.area_difference_percent == pytest.approx(100 / 1400 * 100, abs=0.01)


def test_utm_sirgas_to_wgs84_campinas():
    e0, n0 = 288627.507, 7465450.274
    m = MemorialExtraction(
        utm_zone=23,
        datum="SIRGAS 2000",
        vertices=[
            TopoVertex(point_name="P-01", utm_e=e0, utm_n=n0),
            TopoVertex(point_name="P-02", utm_e=e0 + 30, utm_n=n0),
            TopoVertex(point_name="P-03", utm_e=e0 + 30, utm_n=n0 - 50),
            TopoVertex(point_name="P-04", utm_e=e0, utm_n=n0 - 50),
            TopoVertex(point_name="P-01", utm_e=e0, utm_n=n0),  # repetição do vértice inicial
        ],
    )
    g = analyze_geometry(m)
    assert g.is_georeferenced and g.closure_method == "COORDINATES"
    assert len(g.segments) == 4
    assert g.calculated_area == pytest.approx(1500, abs=0.01)
    ring = g.location_geojson["coordinates"][0]
    assert ring[0] == ring[-1]
    lon, lat = ring[0]
    assert lon == pytest.approx(-47.0608, abs=1e-4) and lat == pytest.approx(-22.9056, abs=1e-4)


def test_declared_distance_mismatch_warning():
    m = MemorialExtraction(
        utm_zone=23,
        vertices=[
            TopoVertex(point_name="P-01", utm_e=0 + 288000, utm_n=7465000, distance_meters=40),
            TopoVertex(point_name="P-02", utm_e=288030, utm_n=7465000),
            TopoVertex(point_name="P-03", utm_e=288030, utm_n=7464950),
        ],
    )
    g = analyze_geometry(m)
    assert any("P-01→P-02" in w for w in g.warnings)


def test_self_intersecting_polygon_is_flagged():
    m = MemorialExtraction(
        utm_zone=23,
        vertices=[
            TopoVertex(point_name="A", utm_e=288000, utm_n=7465000),
            TopoVertex(point_name="B", utm_e=288030, utm_n=7464950),
            TopoVertex(point_name="C", utm_e=288030, utm_n=7465000),
            TopoVertex(point_name="D", utm_e=288000, utm_n=7464950),
        ],
    )
    g = analyze_geometry(m)
    assert not g.is_valid_polygon
    assert g.location_geojson is None  # não pode ir para o índice 2dsphere


def test_too_few_vertices():
    assert analyze_geometry(MemorialExtraction(vertices=[TopoVertex(point_name="A")])) is None
    assert math.isfinite(analyze_geometry(square_traverse()).calculated_area)


def test_gap_line_marks_where_traverse_ends():
    g = analyze_geometry(square_traverse(close_error=2.5))
    start, end = g.closure_gap_line
    assert start == [0.0, 0.0]
    assert end == pytest.approx([-2.5, 0.0])
    assert analyze_geometry(square_traverse()).closure_gap_line is None


def test_anchor_georeferences_traverse():
    g = analyze_geometry(square_traverse(), anchor=(-22.9056, -47.0608))
    assert g.georeference_method == "MANUAL_ANCHOR" and g.is_georeferenced
    assert g.segments[0].coordinates[0] == pytest.approx([-47.0608, -22.9056], abs=1e-7)
    assert g.calculated_area == pytest.approx(1500)
    assert g.location_geojson is not None


def test_inferred_zone_used_when_document_omits_it():
    m = MemorialExtraction(
        vertices=[
            TopoVertex(point_name="P-01", utm_e=288000, utm_n=7465000),
            TopoVertex(point_name="P-02", utm_e=288030, utm_n=7465000),
            TopoVertex(point_name="P-03", utm_e=288030, utm_n=7464950),
        ]
    )
    g22 = analyze_geometry(m, inferred_zone=22)
    g23 = analyze_geometry(m)
    assert any("inferido" in w for w in g22.warnings)
    assert any("assumido fuso 23" in w for w in g23.warnings)
    # Mesmas coordenadas UTM em fusos diferentes ficam ~6° de longitude distantes
    assert g23.segments[0].coordinates[0][0] - g22.segments[0].coordinates[0][0] == pytest.approx(6, abs=0.3)
