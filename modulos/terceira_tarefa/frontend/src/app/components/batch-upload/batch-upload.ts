import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { BOOK_TYPE_LABELS, BOOK_TYPES, BookType } from '../../models/historical-record';
import { apiErrorMessage, HistoricalService } from '../../services/historical.service';

type ItemState = 'queued' | 'processing' | 'done' | 'error';

interface UploadItem {
  key: number;
  file: File;
  page: number;
  state: ItemState;
  recordId?: string;
  confidence?: number;
  error?: string;
}

/** Envios simultâneos ao backend (cada um faz uma chamada ao VLM). */
const CONCURRENCY = 2;
const ACCEPTED = /\.(jpe?g|png|tiff?|bmp|webp)$/i;

@Component({
  selector: 'app-batch-upload',
  imports: [RouterLink, DecimalPipe],
  templateUrl: './batch-upload.html',
})
export class BatchUpload {
  private readonly api = inject(HistoricalService);
  private nextKey = 0;

  protected readonly bookTypes = BOOK_TYPES;
  protected readonly bookTypeLabels = BOOK_TYPE_LABELS;

  protected readonly bookType = signal<BookType>('transcricao_imobiliaria');
  protected readonly bookNumber = signal('');
  protected readonly firstPage = signal(1);
  protected readonly items = signal<UploadItem[]>([]);
  protected readonly running = signal(false);
  protected readonly dragOver = signal(false);

  protected readonly counts = computed(() => {
    const list = this.items();
    return {
      total: list.length,
      done: list.filter((i) => i.state === 'done').length,
      error: list.filter((i) => i.state === 'error').length,
      pending: list.filter((i) => i.state === 'queued' || i.state === 'processing').length,
    };
  });
  protected readonly canStart = computed(
    () => !this.running() && this.bookNumber().trim() !== '' && this.items().some((i) => i.state === 'queued'),
  );

  protected onFiles(fileList: FileList | null): void {
    if (!fileList) return;
    const files = Array.from(fileList)
      .filter((f) => ACCEPTED.test(f.name))
      // Ordem natural: fl_2.jpg antes de fl_10.jpg (padrão dos arquivos do digitalizador).
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    const start = this.items().length ? Math.max(...this.items().map((i) => i.page)) + 1 : this.firstPage();
    this.items.update((list) => [
      ...list,
      ...files.map((file, idx) => ({ key: this.nextKey++, file, page: start + idx, state: 'queued' as const })),
    ]);
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.set(false);
    this.onFiles(event.dataTransfer?.files ?? null);
  }

  protected setFirstPage(value: string): void {
    const n = Math.max(1, Number(value) || 1);
    this.firstPage.set(n);
    // Renumera as folhas ainda não enviadas mantendo a sequência.
    this.items.update((list) => list.map((item, idx) => (item.state === 'queued' ? { ...item, page: n + idx } : item)));
  }

  protected setPage(key: number, value: string): void {
    const n = Math.max(1, Number(value) || 1);
    this.patch(key, { page: n });
  }

  protected remove(key: number): void {
    this.items.update((list) => list.filter((i) => i.key !== key));
  }

  protected retry(key: number): void {
    this.patch(key, { state: 'queued', error: undefined });
    if (!this.running()) this.start();
  }

  protected clearFinished(): void {
    this.items.update((list) => list.filter((i) => i.state !== 'done'));
  }

  protected async start(): Promise<void> {
    if (this.running() || !this.bookNumber().trim()) return;
    this.running.set(true);
    await Promise.all(Array.from({ length: CONCURRENCY }, () => this.worker()));
    this.running.set(false);
  }

  private async worker(): Promise<void> {
    for (;;) {
      const item = this.items().find((i) => i.state === 'queued');
      if (!item) return;
      this.patch(item.key, { state: 'processing' });
      await new Promise<void>((resolve) => {
        this.api.transcribe(item.file, this.bookType(), this.bookNumber().trim(), item.page).subscribe({
          next: (rec) => {
            this.patch(item.key, { state: 'done', recordId: rec._id, confidence: rec.confidence_score });
            resolve();
          },
          error: (err) => {
            this.patch(item.key, { state: 'error', error: apiErrorMessage(err) });
            resolve();
          },
        });
      });
    }
  }

  private patch(key: number, changes: Partial<UploadItem>): void {
    this.items.update((list) => list.map((i) => (i.key === key ? { ...i, ...changes } : i)));
  }

  protected sizeMb(file: File): number {
    return file.size / 1024 / 1024;
  }
}
