import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { CustomerChat } from '../../components/customer-chat/customer-chat';
import { ChatMessage, DOC_STATUS_META, Triage } from '../../models/triage.models';
import { TriageService, errorMessage } from '../../services/triage.service';

const PROTOCOL_KEY = 'triagem.protocol';
const POLL_MS = 4000;

@Component({
  selector: 'app-citizen-widget',
  imports: [CustomerChat],
  templateUrl: './citizen-widget.html',
})
export class CitizenWidget {
  private api = inject(TriageService);

  protected triage = signal<Triage | null>(null);
  protected pending = signal<ChatMessage[]>([]);
  protected typing = signal<string | null>(null);
  protected error = signal<string | null>(null);
  protected starting = signal(false);
  protected restoring = signal(true);
  protected sheetOpen = signal(false);
  protected name = signal('');
  protected contact = signal('');

  protected readonly docMeta = DOC_STATUS_META;
  private uploadTarget: number | null = null;
  private cameraInput = viewChild<ElementRef<HTMLInputElement>>('camera');
  private galleryInput = viewChild<ElementRef<HTMLInputElement>>('gallery');

  protected messages = computed(() => [...(this.triage()?.chat_history ?? []), ...this.pending()]);
  protected docs = computed(() => this.triage()?.checklist ?? []);
  protected validated = computed(() => this.docs().filter((d) => d.required && d.status === 'VALIDADO').length);
  protected busy = computed(() => this.typing() !== null);
  protected withHuman = computed(() => this.triage()?.status === 'human_takeover');

  constructor() {
    const saved = readProtocol();
    if (saved) {
      this.api.getSession(saved).subscribe({
        next: (t) => {
          this.triage.set(t);
          this.restoring.set(false);
        },
        error: () => {
          clearProtocol();
          this.restoring.set(false);
        },
      });
    } else {
      this.restoring.set(false);
    }
    // Busca mensagens do escrevente enquanto o chat está aberto
    const timer = setInterval(() => this.poll(), POLL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  private poll(): void {
    const t = this.triage();
    if (!t || this.busy() || document.hidden) return;
    this.api.getSession(t.protocol_id).subscribe({
      next: (fresh) => {
        if (!this.busy()) this.triage.set(fresh);
      },
      error: () => {},
    });
  }

  protected start(ev: Event): void {
    ev.preventDefault();
    const contact = this.contact().trim();
    if (contact.length < 3) {
      this.error.set('Informe seu WhatsApp ou e-mail para continuarmos.');
      return;
    }
    this.starting.set(true);
    this.error.set(null);
    this.api.startSession(contact, this.name().trim() || null).subscribe({
      next: (t) => {
        this.triage.set(t);
        saveProtocol(t.protocol_id);
        this.starting.set(false);
      },
      error: (e) => {
        this.error.set(errorMessage(e));
        this.starting.set(false);
      },
    });
  }

  protected send(text: string): void {
    const t = this.triage();
    if (!t) return;
    this.error.set(null);
    this.pending.set([{ sender: 'user', message: text, timestamp: new Date().toISOString() }]);
    this.typing.set(this.withHuman() ? null : 'Assistente digitando…');
    this.api.sendMessage(t.protocol_id, text).subscribe({
      next: (r) => {
        this.triage.set(r.triage);
        this.pending.set([]);
        this.typing.set(null);
      },
      error: (e) => {
        this.pending.set([]);
        this.typing.set(null);
        this.error.set(errorMessage(e));
      },
    });
  }

  protected pick(index: number | null, source: 'camera' | 'gallery'): void {
    this.uploadTarget = index;
    const el = (source === 'camera' ? this.cameraInput() : this.galleryInput())?.nativeElement;
    if (el) {
      el.value = '';
      el.click();
    }
  }

  protected onFile(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    const t = this.triage();
    if (!file || !t) return;
    this.sheetOpen.set(false);
    this.error.set(null);
    this.typing.set('Analisando seu documento…');
    this.api.uploadDoc(t.protocol_id, file, this.uploadTarget).subscribe({
      next: (r) => {
        this.triage.set(r.triage);
        this.typing.set(null);
      },
      error: (e) => {
        this.typing.set(null);
        this.error.set(errorMessage(e));
      },
    });
  }

  protected restart(): void {
    clearProtocol();
    this.triage.set(null);
    this.pending.set([]);
    this.sheetOpen.set(false);
  }

  protected openAttachment(url: string): void {
    window.open(url, '_blank', 'noopener');
  }
}

function readProtocol(): string | null {
  try {
    return localStorage.getItem(PROTOCOL_KEY);
  } catch {
    return null;
  }
}

function saveProtocol(p: string): void {
  try {
    localStorage.setItem(PROTOCOL_KEY, p);
  } catch {
    /* sem armazenamento: o atendimento vale só nesta aba */
  }
}

function clearProtocol(): void {
  try {
    localStorage.removeItem(PROTOCOL_KEY);
  } catch {
    /* ignore */
  }
}
