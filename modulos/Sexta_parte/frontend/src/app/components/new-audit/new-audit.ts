import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { DocumentType } from '../../models/fraud.models';
import { FraudService, apiError } from '../../services/fraud.service';

@Component({
  selector: 'app-new-audit',
  imports: [FormsModule, RouterLink],
  templateUrl: './new-audit.html',
})
export class NewAudit {
  private api = inject(FraudService);
  private router = inject(Router);

  model = {
    protocol_number: '',
    service_type: 'escritura_compra_venda',
    document_type: 'RG' as DocumentType,
    presenter_name: '',
    presenter_cpf: '',
    procuration_book: '',
    procuration_page: '',
    procuration_act: '',
    procuration_origin_office: '',
    procuration_issued_on: '',
    procuration_revocation_declared: false,
    censec_confirmed_on: '',
  };
  hasProcuration = false;
  document: File | null = null;
  signature: File | null = null;
  submitting = signal(false);
  error = signal('');

  readonly serviceTypes = [
    ['escritura_compra_venda', 'Escritura de compra e venda'],
    ['escritura_doacao', 'Escritura de doação'],
    ['procuracao', 'Procuração'],
    ['reconhecimento_firma', 'Reconhecimento de firma'],
    ['registro_imovel', 'Registro de imóvel'],
    ['inventario_partilha', 'Inventário e partilha'],
  ];

  onFile(event: Event, kind: 'document' | 'signature') {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    if (kind === 'document') this.document = file;
    else this.signature = file;
  }

  submit() {
    if (!this.document) {
      this.error.set('Selecione o documento a ser analisado.');
      return;
    }
    const form = new FormData();
    form.append('document', this.document);
    if (this.signature) form.append('signature_image', this.signature);
    const procFields = new Set(['procuration_book', 'procuration_page', 'procuration_act', 'procuration_origin_office',
      'procuration_issued_on', 'procuration_revocation_declared', 'censec_confirmed_on']);
    for (const [k, v] of Object.entries(this.model)) {
      if (procFields.has(k) && !this.hasProcuration && this.model.document_type !== 'PROCURACAO') continue;
      if (v !== '' && v !== null) form.append(k, String(v));
    }
    this.submitting.set(true);
    this.error.set('');
    this.api.auditDocument(form).subscribe({
      next: (a) => this.router.navigate(['/audits', a.id]),
      error: (e) => { this.error.set(apiError(e)); this.submitting.set(false); },
    });
  }
}
