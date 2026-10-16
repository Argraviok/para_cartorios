import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import { AnalyzeRequest, ParcelAnalysis, ParcelSummary } from '../models/parcel.model';

@Injectable({ providedIn: 'root' })
export class ParcelService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/parcels';

  analyze(req: AnalyzeRequest): Observable<ParcelAnalysis> {
    const form = new FormData();
    form.append('matricula', req.matricula);
    if (req.memorial) form.append('memorial', req.memorial);
    if (req.titulo) form.append('titulo', req.titulo);
    if (req.sellerName?.trim()) form.append('seller_name', req.sellerName.trim());
    return this.http.post<ParcelAnalysis>(`${this.base}/analyze`, form).pipe(catchError(toMessage));
  }

  /** Posiciona um perímetro sem coordenadas a partir do primeiro vértice clicado no mapa. */
  anchor(id: string, lat: number, lon: number): Observable<ParcelAnalysis> {
    return this.http.post<ParcelAnalysis>(`${this.base}/${id}/anchor`, { lat, lon }).pipe(catchError(toMessage));
  }

  get(id: string): Observable<ParcelAnalysis> {
    return this.http.get<ParcelAnalysis>(`${this.base}/${id}`).pipe(catchError(toMessage));
  }

  list(limit = 10): Observable<ParcelSummary[]> {
    return this.http.get<ParcelSummary[]>(this.base, { params: { limit } }).pipe(catchError(toMessage));
  }
}

function toMessage(err: HttpErrorResponse) {
  let msg: string;
  if (err.status === 0) msg = 'Não foi possível contatar o servidor. O backend está rodando?';
  else if (typeof err.error?.detail === 'string') msg = err.error.detail;
  else if (Array.isArray(err.error?.detail)) msg = err.error.detail.map((d: { msg: string }) => d.msg).join('; ');
  else msg = `Erro ${err.status}: ${err.statusText}`;
  return throwError(() => new Error(msg));
}
