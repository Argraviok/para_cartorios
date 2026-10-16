import { Component, computed, input } from '@angular/core';
import { RISK_META, RiskLevel } from '../../models/fraud.models';

/** Medidor semicircular do score de risco (0–100). */
@Component({
  selector: 'app-risk-gauge',
  template: `
    <div class="flex flex-col items-center">
      <svg viewBox="0 0 200 115" class="w-48">
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#e2e8f0" stroke-width="16" stroke-linecap="round" />
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" [attr.stroke]="meta().hex" stroke-width="16"
              stroke-linecap="round" pathLength="100" [attr.stroke-dasharray]="score() + ' 100'" />
        <text x="100" y="88" text-anchor="middle" class="fill-slate-900" font-size="34" font-weight="700">{{ score() }}</text>
        <text x="100" y="108" text-anchor="middle" class="fill-slate-500" font-size="11">de 100</text>
      </svg>
      <span class="mt-1 rounded-full px-3 py-1 text-sm font-bold ring-1 {{ meta().badge }}">RISCO {{ meta().label.toUpperCase() }}</span>
      <span class="mt-2 text-xs font-medium" [class]="retained() ? 'text-red-700' : 'text-emerald-700'">
        {{ retained() ? 'Retido para conferência do titular' : 'Liberado para conferência usual' }}
      </span>
    </div>
  `,
})
export class RiskGauge {
  score = input.required<number>();
  level = input.required<RiskLevel>();
  meta = computed(() => RISK_META[this.level()]);
  retained = computed(() => this.level() === 'ALTO' || this.level() === 'CRITICO');
}
