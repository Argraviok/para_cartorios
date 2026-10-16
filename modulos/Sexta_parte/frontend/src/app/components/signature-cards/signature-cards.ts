import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SignatureCard } from '../../models/fraud.models';
import { FraudService, apiError } from '../../services/fraud.service';

@Component({
  selector: 'app-signature-cards',
  imports: [FormsModule, DatePipe],
  template: `
    <div class="space-y-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">Cartões de firma</h1>
        <p class="text-sm text-slate-500">Padrões gráficos arquivados na serventia, usados no cotejo de assinaturas.</p>
      </div>

      <form class="card grid gap-4 p-5 md:grid-cols-5 md:items-end" (ngSubmit)="create()">
        <div><label class="label" for="ccpf">CPF *</label><input id="ccpf" class="input" name="cpf" [(ngModel)]="cpf" required /></div>
        <div class="md:col-span-2"><label class="label" for="cname">Nome completo *</label><input id="cname" class="input" name="name" [(ngModel)]="name" required /></div>
        <div><label class="label" for="cnum">Nº do cartão</label><input id="cnum" class="input" name="num" [(ngModel)]="number" /></div>
        <div><label class="label" for="cimg">Assinatura *</label><input id="cimg" type="file" accept="image/*" class="input" (change)="onFile($event)" /></div>
        @if (error()) { <div class="rounded-lg bg-red-50 p-3 text-sm text-red-800 md:col-span-4">{{ error() }}</div> }
        <button class="btn-primary md:col-start-5" type="submit" [disabled]="busy() || !file || !cpf || !name">Cadastrar</button>
      </form>

      <div class="card">
        <div class="border-b border-slate-200 p-4">
          <input class="input max-w-sm" placeholder="Buscar por nome ou CPF" [(ngModel)]="query" (ngModelChange)="load()" />
        </div>
        <div class="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
          @for (c of cards(); track c.id) {
            <div class="rounded-lg border border-slate-200 p-4">
              <div class="flex h-24 items-center justify-center rounded bg-slate-50">
                @if (images()[c.id]) { <img [src]="images()[c.id]" alt="Assinatura" class="max-h-20 object-contain" /> }
                @else { <button type="button" class="text-xs text-slate-500 underline" (click)="loadImage(c.id)">Exibir assinatura</button> }
              </div>
              <div class="mt-3 font-semibold">{{ c.full_name }}</div>
              <div class="text-xs text-slate-500">CPF {{ c.cpf }} · Cartão {{ c.card_number || '—' }} · {{ c.created_at | date: 'dd/MM/yyyy' }}</div>
            </div>
          } @empty {
            <p class="text-sm text-slate-500">Nenhum cartão encontrado.</p>
          }
        </div>
      </div>
    </div>
  `,
})
export class SignatureCards {
  private api = inject(FraudService);
  cards = signal<SignatureCard[]>([]);
  images = signal<Record<string, string>>({});
  error = signal('');
  busy = signal(false);
  query = '';
  cpf = '';
  name = '';
  number = '';
  file: File | null = null;

  constructor() {
    this.load();
    inject(DestroyRef).onDestroy(() => Object.values(this.images()).forEach((u) => URL.revokeObjectURL(u)));
  }

  load() {
    this.api.listCards(this.query.trim()).subscribe({ next: (c) => this.cards.set(c), error: (e) => this.error.set(apiError(e)) });
  }

  /** Imagens carregadas sob demanda: só exibe o padrão gráfico quando o escrevente solicita. */
  loadImage(id: string) {
    this.api.cardImageUrl(id).subscribe((u) => this.images.update((m) => ({ ...m, [id]: u })));
  }

  onFile(e: Event) {
    this.file = (e.target as HTMLInputElement).files?.[0] ?? null;
  }

  create() {
    if (!this.file) return;
    const form = new FormData();
    form.append('cpf', this.cpf);
    form.append('full_name', this.name);
    if (this.number) form.append('card_number', this.number);
    form.append('signature', this.file);
    this.busy.set(true);
    this.error.set('');
    this.api.createCard(form).subscribe({
      next: () => { this.cpf = this.name = this.number = ''; this.busy.set(false); this.load(); },
      error: (e) => { this.error.set(apiError(e)); this.busy.set(false); },
    });
  }
}
