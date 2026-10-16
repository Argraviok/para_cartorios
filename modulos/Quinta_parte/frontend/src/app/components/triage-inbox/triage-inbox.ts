import { Component, computed, input, output, signal } from '@angular/core';
import { STATUS_META, TriageStatus, TriageSummary } from '../../models/triage.models';
import { brl, timeAgo } from '../../format';

type Filter = 'all' | TriageStatus;

@Component({
  selector: 'app-triage-inbox',
  templateUrl: './triage-inbox.html',
})
export class TriageInbox {
  sessions = input.required<TriageSummary[]>();
  selectedId = input<string | null>(null);
  now = input<number>(Date.now());
  select = output<string>();

  protected filter = signal<Filter>('all');
  protected search = signal('');
  protected readonly meta = STATUS_META;
  protected readonly brl = brl;
  protected readonly timeAgo = timeAgo;

  protected readonly filters: { key: Filter; label: string; dot?: string }[] = [
    { key: 'all', label: 'Todos' },
    { key: 'human_takeover', label: 'Atendente', dot: STATUS_META.human_takeover.dot },
    { key: 'in_progress', label: 'Em triagem', dot: STATUS_META.in_progress.dot },
    { key: 'ready_for_counter', label: 'Prontos', dot: STATUS_META.ready_for_counter.dot },
  ];

  protected counts = computed(() => {
    const c: Record<Filter, number> = { all: 0, in_progress: 0, ready_for_counter: 0, human_takeover: 0 };
    for (const s of this.sessions()) {
      c.all++;
      c[s.status]++;
    }
    return c;
  });

  protected visible = computed(() => {
    const f = this.filter();
    const q = this.search().trim().toLowerCase();
    const order: Record<TriageStatus, number> = { human_takeover: 0, in_progress: 1, ready_for_counter: 2 };
    return this.sessions()
      .filter((s) => f === 'all' || s.status === f)
      .filter(
        (s) =>
          !q ||
          [s.customer_name, s.customer_contact, s.protocol_id, s.act_name].some((v) => v?.toLowerCase().includes(q)),
      )
      .sort((a, b) =>
        f === 'all' && order[a.status] !== order[b.status]
          ? order[a.status] - order[b.status]
          : b.updated_at.localeCompare(a.updated_at),
      );
  });

  protected progress(s: TriageSummary): number {
    return s.docs_required ? Math.round((s.docs_validated / s.docs_required) * 100) : 0;
  }

  protected initials(name: string | null): string {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
  }
}
