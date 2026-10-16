import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import {
  ACTION_LABEL, DECISION_META, DecisionAction, DecisionRequest, FileKind, FraudAudit, STATUS_META,
} from '../../models/fraud.models';
import { FraudService, apiError } from '../../services/fraud.service';
import { DecisionModal } from '../decision-modal/decision-modal';
import { RiskGauge } from '../risk-gauge/risk-gauge';
import { SignatureComparator } from '../signature-comparator/signature-comparator';

type OverlayMode = 'heatmap' | 'ela';

@Component({
  selector: 'app-forensic-inspector',
  imports: [RouterLink, FormsModule, DatePipe, RiskGauge, SignatureComparator, DecisionModal],
  templateUrl: './forensic-inspector.html',
})
export class ForensicInspector {
  /** Parâmetro de rota (withComponentInputBinding). */
  id = input.required<string>();

  private api = inject(FraudService);
  readonly status = STATUS_META;
  readonly decisionMeta = DECISION_META;
  readonly actionLabel = ACTION_LABEL;
  readonly actions: DecisionAction[] = ['APROVAR_FE_PUBLICA', 'SOLICITAR_PRESENCIAL', 'REJEITAR_FALSIDADE'];

  audit = signal<FraudAudit | null>(null);
  error = signal('');
  urls = signal<Partial<Record<FileKind, string>>>({});
  overlay: OverlayMode = 'heatmap';
  slider = 50;
  showRegions = true;

  pendingAction = signal<DecisionAction | null>(null);
  deciding = signal(false);
  decisionError = signal('');

  tampering = computed(() => this.audit()?.checks.document_tampering);
  isFinal = computed(() => this.audit()?.officer_decision !== 'PENDENTE');
  highRisk = computed(() => ['ALTO', 'CRITICO'].includes(this.audit()?.risk_level ?? ''));

  constructor() {
    inject(DestroyRef).onDestroy(() => Object.values(this.urls()).forEach((u) => u && URL.revokeObjectURL(u)));
  }

  ngOnInit() {
    this.api.getAudit(this.id()).subscribe({
      next: (a) => { this.audit.set(a); this.loadFiles(a); },
      error: (e) => this.error.set(apiError(e)),
    });
  }

  private loadFiles(a: FraudAudit) {
    const kinds = (Object.keys(a.files) as FileKind[]).filter((k) => a.files[k]);
    const reqs = Object.fromEntries(kinds.map((k) => [k, this.api.fileUrl(a.id, k).pipe(catchError(() => of('')))]));
    if (kinds.length) forkJoin(reqs).subscribe((u) => this.urls.set(u));
  }

  regionStyle(r: { x: number; y: number; w: number; h: number }) {
    const t = this.tampering()!;
    return {
      left: `${(r.x / t.image_width) * 100}%`, top: `${(r.y / t.image_height) * 100}%`,
      width: `${(r.w / t.image_width) * 100}%`, height: `${(r.h / t.image_height) * 100}%`,
    };
  }

  decide(body: DecisionRequest) {
    const a = this.audit();
    if (!a) return;
    this.deciding.set(true);
    this.decisionError.set('');
    this.api.decide(a.id, body).subscribe({
      next: (updated) => { this.audit.set(updated); this.pendingAction.set(null); this.deciding.set(false); },
      error: (e) => { this.decisionError.set(apiError(e)); this.deciding.set(false); },
    });
  }
}
