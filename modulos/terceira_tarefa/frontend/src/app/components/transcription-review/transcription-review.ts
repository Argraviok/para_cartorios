import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { BOOK_TYPE_LABELS, HistoricalRecord, RecordUpdate } from '../../models/historical-record';
import { apiErrorMessage, HistoricalService } from '../../services/historical.service';
import { EntityEditor } from './entity-editor/entity-editor';
import { ImageViewer } from './image-viewer/image-viewer';

@Component({
  selector: 'app-transcription-review',
  imports: [RouterLink, DatePipe, ImageViewer, EntityEditor],
  templateUrl: './transcription-review.html',
})
export class TranscriptionReview {
  private readonly api = inject(HistoricalService);
  private readonly router = inject(Router);

  /** Parâmetro de rota `:id` (withComponentInputBinding). */
  readonly id = input.required<string>();

  protected readonly record = signal<HistoricalRecord | null>(null);
  protected readonly loadError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly notice = signal<{ kind: 'ok' | 'error'; text: string } | null>(null);
  protected readonly bookTypeLabel = computed(() => {
    const r = this.record();
    return r ? BOOK_TYPE_LABELS[r.book_type] : '';
  });

  constructor() {
    effect(() => {
      const id = this.id();
      this.record.set(null);
      this.loadError.set(null);
      this.notice.set(null);
      this.api.getRecord(id).subscribe({
        next: (r) => this.record.set(r),
        error: (err) => this.loadError.set(apiErrorMessage(err)),
      });
    });
  }

  protected onSave(changes: RecordUpdate): void {
    const current = this.record();
    if (!current) return;
    this.saving.set(true);
    this.notice.set(null);
    this.api.updateRecord(current._id, changes).subscribe({
      next: (updated) => {
        this.record.set(updated);
        this.saving.set(false);
        if (changes.status === 'verified') {
          this.notice.set({ kind: 'ok', text: 'Transcrição homologada.' });
        } else if (changes.status === 'analyzed') {
          this.notice.set({ kind: 'ok', text: 'Registro reaberto para revisão.' });
        } else {
          this.notice.set({ kind: 'ok', text: 'Correções salvas.' });
        }
      },
      error: (err) => {
        this.saving.set(false);
        this.notice.set({ kind: 'error', text: apiErrorMessage(err) });
      },
    });
  }

  /** Abre o próximo assento ainda não homologado (fila de revisão). */
  protected nextPending(): void {
    const currentId = this.record()?._id;
    this.api.search({ status: 'analyzed', limit: 2 }).subscribe({
      next: (res) => {
        const next = res.results.find((r) => r._id !== currentId);
        if (next) {
          this.router.navigate(['/records', next._id]);
        } else {
          this.notice.set({ kind: 'ok', text: 'Não há outros assentos aguardando revisão.' });
        }
      },
      error: (err) => this.notice.set({ kind: 'error', text: apiErrorMessage(err) }),
    });
  }
}
