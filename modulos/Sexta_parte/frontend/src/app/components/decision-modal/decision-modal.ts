import { Component, computed, effect, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ACTION_LABEL, DecisionAction, DecisionRequest } from '../../models/fraud.models';

const OFFICER_KEY = 'antifraude.officer_name';

@Component({
  selector: 'app-decision-modal',
  imports: [FormsModule],
  template: `
    @if (action(); as act) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" (click)="cancel.emit()">
        <form class="card w-full max-w-lg space-y-4 p-6" (click)="$event.stopPropagation()" (ngSubmit)="submit(act)">
          <div>
            <h2 class="text-lg font-bold">{{ labels[act] }}</h2>
            <p class="text-sm text-slate-500">O despacho será gravado no log de auditoria com data, hora e responsável.
              @if (act !== 'SOLICITAR_PRESENCIAL') { <strong>Decisão final e irretratável no sistema.</strong> }
            </p>
          </div>
          @if (act === 'APROVAR_FE_PUBLICA' && highRisk()) {
            <div class="rounded-lg bg-red-50 p-3 text-sm text-red-800">
              Atenção: a IA classificou este ato como de risco elevado. A homologação exige justificativa circunstanciada.
            </div>
          }
          <div>
            <label class="label" for="officer">Oficial / Escrevente autorizado *</label>
            <input id="officer" class="input" name="officer" required minlength="3" [(ngModel)]="officerName" />
          </div>
          <div>
            <label class="label" for="notes">Justificativa *</label>
            <textarea id="notes" class="input min-h-28" name="notes" required minlength="10" [(ngModel)]="notes"
                      [placeholder]="placeholder()"></textarea>
            <p class="mt-1 text-xs text-slate-400">Mínimo de 10 caracteres.</p>
          </div>
          @if (error()) { <div class="rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error() }}</div> }
          <div class="flex justify-end gap-3">
            <button type="button" class="btn-ghost" (click)="cancel.emit()">Cancelar</button>
            <button type="submit" [class]="act === 'REJEITAR_FALSIDADE' ? 'btn bg-red-700 text-white hover:bg-red-600' : 'btn-primary'"
                    [disabled]="busy() || officerName.trim().length < 3 || notes.trim().length < 10">
              {{ busy() ? 'Gravando…' : 'Confirmar despacho' }}
            </button>
          </div>
        </form>
      </div>
    }
  `,
})
export class DecisionModal {
  action = input<DecisionAction | null>(null);
  highRisk = input(false);
  busy = input(false);
  error = input('');
  confirm = output<DecisionRequest>();
  cancel = output<void>();

  readonly labels = ACTION_LABEL;
  officerName = '';
  notes = '';

  placeholder = computed(() => ({
    APROVAR_FE_PUBLICA: 'Ex.: Conferido documento original e biometria; divergência de ELA decorre de etiqueta plastificada…',
    SOLICITAR_PRESENCIAL: 'Ex.: Convocar outorgante para comparecimento com documento original e coleta de biometria.',
    REJEITAR_FALSIDADE: 'Ex.: Indícios de inserção digital no campo CPF e assinatura divergente do cartão nº…',
  })[this.action() ?? 'APROVAR_FE_PUBLICA']);

  constructor() {
    try { this.officerName = localStorage.getItem(OFFICER_KEY) ?? ''; } catch { /* armazenamento indisponível */ }
    effect(() => { if (this.action()) this.notes = ''; });
  }

  submit(action: DecisionAction) {
    try { localStorage.setItem(OFFICER_KEY, this.officerName.trim()); } catch { /* ignore */ }
    this.confirm.emit({ action, officer_name: this.officerName.trim(), notes: this.notes.trim() });
  }
}
