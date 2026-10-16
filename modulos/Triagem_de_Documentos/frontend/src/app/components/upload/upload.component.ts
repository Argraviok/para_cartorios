import { Component, input, output, signal } from '@angular/core';

import { ACT_TYPES } from '../../models/qualification.model';

export interface UploadRequest {
  file: File;
  actType: string;
}

@Component({
  selector: 'app-upload',
  template: `
    <main class="mx-auto flex min-h-full max-w-xl flex-col justify-center gap-6 px-4 py-12">
      <header>
        <h1 class="text-2xl font-semibold">Exame Qualificativo</h1>
        <p class="mt-1 text-sm text-slate-600">
          Envie a minuta em PDF ou Word para conferência automática contra as regras do ato.
        </p>
      </header>

      <label class="flex flex-col gap-1 text-sm font-medium">
        Tipo de ato
        <select
          class="rounded-md border border-slate-300 bg-white px-3 py-2 font-normal"
          [value]="actType()"
          (change)="actType.set($any($event.target).value)"
          [disabled]="loading()"
        >
          @for (type of actTypes; track type.value) {
            <option [value]="type.value">{{ type.label }}</option>
          }
        </select>
      </label>

      <label
        class="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed bg-white px-6 py-12 text-center transition-colors"
        [class]="dragging() ? 'border-blue-500 bg-blue-50' : 'border-slate-300 hover:border-slate-400'"
        (dragover)="onDragOver($event)"
        (dragleave)="dragging.set(false)"
        (drop)="onDrop($event)"
      >
        <input type="file" accept=".pdf,.docx,.doc" class="sr-only" (change)="onPick($event)" [disabled]="loading()" />
        @if (file(); as file) {
          <span class="font-medium">{{ file.name }}</span>
          <span class="text-sm text-slate-500">{{ (file.size / 1024 / 1024).toFixed(1) }} MB · clique para trocar</span>
        } @else {
          <span class="font-medium">Arraste o PDF ou Word aqui</span>
          <span class="text-sm text-slate-500">ou clique para selecionar o arquivo</span>
        }
      </label>

      @if (localError() || error(); as message) {
        <p role="alert" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{{ message }}</p>
      }

      <button
        type="button"
        class="rounded-md bg-blue-700 px-4 py-2.5 font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        [disabled]="!file() || loading()"
        (click)="submit()"
      >
        {{ loading() ? 'Analisando a minuta…' : 'Analisar documento' }}
      </button>
      @if (loading()) {
        <p class="text-center text-sm text-slate-500">A análise pode levar até um minuto.</p>
      }
    </main>
  `,
  host: { class: 'block h-full' },
})
export class UploadComponent {
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly submitted = output<UploadRequest>();

  readonly actTypes = ACT_TYPES;
  readonly actType = signal(ACT_TYPES[0].value);
  readonly file = signal<File | null>(null);
  readonly dragging = signal(false);
  readonly localError = signal<string | null>(null);

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(true);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    if (!this.loading()) {
      this.select(event.dataTransfer?.files[0]);
    }
  }

  onPick(event: Event): void {
    this.select((event.target as HTMLInputElement).files?.[0]);
  }

  submit(): void {
    const file = this.file();
    if (file) {
      this.submitted.emit({ file, actType: this.actType() });
    }
  }

  private select(file: File | undefined): void {
    if (!file) {
      return;
    }
    if (!/\.(pdf|docx|doc)$/i.test(file.name)) {
      this.localError.set('Apenas arquivos PDF ou Word (.docx, .doc) são suportados.');
      return;
    }
    this.localError.set(null);
    this.file.set(file);
  }
}
