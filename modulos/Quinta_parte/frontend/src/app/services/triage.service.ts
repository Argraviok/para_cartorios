import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Triage, TriageStatus, TriageSummary, TurnResponse, UploadDocResponse } from '../models/triage.models';

@Injectable({ providedIn: 'root' })
export class TriageService {
  private http = inject(HttpClient);
  private base = '/api/triage';

  // --- Cidadão -------------------------------------------------------------
  startSession(customer_contact: string, customer_name: string | null): Observable<Triage> {
    return this.http.post<Triage>(`${this.base}/sessions`, { customer_contact, customer_name, channel: 'webchat' });
  }

  sendMessage(protocol_id: string, message: string): Observable<TurnResponse> {
    return this.http.post<TurnResponse>(`${this.base}/message`, { protocol_id, message });
  }

  uploadDoc(protocol_id: string, file: File, doc_index: number | null): Observable<UploadDocResponse> {
    const form = new FormData();
    form.append('protocol_id', protocol_id);
    form.append('file', file);
    if (doc_index !== null) form.append('doc_index', String(doc_index));
    return this.http.post<UploadDocResponse>(`${this.base}/upload-doc`, form);
  }

  // --- Escrevente ----------------------------------------------------------
  listSessions(status?: TriageStatus): Observable<TriageSummary[]> {
    const params: Record<string, string> = status ? { status } : {};
    return this.http.get<TriageSummary[]>(`${this.base}/sessions`, { params });
  }

  getSession(protocol_id: string): Observable<Triage> {
    return this.http.get<Triage>(`${this.base}/sessions/${protocol_id}`);
  }

  takeover(protocol_id: string, attendant_name: string): Observable<Triage> {
    return this.http.post<Triage>(`${this.base}/sessions/${protocol_id}/takeover`, { attendant_name });
  }

  release(protocol_id: string): Observable<Triage> {
    return this.http.post<Triage>(`${this.base}/sessions/${protocol_id}/release`, {});
  }

  attendantMessage(protocol_id: string, message: string, attendant_name: string): Observable<Triage> {
    return this.http.post<Triage>(`${this.base}/sessions/${protocol_id}/attendant-message`, {
      message,
      attendant_name,
    });
  }

  reviewDoc(
    protocol_id: string,
    index: number,
    status: 'VALIDADO' | 'REJEITADO' | 'PENDENTE',
    rejection_reason: string | null,
  ): Observable<Triage> {
    return this.http.patch<Triage>(`${this.base}/sessions/${protocol_id}/checklist/${index}`, {
      status,
      rejection_reason,
      notify_customer: true,
    });
  }

  counterTicket(protocol_id: string): Observable<Triage> {
    return this.http.post<Triage>(`${this.base}/sessions/${protocol_id}/counter-ticket`, {});
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (err.status === 0) return 'Sem conexão com o servidor.';
    return `Erro ${err.status}`;
  }
  return 'Erro inesperado.';
}
