import { Component, input, linkedSignal, output, signal } from '@angular/core';

import { ACT_TYPES, Qualification } from '../../models/qualification.model';

export function composeDevolutionNote(result: Qualification): string {
  const act = ACT_TYPES.find((type) => type.value === result.act_type)?.label ?? result.act_type;
  const items = result.checklist
    .filter((item) => item.status === 'PENDENCIA')
    .map((item, index) => {
      const lines = [`${index + 1}. ${item.rule_name}`, `   Constatação: ${item.finding}`];
      if (item.citation) {
        const page = item.page_number ? ` (p. ${item.page_number})` : '';
        lines.push(`   Trecho${page}: "${item.citation}"`);
      }
      if (item.recommendation) {
        lines.push(`   Providência: ${item.recommendation}`);
      }
      lines.push(`   Fundamentação: ${item.legal_ref}`);
      return lines.join('\n');
    });

  return [
    'NOTA DEVOLUTIVA',
    '',
    `Título: ${result.document_title}`,
    `Natureza do ato: ${act}`,
    `Data do exame: ${new Date(result.created_at).toLocaleDateString('pt-BR')}`,
    '',
    'Examinado o título apresentado, verificou-se a necessidade de cumprimento das seguintes EXIGÊNCIAS:',
    '',
    items.join('\n\n'),
    '',
    'Cumpridas as exigências acima, o título deverá ser reapresentado para novo exame.',
  ].join('\n');
}

@Component({
  selector: 'app-devolution-modal',
  template: `
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      (click)="closed.emit()"
      (keydown.escape)="closed.emit()"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="devolution-title"
        class="flex max-h-full w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl"
        (click)="$event.stopPropagation()"
      >
        <header class="border-b border-slate-200 px-5 py-3">
          <h2 id="devolution-title" class="text-lg font-semibold">Nota Devolutiva</h2>
          <p class="text-sm text-slate-600">Minuta gerada a partir das pendências. Revise e ajuste antes de copiar.</p>
        </header>
        <textarea
          class="min-h-96 flex-1 resize-none px-5 py-4 font-mono text-sm leading-relaxed outline-none"
          [value]="text()"
          (input)="text.set($any($event.target).value)"
        ></textarea>
        <footer class="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          @if (copyFailed()) {
            <span role="alert" class="mr-auto text-sm text-red-700">Não foi possível copiar. Selecione o texto e copie manualmente.</span>
          }
          <button type="button" class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50" (click)="closed.emit()">
            Fechar
          </button>
          <button type="button" class="rounded-md bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800" (click)="copy()">
            {{ copied() ? 'Copiado' : 'Copiar para Área de Transferência' }}
          </button>
        </footer>
      </div>
    </div>
  `,
})
export class DevolutionModalComponent {
  readonly result = input.required<Qualification>();
  readonly closed = output<void>();

  readonly text = linkedSignal(() => composeDevolutionNote(this.result()));
  readonly copied = signal(false);
  readonly copyFailed = signal(false);

  async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.text());
      this.copied.set(true);
      this.copyFailed.set(false);
      setTimeout(() => this.copied.set(false), 2000);
    } catch {
      this.copyFailed.set(true);
    }
  }
}
