import { DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { STATUS_META, SignatureCheck } from '../../models/fraud.models';

const METRIC_LABEL: Record<string, string> = {
  forma_global: 'Morfologia geral',
  perfis_projecao: 'Distribuição gráfica',
  inclinacao: 'Inclinação global',
  proporcao: 'Proporcionalidade',
  interrupcoes_traco: 'Continuidade do traço',
  densidade_tinta: 'Densidade de tinta',
  espessura_traco: 'Calibre do traço',
  regularidade_traco: 'Variação de pressão',
};

/** Cotejo imediato: assinatura do título disposta diretamente acima do padrão arquivado. */
@Component({
  selector: 'app-signature-comparator',
  imports: [DecimalPipe, KeyValuePipe],
  template: `
    <section class="card p-5">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="font-semibold">Validação grafotécnica</h2>
        <span class="rounded px-2 py-0.5 text-xs font-semibold {{ status[check().status].cls }}">{{ status[check().status].label }}</span>
      </div>

      @if (signatureUrl() && cardUrl()) {
        <div class="space-y-2">
          <figure class="rounded-lg border border-slate-200 bg-white p-3">
            <figcaption class="mb-1 text-xs font-semibold uppercase text-slate-500">Assinatura no título</figcaption>
            <img [src]="signatureUrl()" alt="Assinatura do título" class="mx-auto max-h-36 object-contain" />
          </figure>
          <figure class="rounded-lg border border-dashed border-slate-300 bg-amber-50/40 p-3">
            <figcaption class="mb-1 text-xs font-semibold uppercase text-slate-500">Cartão de autógrafo (padrão da serventia)</figcaption>
            <img [src]="cardUrl()" alt="Cartão de firma" class="mx-auto max-h-36 object-contain" />
          </figure>
        </div>
      }

      @if (check().match_score !== null) {
        <div class="mt-4 flex items-baseline gap-3">
          <span class="text-3xl font-bold">{{ check().match_score }}</span>
          <span class="text-sm text-slate-500">/100 de compatibilidade · confiança {{ check().confidence * 100 | number: '1.0-0' }}%</span>
        </div>
        <div class="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
          @for (m of check().metrics | keyvalue; track m.key) {
            <div>
              <div class="flex justify-between text-xs"><span>{{ label(m.key) }}</span><span class="font-mono">{{ m.value * 100 | number: '1.0-0' }}</span></div>
              <div class="h-1.5 rounded bg-slate-100">
                <div class="h-1.5 rounded" [style.width.%]="m.value * 100"
                     [class]="m.value >= 0.7 ? 'bg-emerald-500' : m.value >= 0.45 ? 'bg-amber-400' : 'bg-red-500'"></div>
              </div>
            </div>
          }
        </div>
      }
      <p class="mt-4 text-sm text-slate-700">{{ check().observation }}</p>
      @if (check().vlm_error) { <p class="mt-2 text-xs text-amber-700">VLM indisponível: {{ check().vlm_error }}</p> }
      <p class="mt-3 text-xs text-slate-400">Triagem automatizada — não substitui exame grafotécnico pericial.</p>
    </section>
  `,
})
export class SignatureComparator {
  check = input.required<SignatureCheck>();
  signatureUrl = input<string | null>(null);
  cardUrl = input<string | null>(null);
  readonly status = STATUS_META;
  label = (k: string) => METRIC_LABEL[k] ?? k;
}
