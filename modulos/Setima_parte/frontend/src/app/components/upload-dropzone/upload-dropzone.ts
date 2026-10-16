import { Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { RedactionJob, SERVICE_TYPES, ServiceType } from '../../models/redaction.models';
import { RedactionService, errorMessage } from '../../services/redaction.service';

const ACCEPTED = /\.(pdf|docx|doc)$/i;

interface UploadEntry {
  name: string;
  state: 'waiting' | 'analyzing' | 'done' | 'error';
  message?: string;
}

@Component({
  selector: 'app-upload-dropzone',
  imports: [FormsModule],
  templateUrl: './upload-dropzone.html',
  styleUrl: './upload-dropzone.css',
})
export class UploadDropzone {
  private readonly api = inject(RedactionService);

  readonly operator = input.required<string>();
  readonly jobCreated = output<RedactionJob>();

  protected readonly serviceTypes = SERVICE_TYPES;
  protected serviceType: ServiceType = 'registro_civil';
  protected readonly dragging = signal(false);
  protected readonly queue = signal<UploadEntry[]>([]);
  protected readonly busy = signal(false);

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    this.enqueue(event.dataTransfer?.files);
  }

  protected onPick(event: Event): void {
    const el = event.target as HTMLInputElement;
    this.enqueue(el.files);
    el.value = '';
  }

  private async enqueue(list: FileList | null | undefined): Promise<void> {
    const files = Array.from(list ?? []);
    if (!files.length || this.busy()) return;
    this.queue.set(files.map((f) => ({ name: f.name, state: 'waiting' })));
    this.busy.set(true);
    // Processamento sequencial: evita sobrecarregar o backend e o provedor LLM.
    for (const [i, file] of files.entries()) {
      if (!ACCEPTED.test(file.name)) {
        this.update(i, { state: 'error', message: 'Formato não suportado (PDF, DOCX ou DOC)' });
        continue;
      }
      this.update(i, { state: 'analyzing', message: /\.pdf$/i.test(file.name) ? undefined : 'convertendo Word…' });
      try {
        const job = await firstValueFrom(this.api.analyze(file, this.serviceType, this.operator()));
        this.update(i, { state: 'done', message: `${job.total_detected} sugestão(ões)` });
        this.jobCreated.emit(job);
      } catch (err) {
        this.update(i, { state: 'error', message: await errorMessage(err) });
      }
    }
    this.busy.set(false);
  }

  private update(index: number, patch: Partial<UploadEntry>): void {
    this.queue.update((q) => q.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  }
}
