export type BookType = 'transcricao_imobiliaria' | 'nascimento' | 'casamento' | 'obito';
export type RecordStatus = 'analyzed' | 'verified';

export const BOOK_TYPE_LABELS: Record<BookType, string> = {
  transcricao_imobiliaria: 'Transcrição Imobiliária (Livro 3)',
  nascimento: 'Nascimento',
  casamento: 'Casamento',
  obito: 'Óbito',
};

export const BOOK_TYPES = Object.keys(BOOK_TYPE_LABELS) as BookType[];

/** Rótulo do campo de confrontantes/filiação conforme o tipo de livro. */
export const RELATIVES_LABEL: Record<BookType, string> = {
  transcricao_imobiliaria: 'Confrontantes',
  nascimento: 'Filiação e avós',
  casamento: 'Pais dos nubentes',
  obito: 'Filiação',
};

export interface Party {
  role: string;
  name_standardized: string;
  name_original: string;
  phonetic?: string;
}

export interface HistoricalRecord {
  _id: string;
  book_type: BookType;
  book_number: string;
  page_number: number;
  entry_number: string | null;
  entry_date_text: string | null;
  entry_date_iso: string | null;
  image_url: string;
  image_enhanced_url: string | null;
  transcription_raw: string;
  status: RecordStatus;
  parties: Party[];
  confrontants_or_relatives: string[];
  confidence_score: number;
  vlm_model: string | null;
  created_at: string;
  updated_at: string | null;
  verified_at: string | null;
}

export interface SearchHit extends HistoricalRecord {
  score: number | null;
  highlights: string[];
}

export interface SearchResponse {
  total: number;
  engine: 'atlas_search' | 'fallback';
  results: SearchHit[];
}

export interface SearchParams {
  q?: string;
  book_type?: BookType | '';
  status?: RecordStatus | '';
  year_from?: number | null;
  year_to?: number | null;
  limit?: number;
  skip?: number;
}

export type RecordUpdate = Partial<
  Pick<
    HistoricalRecord,
    | 'entry_number'
    | 'entry_date_text'
    | 'entry_date_iso'
    | 'transcription_raw'
    | 'confrontants_or_relatives'
    | 'status'
  >
> & { parties?: Omit<Party, 'phonetic'>[] };
