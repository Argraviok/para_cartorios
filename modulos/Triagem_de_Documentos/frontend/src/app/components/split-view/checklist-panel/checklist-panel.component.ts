import { Component, computed, input, output } from '@angular/core';

import { FindingStatus, Qualification, RuleFinding } from '../../../models/qualification.model';

const STATUS_STYLE: Record<FindingStatus, { label: string; card: string; badge: string }> = {
  CONFORME: { label: 'Conforme', card: 'border-l-green-600', badge: 'bg-green-100 text-green-800' },
  PENDENCIA: { label: 'Pendência', card: 'border-l-red-600', badge: 'bg-red-100 text-red-800' },
  ALERTA: { label: 'Alerta', card: 'border-l-amber-500', badge: 'bg-amber-100 text-amber-900' },
};

@Component({
  selector: 'app-checklist-panel',
  template: `
    <header
      class="border-b px-4 py-3"
      [class]="approved() ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'"
    >
      <p class="truncate text-xs text-slate-600" [title]="result().document_title">{{ result().document_title }}</p>
      <h2 class="text-lg font-semibold" [class]="approved() ? 'text-green-900' : 'text-red-900'">
        {{ approved() ? 'Aprovado' : 'Com exigências' }}
      </h2>
      <p class="text-sm text-slate-700">
        {{ count('PENDENCIA') }} pendência(s) · {{ count('ALERTA') }} alerta(s) · {{ count('CONFORME') }} conforme(s)
      </p>
      <div class="mt-3 flex gap-2">
        <button
          type="button"
          class="rounded-md bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          [disabled]="count('PENDENCIA') === 0"
          (click)="devolutionRequested.emit()"
        >
          Gerar Nota Devolutiva
        </button>
        <button
          type="button"
          class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          (click)="restart.emit()"
        >
          Novo documento
        </button>
      </div>
    </header>

    <ul class="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      @for (item of result().checklist; track item.rule_code) {
        <li>
          <button
            type="button"
            class="w-full rounded-md border border-l-4 border-slate-200 bg-white p-3 text-left shadow-sm transition-shadow"
            [class]="style(item).card + (item.page_number ? ' cursor-pointer hover:shadow-md' : ' cursor-default')"
            (click)="select(item)"
          >
            <div class="flex items-start justify-between gap-2">
              <h3 class="text-sm font-semibold">{{ item.rule_name }}</h3>
              <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium" [class]="style(item).badge">
                {{ style(item).label }}
              </span>
            </div>
            <p class="mt-0.5 text-xs text-slate-500">
              {{ item.severity === 'impeditiva' ? 'Impeditiva' : 'Recomendável' }} · {{ item.legal_ref }}
            </p>
            <p class="mt-2 text-sm text-slate-800">{{ item.finding }}</p>
            @if (item.citation) {
              <blockquote class="mt-2 border-l-2 border-slate-300 pl-2 text-sm italic text-slate-600">
                “{{ item.citation }}”
                @if (item.page_number) {
                  <span class="not-italic text-slate-500"> — p. {{ item.page_number }}</span>
                }
              </blockquote>
              @if (!item.citation_verified) {
                <p class="mt-1 text-xs font-medium text-amber-800">
                  Trecho não localizado literalmente no PDF: confira no documento.
                </p>
              }
            }
            @if (item.recommendation) {
              <p class="mt-2 text-sm"><span class="font-medium">Providência:</span> {{ item.recommendation }}</p>
            }
          </button>
        </li>
      }
    </ul>
  `,
  host: { class: 'flex h-full flex-col bg-slate-50' },
})
export class ChecklistPanelComponent {
  readonly result = input.required<Qualification>();
  readonly pageSelected = output<number>();
  readonly devolutionRequested = output<void>();
  readonly restart = output<void>();

  readonly approved = computed(() => this.result().overall_status === 'APROVADO');

  count(status: FindingStatus): number {
    return this.result().checklist.filter((item) => item.status === status).length;
  }

  style(item: RuleFinding) {
    return STATUS_STYLE[item.status];
  }

  select(item: RuleFinding): void {
    if (item.page_number) {
      this.pageSelected.emit(item.page_number);
    }
  }
}
