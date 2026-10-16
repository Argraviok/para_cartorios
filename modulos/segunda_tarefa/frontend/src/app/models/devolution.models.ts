// Espelha app/schemas/devolution_schema.py e app/schemas/enums.py do backend.

export type VicioCode =
  | 'quebra_continuidade'
  | 'itbi_nao_recolhido'
  | 'procuracao_sem_censec'
  | 'outorga_conjugal'
  | 'descricao_tabular_divergente'
  | 'debito_condominial'
  | 'cnd_municipal_ausente'
  | 'averbacao_casamento_pendente'
  | 'outro';

export interface Vicio {
  code: VicioCode;
  label: string;
}

export interface IssueInput {
  vicio_code: VicioCode;
  title?: string | null;
  case_facts: string;
}

export interface GenerateNoteRequest {
  protocol_number: string;
  protocol_date: string; // AAAA-MM-DD
  act_type: string;
  presenter_name: string;
  uf: string;
  issues: IssueInput[];
}

export interface RequirementEdit {
  vicio_code: VicioCode;
  legal_topic: string;
  precedent_ids: string[];
  legal_basis: string;
  justification_draft: string;
  user_edited_text: string | null;
  suggested_solution: string;
  source: 'ai' | 'manual';
  grounded: boolean;
}

export interface Requirement extends RequirementEdit {
  order: number;
}

export type NoteStatus = 'draft' | 'issuing' | 'issued';

export interface DevolutionNote {
  id: string;
  note_number: string | null;
  protocol_number: string;
  protocol_date: string;
  act_type: string;
  presenter_name: string;
  uf: string;
  status: NoteStatus;
  requirements: Requirement[];
  full_compiled_text: string;
  llm_model: string | null;
  prompt_version: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  issued_at: string | null;
}

export interface DevolutionNoteResponse extends DevolutionNote {
  warnings: string[];
}
