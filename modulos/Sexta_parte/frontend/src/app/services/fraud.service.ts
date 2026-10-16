import { HttpClient, HttpInterceptorFn, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  DecisionRequest, FileKind, FraudAudit, FraudAuditSummary, FraudStats, OfficerDecision, RiskLevel, SignatureCard,
} from '../models/fraud.models';

export const authInterceptor: HttpInterceptorFn = (req, next) =>
  environment.apiToken && req.url.startsWith(environment.apiBaseUrl)
    ? next(req.clone({ setHeaders: { Authorization: `Bearer ${environment.apiToken}` } }))
    : next(req);

@Injectable({ providedIn: 'root' })
export class FraudService {
  private http = inject(HttpClient);
  private base = `${environment.apiBaseUrl}/api`;

  listAudits(filters: { risk_level?: RiskLevel | ''; decision?: OfficerDecision | ''; protocol?: string } = {}) {
    let params = new HttpParams().set('limit', 100);
    for (const [k, v] of Object.entries(filters)) if (v) params = params.set(k, v);
    return this.http.get<FraudAuditSummary[]>(`${this.base}/fraud/audits`, { params });
  }

  stats() {
    return this.http.get<FraudStats>(`${this.base}/fraud/stats`);
  }

  getAudit(id: string) {
    return this.http.get<FraudAudit>(`${this.base}/fraud/audits/${id}`);
  }

  auditDocument(form: FormData) {
    return this.http.post<FraudAudit>(`${this.base}/fraud/audit-document`, form);
  }

  decide(id: string, body: DecisionRequest) {
    return this.http.patch<FraudAudit>(`${this.base}/fraud/audits/${id}/decision`, body);
  }

  /** Arquivos sensíveis são baixados com o token e expostos como object URL (revogar após o uso). */
  fileUrl(id: string, kind: FileKind): Observable<string> {
    return this.blobUrl(`${this.base}/fraud/audits/${id}/files/${kind}`);
  }

  listCards(q = '') {
    const params = q ? new HttpParams().set('q', q) : undefined;
    return this.http.get<SignatureCard[]>(`${this.base}/signature-cards`, { params });
  }

  createCard(form: FormData) {
    return this.http.post<SignatureCard>(`${this.base}/signature-cards`, form);
  }

  cardImageUrl(id: string): Observable<string> {
    return this.blobUrl(`${this.base}/signature-cards/${id}/image`);
  }

  private blobUrl(url: string): Observable<string> {
    return this.http.get(url, { responseType: 'blob' }).pipe(map((b) => URL.createObjectURL(b)));
  }
}

export function apiError(err: any): string {
  const d = err?.error?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((e) => `${(e.loc ?? []).slice(-1)[0] ?? ''}: ${e.msg}`).join('; ');
  if (err?.status === 0) return 'Backend indisponível. Verifique se a API está em execução.';
  return err?.message ?? 'Erro inesperado';
}
