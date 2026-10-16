import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Qualification } from '../models/qualification.model';

export const API_URL = 'http://localhost:8030/api';

@Injectable({ providedIn: 'root' })
export class QualificationService {
  private readonly http = inject(HttpClient);

  analyze(file: File, actType: string): Observable<Qualification> {
    const form = new FormData();
    form.append('file', file);
    form.append('act_type', actType);
    return this.http.post<Qualification>(`${API_URL}/qualifications/analyze`, form);
  }

  /** Converte um documento Word em PDF para exibição e análise. */
  convertToPdf(file: File): Observable<Blob> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post(`${API_URL}/qualifications/convert`, form, { responseType: 'blob' });
  }

  get(id: string): Observable<Qualification> {
    return this.http.get<Qualification>(`${API_URL}/qualifications/${id}`);
  }
}
