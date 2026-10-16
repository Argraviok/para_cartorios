export type TriageStatus = 'in_progress' | 'ready_for_counter' | 'human_takeover';
export type TriageStage = 'ask_name' | 'identify_act' | 'ask_value' | 'collect_docs' | 'done';
export type DocStatus = 'PENDENTE' | 'ENVIADO' | 'VALIDADO' | 'REJEITADO';
export type Sender = 'user' | 'bot' | 'attendant' | 'system';

export interface ChatMessage {
  sender: Sender;
  message: string;
  timestamp: string;
  attendant_name?: string | null;
  attachment_url?: string | null;
}

export interface ChecklistItem {
  doc_name: string;
  description: string;
  required: boolean;
  max_age_days: number | null;
  status: DocStatus;
  image_url: string | null;
  content_type: string | null;
  rejection_reason: string | null;
  ai_feedback: string | null;
  document_type_identified: string | null;
  issue_date: string | null;
  validated_by: 'ai' | 'attendant' | null;
  uploaded_at: string | null;
}

export interface FeeEstimate {
  service_name: string;
  declared_value: number | null;
  base_fee: number;
  state_funds: number;
  municipal_tax: number;
  taxes_and_funds: number;
  total_estimate: number;
  tier_label: string | null;
  legal_disclaimer: string;
}

export interface Triage {
  protocol_id: string;
  customer_name: string | null;
  customer_contact: string;
  channel: 'webchat' | 'whatsapp';
  state: string;
  act_type: string | null;
  act_name: string | null;
  stage: TriageStage;
  status: TriageStatus;
  human_requested: boolean;
  attendant_name: string | null;
  declared_value: number | null;
  estimated_total: number | null;
  fee_estimate: FeeEstimate | null;
  checklist: ChecklistItem[];
  chat_history: ChatMessage[];
  counter_ticket: string | null;
  created_at: string;
  updated_at: string;
}

export interface TriageSummary {
  protocol_id: string;
  customer_name: string | null;
  customer_contact: string;
  channel: string;
  act_name: string | null;
  status: TriageStatus;
  human_requested: boolean;
  attendant_name: string | null;
  estimated_total: number | null;
  docs_validated: number;
  docs_required: number;
  docs_rejected: number;
  last_message: string | null;
  last_sender: Sender | null;
  counter_ticket: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentVerification {
  document_type_identified: string;
  is_legible: boolean;
  matches_expected: boolean;
  issue_date_identified: string | null;
  validation_status: 'APROVADO' | 'REJEITADO_ILEGIVEL' | 'EXPIRADO' | 'DOCUMENTO_INCORRETO' | 'REVISAO_MANUAL';
  feedback_to_user: string;
  engine: string;
}

export interface TurnResponse {
  triage: Triage;
  replies: ChatMessage[];
}

export interface UploadDocResponse extends TurnResponse {
  verification: DocumentVerification;
  doc_index: number;
}

export const STATUS_META: Record<TriageStatus, { label: string; dot: string; badge: string }> = {
  in_progress: { label: 'Em triagem com IA', dot: 'bg-amber-400', badge: 'bg-amber-50 text-amber-800 ring-amber-200' },
  ready_for_counter: {
    label: 'Pronto para balcão',
    dot: 'bg-emerald-500',
    badge: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  },
  human_takeover: { label: 'Atendimento humano', dot: 'bg-rose-500', badge: 'bg-rose-50 text-rose-800 ring-rose-200' },
};

export const DOC_STATUS_META: Record<DocStatus, { label: string; icon: string; cls: string }> = {
  PENDENTE: { label: 'Pendente', icon: '○', cls: 'text-slate-500 bg-slate-100' },
  ENVIADO: { label: 'Aguardando conferência', icon: '◔', cls: 'text-sky-800 bg-sky-100' },
  VALIDADO: { label: 'Validado', icon: '✓', cls: 'text-emerald-800 bg-emerald-100' },
  REJEITADO: { label: 'Recusado', icon: '!', cls: 'text-rose-800 bg-rose-100' },
};
