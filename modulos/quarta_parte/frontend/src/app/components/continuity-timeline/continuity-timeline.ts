import { Component, computed, input } from '@angular/core';

import { Alert, SubjectiveContinuity } from '../../models/parcel.model';

const STATUS_LABEL = {
  REGULAR: 'Continuidade regular',
  ALERTA: 'Atenção',
  QUEBRA_DETECTADA: 'Quebra de continuidade detectada',
} as const;

const ACT_LABEL: Record<string, string> = {
  COMPRA_E_VENDA: 'Compra e venda',
  DOACAO: 'Doação',
  PARTILHA: 'Partilha',
  ARREMATACAO: 'Arrematação',
  ADJUDICACAO: 'Adjudicação',
  USUCAPIAO: 'Usucapião',
  PERMUTA: 'Permuta',
  PENHORA: 'Penhora',
  HIPOTECA: 'Hipoteca',
  INDISPONIBILIDADE: 'Indisponibilidade (CNIB)',
  USUFRUTO: 'Usufruto',
  ALIENACAO_FIDUCIARIA: 'Alienação fiduciária',
  ARRESTO: 'Arresto',
};

@Component({
  selector: 'app-continuity-timeline',
  templateUrl: './continuity-timeline.html',
})
export class ContinuityTimeline {
  readonly continuity = input.required<SubjectiveContinuity>();
  readonly alerts = input<Alert[]>([]);

  readonly statusLabel = computed(() => STATUS_LABEL[this.continuity().status]);
  readonly isBreak = computed(() => this.continuity().status === 'QUEBRA_DETECTADA');

  /** Alertas sem card próprio (continuidade, ônus e avisos geométricos já aparecem em outros painéis). */
  readonly otherAlerts = computed(() =>
    this.alerts().filter(
      (a) => a.code !== 'QUEBRA_CONTINUIDADE' && a.code !== 'GEOMETRIA' && !a.code.startsWith('ONUS_'),
    ),
  );

  actLabel(type: string) {
    return ACT_LABEL[type] ?? type.replaceAll('_', ' ').toLowerCase();
  }
}
