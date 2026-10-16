import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { JobSummary, RedactionItem, RedactionJob, ServiceType } from '../models/redaction.models';

const API = '/api/redact';

@Injectable({ providedIn: 'root' })
export class RedactionService {
  private readonly http = inject(HttpClient);

  analyze(file: File, serviceType: ServiceType, operator: string): Observable<RedactionJob> {
    const form = new FormData();
    form.append('file', file);
    form.append('service_type', serviceType);
    form.append('operator', operator);
    return this.http.post<RedactionJob>(`${API}/analyze`, form);
  }

  listJobs(): Observable<JobSummary[]> {
    return this.http.get<JobSummary[]>(`${API}/jobs`);
  }

  getJob(jobId: string): Observable<RedactionJob> {
    return this.http.get<RedactionJob>(`${API}/jobs/${jobId}`);
  }

  saveReview(jobId: string, items: RedactionItem[], operator: string): Observable<RedactionJob> {
    return this.http.put<RedactionJob>(`${API}/jobs/${jobId}/items`, { items, operator });
  }

  apply(jobId: string, items: RedactionItem[], operator: string): Observable<HttpResponse<Blob>> {
    return this.http.post(
      `${API}/apply`,
      { job_id: jobId, items, operator, confirm_irreversible: true },
      { responseType: 'blob', observe: 'response' },
    );
  }

  pageImageUrl(jobId: string, page: number, scale = 1.5): string {
    return `${API}/jobs/${jobId}/pages/${page}.png?scale=${scale}`;
  }

  sanitizedUrl(jobId: string): string {
    return `${API}/jobs/${jobId}/sanitized`;
  }

  auditUrl(jobId: string, format: 'csv' | 'pdf'): string {
    return `${API}/jobs/${jobId}/audit.${format}`;
  }
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header?.match(/filename\*=UTF-8''([^;]+)/i);
  return match ? decodeURIComponent(match[1]) : fallback;
}

/** Mensagem legível a partir de um erro HTTP do FastAPI (inclusive quando o corpo é Blob). */
export async function errorMessage(err: unknown): Promise<string> {
  const e = err as { error?: unknown; message?: string; status?: number };
  let body = e.error;
  if (body instanceof Blob) {
    try {
      body = JSON.parse(await body.text());
    } catch {
      body = undefined;
    }
  }
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  if (e.status === 0) return 'Servidor indisponível';
  return e.message ?? 'Erro inesperado';
}
