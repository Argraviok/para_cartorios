import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  DECISION_META, FraudAuditSummary, FraudStats, OfficerDecision, RISK_META, RiskLevel,
} from '../../models/fraud.models';
import { FraudService, apiError } from '../../services/fraud.service';

@Component({
  selector: 'app-fraud-dashboard',
  imports: [RouterLink, FormsModule, DatePipe],
  templateUrl: './fraud-dashboard.html',
})
export class FraudDashboard {
  private api = inject(FraudService);
  readonly risk = RISK_META;
  readonly decisionMeta = DECISION_META;
  readonly levels: RiskLevel[] = ['CRITICO', 'ALTO', 'MEDIO', 'BAIXO'];

  audits = signal<FraudAuditSummary[]>([]);
  stats = signal<FraudStats | null>(null);
  loading = signal(true);
  error = signal('');
  riskFilter: RiskLevel | '' = '';
  decisionFilter: OfficerDecision | '' = 'PENDENTE';
  protocol = '';

  constructor() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.api.stats().subscribe({ next: (s) => this.stats.set(s), error: () => {} });
    this.api.listAudits({ risk_level: this.riskFilter, decision: this.decisionFilter, protocol: this.protocol.trim() })
      .subscribe({
        next: (a) => { this.audits.set(a); this.loading.set(false); },
        error: (e) => { this.error.set(apiError(e)); this.loading.set(false); },
      });
  }

  filterLevel(level: RiskLevel) {
    this.riskFilter = this.riskFilter === level ? '' : level;
    this.load();
  }
}
