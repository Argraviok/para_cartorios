import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  BookType,
  HistoricalRecord,
  RecordUpdate,
  SearchParams,
  SearchResponse,
} from '../models/historical-record';

const API = '/api/historical';

@Injectable({ providedIn: 'root' })
export class HistoricalService {
  private readonly http = inject(HttpClient);

  search(params: SearchParams): Observable<SearchResponse> {
    let httpParams = new HttpParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        httpParams = httpParams.set(key, String(value));
      }
    }
    return this.http.get<SearchResponse>(`${API}/search`, { params: httpParams });
  }

  getRecord(id: string): Observable<HistoricalRecord> {
    return this.http.get<HistoricalRecord>(`${API}/records/${encodeURIComponent(id)}`);
  }

  updateRecord(id: string, changes: RecordUpdate): Observable<HistoricalRecord> {
    return this.http.patch<HistoricalRecord>(`${API}/records/${encodeURIComponent(id)}`, changes);
  }

  transcribe(file: File, bookType: BookType, bookNumber: string, pageNumber: number): Observable<HistoricalRecord> {
    const form = new FormData();
    form.append('image', file);
    form.append('book_type', bookType);
    form.append('book_number', bookNumber);
    form.append('page_number', String(pageNumber));
    return this.http.post<HistoricalRecord>(`${API}/transcribe`, form);
  }
}

/** Extrai a mensagem `detail` do FastAPI de um erro HTTP. */
export function apiErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
    if (err.status === 0) return 'Servidor indisponível.';
    return `Erro ${err.status}`;
  }
  return 'Erro inesperado.';
}
