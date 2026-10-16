export type Category =
  | 'DADO_MEDICO'
  | 'DADO_BANCARIO'
  | 'FILIACAO_PROTEGIDA'
  | 'DADO_FINANCEIRO'
  | 'DOCUMENTO_PESSOAL';

export type DetectionSource = 'regex' | 'llm' | 'manual';
export type SourceFormat = 'pdf' | 'docx' | 'doc';
export type JobStatus = 'analyzed' | 'pending_review' | 'sanitized';

export type ServiceType =
  | 'registro_civil'
  | 'registro_civil_interdicoes'
  | 'registro_imoveis'
  | 'tabelionato_notas'
  | 'protesto'
  | 'titulos_documentos';

/** Retângulo em pontos PDF, origem no canto superior esquerdo. */
export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface RedactionItem {
  redaction_id: string;
  category: Category;
  pii_type: string;
  detected_text: string;
  page_number: number;
  bboxes: BoundingBox[];
  approved: boolean;
  legal_basis: string;
  source: DetectionSource;
}

export interface PageInfo {
  page_number: number;
  width: number;
  height: number;
  has_text_layer: boolean;
}

export interface RedactionJob {
  job_id: string;
  filename: string;
  service_type: ServiceType;
  status: JobStatus;
  total_detected: number;
  items: RedactionItem[];
  pages: PageInfo[];
  warnings: string[];
  llm_provider: string;
  source_format: SourceFormat;
  source_sha256: string | null;
  original_sha256: string;
  sanitized_sha256: string | null;
  created_at: string;
  updated_at: string;
  sanitized_at: string | null;
  sanitized_by: string | null;
}

export interface JobSummary {
  job_id: string;
  filename: string;
  service_type: ServiceType;
  status: JobStatus;
  total_detected: number;
  created_at: string;
}

export const CATEGORY_META: Record<Category, { label: string; color: string }> = {
  DADO_MEDICO: { label: 'Saúde', color: '#d93025' },
  DADO_BANCARIO: { label: 'Bancário', color: '#1a73e8' },
  DADO_FINANCEIRO: { label: 'Financeiro', color: '#e37400' },
  FILIACAO_PROTEGIDA: { label: 'Filiação / família', color: '#8430ce' },
  DOCUMENTO_PESSOAL: { label: 'Documento pessoal', color: '#5f6368' },
};

export const CATEGORIES = Object.keys(CATEGORY_META) as Category[];

export const SERVICE_TYPES: { value: ServiceType; label: string }[] = [
  { value: 'registro_civil', label: 'Registro Civil' },
  { value: 'registro_civil_interdicoes', label: 'Registro Civil – Interdições' },
  { value: 'registro_imoveis', label: 'Registro de Imóveis' },
  { value: 'tabelionato_notas', label: 'Tabelionato de Notas' },
  { value: 'protesto', label: 'Protesto' },
  { value: 'titulos_documentos', label: 'Títulos e Documentos' },
];

export const STATUS_LABEL: Record<JobStatus, string> = {
  analyzed: 'Analisado',
  pending_review: 'Aguardando revisão',
  sanitized: 'Sanitizado',
};
