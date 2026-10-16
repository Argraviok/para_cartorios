export type ContinuityStatus = 'REGULAR' | 'QUEBRA_DETECTADA' | 'ALERTA';
export type AlertLevel = 'INFO' | 'WARNING' | 'CRITICAL';

export interface ChainLink {
  act_code: string;
  act_date: string | null;
  act_type: string;
  grantors: string[];
  grantees: string[];
  is_continuous: boolean;
  note: string | null;
}

export interface ActiveLien {
  act_code: string;
  type: string;
  court_or_creditor: string | null;
  summary: string;
  status: 'VIGENTE';
}

export interface SubjectiveContinuity {
  status: ContinuityStatus;
  current_registered_owner: string;
  current_owner_act: string | null;
  seller_in_contract: string | null;
  active_liens: ActiveLien[];
  chain: ChainLink[];
  observation: string;
}

export interface Confrontant {
  direction: string | null;
  name: string;
  segment: string;
  registry: string | null;
}

export interface Segment {
  from_point: string;
  to_point: string;
  azimuth: string | null;
  declared_distance_m: number | null;
  computed_distance_m: number;
  confrontant: string | null;
  /** [lon, lat] se georreferenciado; senão [x, y] em metros (sistema local) */
  coordinates: number[][] | null;
}

export interface GeoJsonPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface GeometryAnalysis {
  source: 'MEMORIAL' | 'MATRICULA';
  georeference_method: 'COORDINATES' | 'MANUAL_ANCHOR' | 'NONE';
  is_closed: boolean;
  gap_meters: number;
  closure_method: 'TRAVERSE' | 'COORDINATES' | 'NONE';
  declared_area: number | null;
  calculated_area: number;
  area_difference_percent: number | null;
  perimeter_m: number;
  is_valid_polygon: boolean;
  is_georeferenced: boolean;
  location_geojson: GeoJsonPolygon | null;
  /** [vértice inicial, ponto onde a poligonal termina] quando o perímetro não fecha */
  closure_gap_line: number[][] | null;
  segments: Segment[];
  confrontants: Confrontant[];
  warnings: string[];
}

export interface ApproximateLocation {
  lat: number;
  lon: number;
  precision: 'ENDERECO' | 'RUA' | 'BAIRRO' | 'CIDADE';
  query: string;
  display_name: string | null;
  source: string;
}

export interface Alert {
  level: AlertLevel;
  code: string;
  message: string;
}

export interface ParcelAnalysis {
  id: string;
  registry_number: string;
  registry_office: string | null;
  document_filename: string;
  memorial_filename: string | null;
  subjective_continuity: SubjectiveContinuity;
  geometry: GeometryAnalysis | null;
  approximate_location: ApproximateLocation | null;
  alerts: Alert[];
  extraction_engine: string;
  created_at: string;
}

export interface ParcelSummary {
  id: string;
  registry_number: string;
  registry_office: string | null;
  document_filename: string;
  created_at: string;
  subjective_continuity: { status: ContinuityStatus };
}

export interface AnalyzeRequest {
  matricula: File;
  memorial?: File | null;
  titulo?: File | null;
  sellerName?: string;
}
