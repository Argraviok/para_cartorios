import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  DevolutionNote,
  DevolutionNoteResponse,
  GenerateNoteRequest,
  RequirementEdit,
  Vicio,
} from '../models/devolution.models';

const API = '/api';

@Injectable({ providedIn: 'root' })
export class DevolutionService {
  private http = inject(HttpClient);

  getVicios(): Observable<Vicio[]> {
    return this.http.get<Vicio[]>(`${API}/vicios`);
  }

  generate(body: GenerateNoteRequest): Observable<DevolutionNoteResponse> {
    return this.http.post<DevolutionNoteResponse>(`${API}/devolution-notes/generate`, body);
  }

  get(id: string): Observable<DevolutionNote> {
    return this.http.get<DevolutionNote>(`${API}/devolution-notes/${id}`);
  }

  update(id: string, version: number, requirements: RequirementEdit[]): Observable<DevolutionNote> {
    return this.http.patch<DevolutionNote>(`${API}/devolution-notes/${id}`, { version, requirements });
  }

  preview(id: string, requirements: RequirementEdit[]): Observable<string> {
    return this.http
      .post<{ markdown: string }>(`${API}/devolution-notes/${id}/preview`, { requirements })
      .pipe(map((r) => r.markdown));
  }

  issue(id: string): Observable<DevolutionNote> {
    return this.http.post<DevolutionNote>(`${API}/devolution-notes/${id}/issue`, {});
  }

  exportUrl(id: string, format: 'md' | 'txt'): string {
    return `${API}/devolution-notes/${id}/export.${format}`;
  }
}

/** Extrai a mensagem de erro do FastAPI (string ou lista de erros de validação). */
export function apiErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ');
    }
    if (err.status === 0) return 'Não foi possível conectar ao servidor.';
    return `Erro ${err.status}`;
  }
  return String(err);
}
