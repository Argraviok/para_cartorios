import {
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { ChatMessage } from '../../models/triage.models';
import { clock, isPdf } from '../../format';

/**
 * Histórico + caixa de mensagem.
 * mode "attendant": cidadão à esquerda; bot e escrevente à direita (visão do painel).
 * mode "citizen":   cidadão à direita; cartório à esquerda (visão do widget).
 */
@Component({
  selector: 'app-customer-chat',
  templateUrl: './customer-chat.html',
})
export class CustomerChat {
  messages = input.required<ChatMessage[]>();
  mode = input<'attendant' | 'citizen'>('attendant');
  placeholder = input('Escreva uma mensagem');
  disabled = input(false);
  typing = input<string | null>(null);
  allowAttach = input(false);
  send = output<string>();
  attach = output<void>();
  openImage = output<string>();

  protected draft = signal('');
  protected readonly clock = clock;
  protected readonly isPdf = isPdf;
  private scroller = viewChild<ElementRef<HTMLElement>>('scroller');
  private lastKey = '';

  protected rows = computed(() => {
    const msgs = this.messages();
    return msgs.map((m, i) => ({
      m,
      mine: this.isMine(m),
      day: i === 0 || !sameDay(msgs[i - 1].timestamp, m.timestamp) ? dayLabel(m.timestamp) : null,
      grouped: i > 0 && msgs[i - 1].sender === m.sender && m.sender !== 'system',
    }));
  });

  constructor() {
    // Rola para o fim só quando chega mensagem nova (o polling recria o array a cada ciclo)
    afterRenderEffect(() => {
      const key = `${this.messages().length}|${this.typing() ?? ''}`;
      const el = this.scroller()?.nativeElement;
      if (el && key !== this.lastKey) {
        this.lastKey = key;
        el.scrollTop = el.scrollHeight;
      }
    });
  }

  private isMine(m: ChatMessage): boolean {
    return this.mode() === 'citizen' ? m.sender === 'user' : m.sender === 'bot' || m.sender === 'attendant';
  }

  protected bubbleClass(m: ChatMessage, mine: boolean): string {
    if (m.sender === 'user') return mine ? 'bg-brand-600 text-white' : 'bg-white text-slate-800 ring-1 ring-stone-200';
    if (m.sender === 'attendant') return 'bg-indigo-50 text-slate-800 ring-1 ring-indigo-200';
    return mine ? 'bg-brand-50 text-slate-800 ring-1 ring-brand-100' : 'bg-white text-slate-800 ring-1 ring-stone-200';
  }

  protected author(m: ChatMessage): string {
    if (m.sender === 'bot') return 'Assistente virtual';
    if (m.sender === 'attendant') return m.attendant_name || 'Atendente';
    return this.mode() === 'citizen' ? 'Você' : 'Cidadão';
  }

  protected submit(ev?: Event): void {
    ev?.preventDefault();
    const text = this.draft().trim();
    if (!text || this.disabled()) return;
    this.send.emit(text);
    this.draft.set('');
  }

  protected onKey(ev: KeyboardEvent): void {
    if (ev.key === 'Enter' && !ev.shiftKey) this.submit(ev);
  }
}

function sameDay(a: string, b: string): boolean {
  return new Date(a).toDateString() === new Date(b).toDateString();
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return 'Hoje';
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
}
