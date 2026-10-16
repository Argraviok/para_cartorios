export type FindingStatus = 'CONFORME' | 'PENDENCIA' | 'ALERTA';
export type Severity = 'impeditiva' | 'recomendavel';
export type OverallStatus = 'APROVADO' | 'EXIGENCIAS_PENDENTES';

export interface RuleFinding {
  rule_code: string;
  rule_name: string;
  severity: Severity;
  legal_ref: string;
  status: FindingStatus;
  finding: string;
  citation: string | null;
  page_number: number | null;
  citation_verified: boolean;
  recommendation: string | null;
}

export interface Qualification {
  id: string;
  document_title: string;
  act_type: string;
  created_at: string;
  overall_status: OverallStatus;
  checklist: RuleFinding[];
}

export interface ActType {
  value: string;
  label: string;
}

export const ACT_TYPES: ActType[] = [
  { value: 'compra_e_venda_urbano', label: 'Escritura Pública de Compra e Venda de Imóvel Urbano' },
];
