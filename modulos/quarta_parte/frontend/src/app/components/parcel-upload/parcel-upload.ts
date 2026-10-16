import { Component, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ParcelAnalysis } from '../../models/parcel.model';
import { ParcelService } from '../../services/parcel.service';

type Slot = 'matricula' | 'memorial' | 'titulo';

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.doc'];

interface SlotDef {
  key: Slot;
  label: string;
  hint: string;
  required: boolean;
}

@Component({
  selector: 'app-parcel-upload',
  imports: [FormsModule],
  templateUrl: './parcel-upload.html',
})
export class ParcelUpload {
  private readonly api = inject(ParcelService);
  readonly analyzed = output<ParcelAnalysis>();

  readonly accept = [
    ...ACCEPTED_EXTENSIONS,
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  ].join(',');

  readonly slots: SlotDef[] = [
    { key: 'matricula', label: 'Certidão de Matrícula', hint: 'Inteiro teor com todos os atos (R / AV)', required: true },
    { key: 'memorial', label: 'Memorial Descritivo', hint: 'Vértices, azimutes, distâncias ou coordenadas UTM', required: false },
    { key: 'titulo', label: 'Título / Contrato', hint: 'Escritura ou contrato com o vendedor', required: false },
  ];

  readonly files = signal<Record<Slot, File | null>>({ matricula: null, memorial: null, titulo: null });
  readonly dragOver = signal<Slot | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  sellerName = '';

  pick(slot: Slot, event: Event) {
    const input = event.target as HTMLInputElement;
    this.setFile(slot, input.files?.[0] ?? null);
    input.value = '';
  }

  drop(slot: Slot, event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(null);
    this.setFile(slot, event.dataTransfer?.files?.[0] ?? null);
  }

  clear(slot: Slot) {
    this.files.update((f) => ({ ...f, [slot]: null }));
  }

  private setFile(slot: Slot, file: File | null) {
    if (file && !ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext))) {
      this.error.set(`"${file.name}" não é um formato aceito. Envie PDF, DOCX ou DOC.`);
      return;
    }
    this.error.set(null);
    this.files.update((f) => ({ ...f, [slot]: file }));
  }

  submit() {
    const { matricula, memorial, titulo } = this.files();
    if (!matricula) {
      this.error.set('Selecione a certidão de matrícula.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.api.analyze({ matricula, memorial, titulo, sellerName: this.sellerName }).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.analyzed.emit(res);
      },
      error: (err: Error) => {
        this.loading.set(false);
        this.error.set(err.message);
      },
    });
  }

  size(file: File) {
    return file.size > 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(file.size / 1024)} KB`;
  }
}
