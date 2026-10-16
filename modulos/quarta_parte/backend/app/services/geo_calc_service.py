"""Cálculos geométricos do memorial descritivo.

Todas as contas (área, perímetro, fechamento) são feitas em sistema métrico plano
(UTM ou coordenadas locais da poligonal). Só a saída GeoJSON é convertida para WGS84.
"""

import math
import re
from functools import lru_cache
from typing import Optional

from pyproj import CRS, Geod, Transformer
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity

from app.core.config import settings
from app.schemas.geo_schema import (
    Confrontant,
    GeometryAnalysis,
    MemorialExtraction,
    Segment,
    TopoVertex,
)

# ---------------------------------------------------------------------------
# Azimutes e rumos
# ---------------------------------------------------------------------------

_DMS_RE = re.compile(
    r"(?P<deg>\d+(?:[.,]\d+)?)\s*[°º]?\s*(?:(?P<min>\d+(?:[.,]\d+)?)\s*['′’])?\s*"
    r"(?:(?P<sec>\d+(?:[.,]\d+)?)\s*(?:\"|″|”|''|’’))?"
)
_BEARING_RE = re.compile(r"^\s*(?P<ns>[NS])\s*(?P<angle>.+?)\s*(?P<ew>[EWLO])\s*$", re.IGNORECASE)


def _dms_to_decimal(text: str) -> float:
    m = _DMS_RE.search(text)
    if not m or m.group("deg") is None:
        raise ValueError(f"Ângulo inválido: {text!r}")
    deg = float(m.group("deg").replace(",", "."))
    minutes = float((m.group("min") or "0").replace(",", "."))
    seconds = float((m.group("sec") or "0").replace(",", "."))
    return deg + minutes / 60 + seconds / 3600


def parse_azimuth(text: str) -> float:
    """Converte azimute ("45°30'15\"", "45.5") ou rumo ("N 45°30' E", "S30°W") em graus decimais."""
    text = text.strip()
    bearing = _BEARING_RE.match(text)
    if bearing:
        angle = _dms_to_decimal(bearing.group("angle"))
        ns = bearing.group("ns").upper()
        ew = bearing.group("ew").upper()
        east = ew in ("E", "L")
        if ns == "N":
            az = angle if east else 360 - angle
        else:
            az = 180 - angle if east else 180 + angle
        return az % 360
    az = _dms_to_decimal(text)
    if not 0 <= az <= 360:
        raise ValueError(f"Azimute fora do intervalo: {text!r}")
    return az % 360


# ---------------------------------------------------------------------------
# Sistemas de referência
# ---------------------------------------------------------------------------


def utm_epsg(zone: int, south: bool = True, datum: Optional[str] = None) -> int:
    d = (datum or "SIRGAS").upper().replace(" ", "").replace("-", "")
    if "SAD69" in d:
        return (29170 if south else 29150) + zone
    if "WGS84" in d:
        return (32700 if south else 32600) + zone
    # SIRGAS 2000 (padrão para georreferenciamento no Brasil — Lei 10.267/2001)
    return (31960 if south else 31954) + zone


@lru_cache(maxsize=32)
def _transformer(src_epsg: int, dst_epsg: int) -> Transformer:
    return Transformer.from_crs(CRS.from_epsg(src_epsg), CRS.from_epsg(dst_epsg), always_xy=True)


def zone_from_lon(lon: float) -> int:
    return int((lon + 180) // 6) + 1


# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------


def _same_vertex(a: TopoVertex, b: TopoVertex) -> bool:
    if a.point_name and a.point_name.strip().upper() == b.point_name.strip().upper():
        return True
    if a.utm_e is not None and b.utm_e is not None:
        return abs(a.utm_e - b.utm_e) < 1e-3 and abs((a.utm_n or 0) - (b.utm_n or 0)) < 1e-3
    return False


def fmt_br(value: float, decimals: int = 2) -> str:
    """1234.5 -> '1.234,50'"""
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_m(value: float) -> str:
    return fmt_br(value, 3) + " m"


def analyze_geometry(
    memorial: MemorialExtraction,
    registry_declared_area: Optional[float] = None,
    utm_zone: Optional[int] = None,
    *,
    inferred_zone: Optional[int] = None,
    anchor: Optional[tuple[float, float]] = None,
    source: str = "MEMORIAL",
) -> Optional[GeometryAnalysis]:
    """Reconstrói o polígono, mede fechamento/área e gera GeoJSON. None se não houver vértices.

    utm_zone: fuso informado pelo usuário. inferred_zone: fuso deduzido do endereço (geocodificação).
    anchor: (lat, lon) WGS84 do primeiro vértice, para posicionar uma poligonal sem coordenadas.
    """
    vertices = list(memorial.vertices)
    if len(vertices) < 3:
        return None

    # Memoriais costumam repetir o vértice inicial no fim ("...até o ponto V-01, início").
    if len(vertices) > 3 and _same_vertex(vertices[0], vertices[-1]):
        vertices = vertices[:-1]
    n = len(vertices)
    warnings: list[str] = []

    has_utm = all(v.utm_e is not None and v.utm_n is not None for v in vertices)
    has_latlon = all(v.lat is not None and v.lon is not None for v in vertices)
    has_traverse = all(v.azimuth and v.distance_meters for v in vertices)

    zone = memorial.utm_zone or utm_zone
    south = True
    src_epsg: Optional[int] = None
    coords: Optional[list[tuple[float, float]]] = None

    # 1) Coordenadas absolutas (preferencial)
    if has_utm:
        if zone is None and inferred_zone:
            zone = inferred_zone
            warnings.append(f"Fuso UTM não informado no documento; inferido pela localização do endereço: fuso {zone}.")
        elif zone is None:
            zone = settings.default_utm_zone
            warnings.append(
                f"Fuso UTM não informado no documento e endereço não localizado; assumido fuso {zone}S "
                "— confira a posição no mapa."
            )
        south = vertices[0].utm_n > 2_000_000  # Norte de N < ~2.000 km => hemisfério norte
        src_epsg = utm_epsg(zone, south, memorial.datum)
        if memorial.datum and "SAD" in memorial.datum.upper():
            warnings.append("Coordenadas em SAD-69: recomenda-se conversão oficial para SIRGAS 2000.")
        coords = [(v.utm_e, v.utm_n) for v in vertices]
    elif has_latlon:
        zone = zone_from_lon(vertices[0].lon)
        south = vertices[0].lat < 0
        src_epsg = utm_epsg(zone, south)
        to_utm = _transformer(4674, src_epsg)  # SIRGAS 2000 geográfico
        coords = [to_utm.transform(v.lon, v.lat) for v in vertices]

    # 1b) Sem coordenadas, mas com ponto de amarração escolhido no mapa
    anchor_xy: Optional[tuple[float, float]] = None
    if coords is None and anchor is not None and has_traverse:
        lat, lon = anchor
        zone = zone_from_lon(lon)
        south = lat < 0
        src_epsg = utm_epsg(zone, south)
        anchor_xy = _transformer(4326, src_epsg).transform(lon, lat)

    # 2) Poligonal por azimutes e distâncias
    traverse: Optional[list[tuple[float, float]]] = None
    if has_traverse:
        try:
            x, y = coords[0] if coords else (anchor_xy or (0.0, 0.0))
            traverse = [(x, y)]
            for v in vertices:
                az = math.radians(parse_azimuth(v.azimuth))
                x += v.distance_meters * math.sin(az)
                y += v.distance_meters * math.cos(az)
                traverse.append((x, y))
        except ValueError as exc:
            warnings.append(f"Não foi possível interpretar azimute: {exc}")
            traverse = None

    if coords is None and traverse is None:
        return None

    if traverse is not None:
        closure_method = "TRAVERSE"
        gap = math.dist(traverse[-1], traverse[0])
    else:
        closure_method = "COORDINATES"
        gap = 0.0

    polygon_pts = coords if coords is not None else traverse[:-1]
    is_georeferenced = src_epsg is not None

    if coords is not None:
        georeference_method = "COORDINATES"
    elif anchor_xy is not None:
        georeference_method = "MANUAL_ANCHOR"
        warnings.append(
            f"Posição definida manualmente pelo vértice {vertices[0].point_name} (ponto de amarração). "
            "A orientação assume azimutes referidos ao Norte; a localização não tem valor de georreferenciamento."
        )
    else:
        georeference_method = "NONE"
        warnings.append(
            "Documento sem coordenadas georreferenciadas: polígono reconstruído em sistema local a partir "
            "de azimutes e distâncias. Clique no mapa para indicar onde fica o primeiro vértice."
        )

    # Divergência entre distância declarada e distância entre coordenadas
    segments: list[Segment] = []
    to_wgs = _transformer(src_epsg, 4326) if is_georeferenced else None
    for i, v in enumerate(vertices):
        a, b = polygon_pts[i], polygon_pts[(i + 1) % n]
        computed = math.dist(a, b)
        if coords is not None and v.distance_meters:
            diff = abs(computed - v.distance_meters)
            if diff > max(0.10, v.distance_meters * 0.005):
                warnings.append(
                    f"Segmento {v.point_name}→{vertices[(i + 1) % n].point_name}: distância declarada "
                    f"{_fmt_m(v.distance_meters)} difere da calculada pelas coordenadas "
                    f"({_fmt_m(computed)})."
                )
        seg_coords = [list(to_wgs.transform(*a)), list(to_wgs.transform(*b))] if to_wgs else [list(a), list(b)]
        segments.append(
            Segment(
                from_point=v.point_name,
                to_point=vertices[(i + 1) % n].point_name,
                azimuth=v.azimuth,
                declared_distance_m=v.distance_meters,
                computed_distance_m=round(computed, 3),
                confrontant=v.confrontant,
                coordinates=[[round(c, 8) for c in p] for p in seg_coords],
            )
        )

    poly = Polygon(polygon_pts)
    is_valid = poly.is_valid
    if not is_valid:
        warnings.append(f"Polígono inválido ({explain_validity(poly)}): verifique ordem dos vértices.")
    area = abs(poly.area)
    perimeter = poly.length

    declared = memorial.declared_area_m2 or registry_declared_area
    if memorial.declared_area_m2 and registry_declared_area:
        mismatch = abs(memorial.declared_area_m2 - registry_declared_area) / registry_declared_area * 100
        if mismatch > settings.area_tolerance_percent:
            warnings.append(
                f"Área do memorial ({fmt_br(memorial.declared_area_m2)} m²) diverge {fmt_br(mismatch)}% "
                f"da área constante na matrícula ({fmt_br(registry_declared_area)} m²)."
            )
    area_diff = round(abs(area - declared) / declared * 100, 2) if declared else None

    geojson = None
    if is_georeferenced and is_valid:
        ring = orient(poly, sign=1.0).exterior.coords  # anti-horário (regra da mão direita)
        geojson = {
            "type": "Polygon",
            "coordinates": [[[round(c, 8) for c in to_wgs.transform(x, y)] for x, y in ring]],
        }

    gap_line = None
    if traverse is not None and gap > settings.closure_tolerance_m:
        ends = [traverse[0], traverse[-1]]
        gap_line = [[round(c, 8) for c in (to_wgs.transform(*p) if to_wgs else p)] for p in ends]

    confrontants = [
        Confrontant(
            direction=v.direction,
            name=v.confrontant,
            segment=f"{v.point_name} → {vertices[(i + 1) % n].point_name}",
            registry=v.confrontant_registry or _registry_in_text(v.confrontant),
        )
        for i, v in enumerate(vertices)
        if v.confrontant
    ]

    return GeometryAnalysis(
        source=source,
        georeference_method=georeference_method,
        is_closed=gap <= settings.closure_max_acceptable_m,
        gap_meters=round(gap, 4),
        closure_method=closure_method,
        declared_area=declared,
        calculated_area=round(area, 2),
        area_difference_percent=area_diff,
        perimeter_m=round(perimeter, 3),
        is_valid_polygon=is_valid,
        is_georeferenced=is_georeferenced,
        location_geojson=geojson,
        closure_gap_line=gap_line,
        segments=segments,
        confrontants=confrontants,
        warnings=warnings,
    )


_REGISTRY_RE = re.compile(r"matr[íi]cula\s*(?:n[º°o.]*\s*)?([\d.]+\d)", re.IGNORECASE)


def _registry_in_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = _REGISTRY_RE.search(text)
    return m.group(1) if m else None


_GEOD = Geod(ellps="GRS80")


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância geodésica entre (lat, lon) e (lat, lon), em metros."""
    return _GEOD.inv(a[1], a[0], b[1], b[0])[2]


def geometry_center(geo: GeometryAnalysis) -> Optional[tuple[float, float]]:
    """(lat, lon) médio dos vértices de uma geometria georreferenciada."""
    pts = [s.coordinates[0] for s in geo.segments if s.coordinates]
    if not geo.is_georeferenced or not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)
