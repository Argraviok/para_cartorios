export type RiskLevel = 'BAIXO' | 'MEDIO' | 'ALTO' | 'CRITICO';
export type OfficerDecision = 'PENDENTE' | 'HOMOLOGADO' | 'RECUSADO';
export type DocumentType = 'RG' | 'CNH' | 'PROCURACAO' | 'OUTRO';
export type CheckStatus =
  | 'APROVADO' | 'SUSPEITO' | 'DIVERGENTE' | 'INCONCLUSIVO' | 'ALERTA' | 'REPROVADO' | 'NAO_APLICAVEL' | 'NAO_EXECUTADO';
export type DecisionAction = 'APROVAR_FE_PUBLICA' | 'SOLICITAR_PRESENCIAL' | 'REJEITAR_FALSIDADE';
export type FileKind = 'document' | 'heatmap' | 'ela' | 'signature' | 'signature_card';

export interface SuspiciousRegion { x: number; y: number; w: number; h: number; intensity: number; }

export interface TamperingCheck {
  status: CheckStatus;
  score: number;
  findings: string[];
  suspicious_regions: SuspiciousRegion[];
  source_format: string;
  ela_reliable: boolean;
  vlm_used: boolean;
  vlm_error: string | null;
  image_width: number;
  image_height: number;
}

export interface SignatureCheck {
  status: CheckStatus;
  match_score: number | null;
  confidence: number;
  metrics: Record<string, number>;
  observation: string;
  signature_card_id: string | null;
  vlm_used: boolean;
  vlm_error: string | null;
}

export interface ProcurationCheck {
  status: CheckStatus;
  is_valid: boolean | null;
  verified_on_censec: boolean;
  age_days: number | null;
  book: string | null;
  page: string | null;
  act: string | null;
  origin_office: string | null;
  observations: string[];
}

export interface FacialBiometricsCheck {
  status: CheckStatus;
  similarity_score: number | null;
  liveness_detected: boolean | null;
  observation: string;
}

export interface DecisionHistoryEntry {
  action: DecisionAction;
  decision: OfficerDecision;
  officer_name: string;
  notes: string;
  decided_at: string;
}

export interface FraudAudit {
  id: string;
  protocol_number: string;
  service_type: string;
  document_type: DocumentType;
  presenter_name: string | null;
  presenter_cpf: string | null;
  risk_level: RiskLevel;
  risk_score: number;
  tampering_detected: boolean;
  tampering_details: string[];
  signature_match_score: number | null;
  procuration_verified: boolean | null;
  recommendation_to_officer: string;
  risk_factors: string[];
  checks: {
    document_tampering: TamperingCheck;
    signature_matching: SignatureCheck;
    power_of_attorney_censec: ProcurationCheck;
    facial_biometrics: FacialBiometricsCheck;
  };
  files: Partial<Record<FileKind, boolean>>;
  officer_decision: OfficerDecision;
  officer_notes: string | null;
  in_person_requested: boolean;
  decision_history: DecisionHistoryEntry[];
  created_at: string;
  decided_at: string | null;
}

export interface FraudAuditSummary {
  id: string;
  protocol_number: string;
  service_type: string;
  document_type: DocumentType;
  presenter_name: string | null;
  risk_level: RiskLevel;
  risk_score: number;
  tampering_detected: boolean;
  signature_match_score: number | null;
  officer_decision: OfficerDecision;
  in_person_requested: boolean;
  created_at: string;
}

export interface FraudStats {
  by_risk_level: Record<RiskLevel, number>;
  pending: number;
  total: number;
}

export interface SignatureCard {
  id: string;
  cpf: string;
  full_name: string;
  card_number: string | null;
  created_at: string;
}

export interface DecisionRequest {
  action: DecisionAction;
  officer_name: string;
  notes: string;
}

export const RISK_META: Record<RiskLevel, { label: string; dot: string; badge: string; hex: string }> = {
  BAIXO: { label: 'Baixo', dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-800 ring-emerald-300', hex: '#10b981' },
  MEDIO: { label: 'Médio', dot: 'bg-amber-400', badge: 'bg-amber-100 text-amber-800 ring-amber-300', hex: '#f59e0b' },
  ALTO: { label: 'Alto', dot: 'bg-orange-500', badge: 'bg-orange-100 text-orange-800 ring-orange-300', hex: '#f97316' },
  CRITICO: { label: 'Crítico', dot: 'bg-red-600', badge: 'bg-red-100 text-red-800 ring-red-300', hex: '#dc2626' },
};

export const STATUS_META: Record<CheckStatus, { label: string; cls: string }> = {
  APROVADO: { label: 'Aprovado', cls: 'bg-emerald-100 text-emerald-800' },
  SUSPEITO: { label: 'Suspeito', cls: 'bg-red-100 text-red-800' },
  DIVERGENTE: { label: 'Divergente', cls: 'bg-red-100 text-red-800' },
  INCONCLUSIVO: { label: 'Inconclusivo', cls: 'bg-amber-100 text-amber-800' },
  ALERTA: { label: 'Alerta', cls: 'bg-amber-100 text-amber-800' },
  REPROVADO: { label: 'Reprovado', cls: 'bg-red-100 text-red-800' },
  NAO_APLICAVEL: { label: 'Não aplicável', cls: 'bg-slate-100 text-slate-600' },
  NAO_EXECUTADO: { label: 'Não executado', cls: 'bg-slate-100 text-slate-600' },
};

export const DECISION_META: Record<OfficerDecision, { label: string; cls: string }> = {
  PENDENTE: { label: 'Pendente', cls: 'bg-slate-100 text-slate-700' },
  HOMOLOGADO: { label: 'Homologado', cls: 'bg-emerald-100 text-emerald-800' },
  RECUSADO: { label: 'Recusado', cls: 'bg-red-100 text-red-800' },
};

export const ACTION_LABEL: Record<DecisionAction, string> = {
  APROVAR_FE_PUBLICA: 'Aprovar sob fé pública',
  SOLICITAR_PRESENCIAL: 'Solicitar comparecimento presencial com biometria',
  REJEITAR_FALSIDADE: 'Rejeitar por suspeita de falsidade material',
};
