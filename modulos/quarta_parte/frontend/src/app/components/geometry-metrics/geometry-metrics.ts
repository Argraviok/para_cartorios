import { Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';

import { GeometryAnalysis } from '../../models/parcel.model';

/** Regra de qualidade registral: divergência de área acima de 5% gera aviso. */
const AREA_TOLERANCE_PERCENT = 5;

@Component({
  selector: 'app-geometry-metrics',
  imports: [DecimalPipe],
  templateUrl: './geometry-metrics.html',
})
export class GeometryMetrics {
  readonly geometry = input.required<GeometryAnalysis>();
  readonly tolerance = AREA_TOLERANCE_PERCENT;

  readonly areaDiverges = computed(() => (this.geometry().area_difference_percent ?? 0) > AREA_TOLERANCE_PERCENT);

  /** Precisão relativa da poligonal (1:N), padrão em levantamentos topográficos. */
  readonly precision = computed(() => {
    const g = this.geometry();
    if (g.closure_method !== 'TRAVERSE' || g.gap_meters <= 0) return null;
    return Math.round(g.perimeter_m / g.gap_meters);
  });
}
