import { Component, DestroyRef, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { ChecklistInspector } from '../../components/checklist-inspector/checklist-inspector';
import { CustomerChat } from '../../components/customer-chat/customer-chat';
import { DocLightbox, ReviewEvent } from '../../components/doc-lightbox/doc-lightbox';
import { FeeSummaryCard } from '../../components/fee-summary-card/fee-summary-card';
import { TriageInbox } from '../../components/triage-inbox/triage-inbox';
import { brl, timeAgo } from '../../format';
import { STATUS_META, Triage, TriageSummary } from '../../models/triage.models';
import { TriageService, errorMessage } from '../../services/triage.service';

const POLL_MS = 3000;
const NAME_KEY = 'triagem.attendantName';

@Component({
  selector: 'app-attendant-panel',
  imports: [TriageInbox, CustomerChat, ChecklistInspector, FeeSummaryCard, DocLightbox, RouterLink],
  templateUrl: './attendant-panel.html',
})
export class AttendantPanel {
  protocolId = input<string | undefined>(undefined);

  private api = inject(TriageService);
  private router = inject(Router);

  protected sessions = signal<TriageSummary[]>([]);
  protected triage = signal<Triage | null>(null);
  protected loadingList = signal(true);
  protected busy = signal(false);
  protected error = signal<string | null>(null);
  protected lightbox = signal<number | null>(null);
  protected now = signal(Date.now());
  protected attendantName = signal(readName());
  protected editingName = signal(false);

  protected readonly meta = STATUS_META;
  protected readonly brl = brl;
  protected readonly timeAgo = timeAgo;

  protected selected = computed(() => {
    const t = this.triage();
    return t && t.protocol_id === this.protocolId() ? t : null;
  });
  protected lightboxItem = computed(() => {
    const i = this.lightbox();
    const t = this.selected();
    return i !== null && t ? (t.checklist[i] ?? null) : null;
  });
  protected checklistDone = computed(() => {
    const items = this.selected()?.checklist.filter((c) => c.required) ?? [];
    return items.length > 0 && items.every((c) => c.status === 'VALIDADO');
  });
  protected pendingReview = computed(() => this.selected()?.checklist.filter((c) => c.status === 'ENVIADO').length ?? 0);

  constructor() {
    const timer = setInterval(() => {
      this.now.set(Date.now());
      this.refreshList();
      this.refreshSelected();
    }, POLL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
    this.refreshList();

    // Troca de atendimento pela rota
    effect(() => {
      const id = this.protocolId();
      untracked(() => {
        this.lightbox.set(null);
        if (id) this.refreshSelected(true);
        else this.triage.set(null);
      });
    });
  }

  private inflightList = false;
  private refreshList(): void {
    if (this.inflightList) return;
    this.inflightList = true;
    this.api.listSessions().subscribe({
      next: (s) => {
        this.sessions.set(s);
        this.loadingList.set(false);
        this.inflightList = false;
      },
      error: (e) => {
        this.error.set(errorMessage(e));
        this.loadingList.set(false);
        this.inflightList = false;
      },
    });
  }

  private inflightOne = false;
  private refreshSelected(force = false): void {
    const id = this.protocolId();
    if (!id || (this.inflightOne && !force) || this.busy()) return;
    this.inflightOne = true;
    this.api.getSession(id).subscribe({
      next: (t) => {
        if (t.protocol_id === this.protocolId()) this.triage.set(t);
        this.inflightOne = false;
      },
      error: (e) => {
        this.inflightOne = false;
        if (force) this.error.set(errorMessage(e));
      },
    });
  }

  protected select(id: string): void {
    this.router.navigate(['/painel', id]);
  }

  private run(call: Observable<Triage>): void {
    this.busy.set(true);
    this.error.set(null);
    call.subscribe({
      next: (t) => {
        this.triage.set(t);
        this.busy.set(false);
        this.refreshList();
      },
      error: (e) => {
        this.error.set(errorMessage(e));
        this.busy.set(false);
      },
    });
  }

  protected takeover(): void {
    const t = this.selected();
    if (t) this.run(this.api.takeover(t.protocol_id, this.attendantName()));
  }

  protected release(): void {
    const t = this.selected();
    if (t) this.run(this.api.release(t.protocol_id));
  }

  protected sendMessage(text: string): void {
    const t = this.selected();
    if (t) this.run(this.api.attendantMessage(t.protocol_id, text, this.attendantName()));
  }

  protected review(ev: ReviewEvent): void {
    const t = this.selected();
    const i = this.lightbox();
    if (t && i !== null) this.run(this.api.reviewDoc(t.protocol_id, i, ev.status, ev.reason));
  }

  protected ticket(): void {
    const t = this.selected();
    if (t) this.run(this.api.counterTicket(t.protocol_id));
  }

  protected stepLightbox(delta: number): void {
    const t = this.selected();
    const i = this.lightbox();
    if (!t || i === null || !t.checklist.length) return;
    this.lightbox.set((i + delta + t.checklist.length) % t.checklist.length);
  }

  protected openImage(url: string): void {
    const i = this.selected()?.checklist.findIndex((c) => c.image_url === url) ?? -1;
    if (i >= 0) this.lightbox.set(i);
    else window.open(url, '_blank', 'noopener');
  }

  protected saveName(value: string): void {
    const name = value.trim() || 'Escrevente';
    this.attendantName.set(name);
    this.editingName.set(false);
    try {
      localStorage.setItem(NAME_KEY, name);
    } catch {
      /* armazenamento indisponível: mantém só nesta aba */
    }
  }
}

function readName(): string {
  try {
    return localStorage.getItem(NAME_KEY) || 'Escrevente';
  } catch {
    return 'Escrevente';
  }
}
