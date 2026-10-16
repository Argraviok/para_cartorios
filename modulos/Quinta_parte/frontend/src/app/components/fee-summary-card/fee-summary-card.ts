import { Component, computed, input } from '@angular/core';
import { FeeEstimate } from '../../models/triage.models';
import { brl } from '../../format';

@Component({
  selector: 'app-fee-summary-card',
  template: `
    <section class="rounded-xl bg-white p-4 shadow-sm ring-1 ring-stone-200">
      <header class="mb-3 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-slate-900">Simulação de emolumentos</h3>
        @if (fee(); as f) {
          <span class="text-[11px] text-slate-500">{{ f.service_name }}</span>
        }
      </header>
      @if (fee(); as f) {
        @if (f.declared_value !== null) {
          <p class="mb-3 text-xs text-slate-500">
            Valor declarado <span class="font-semibold text-slate-700">{{ brl(f.declared_value) }}</span>
            @if (f.tier_label) {
              <br />Faixa: {{ f.tier_label }}
            }
          </p>
        }
        <dl class="space-y-1.5 text-sm">
          @for (row of rows(); track row.label) {
            <div class="flex justify-between gap-3">
              <dt class="text-slate-600">{{ row.label }}</dt>
              <dd class="tabular-nums">{{ brl(row.value) }}</dd>
            </div>
          }
          <div class="mt-2 flex justify-between gap-3 border-t border-dashed border-stone-300 pt-2 text-base font-semibold text-slate-900">
            <dt>Total estimado</dt>
            <dd class="tabular-nums">{{ brl(f.total_estimate) }}</dd>
          </div>
        </dl>
        <p class="mt-3 rounded-lg bg-amber-50 p-2.5 text-[11px] leading-snug text-amber-900">⚠️ {{ f.legal_disclaimer }}</p>
      } @else {
        <p class="text-sm text-slate-500">
          {{ waitingValue() ? 'Aguardando o cidadão informar o valor dos bens.' : 'Ainda não há serviço definido.' }}
        </p>
      }
    </section>
  `,
})
export class FeeSummaryCard {
  fee = input<FeeEstimate | null>(null);
  waitingValue = input(false);
  protected readonly brl = brl;

  protected rows = computed(() => {
    const f = this.fee();
    if (!f) return [];
    const pct = f.base_fee ? Math.round((f.municipal_tax / f.base_fee) * 1000) / 10 : 0;
    return [
      { label: 'Emolumentos do tabelião', value: f.base_fee },
      { label: 'Fundos estaduais', value: f.state_funds },
      { label: `ISSQN (${pct.toLocaleString('pt-BR')}%)`, value: f.municipal_tax },
    ];
  });
}
