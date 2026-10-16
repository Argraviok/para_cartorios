import { Component, input, output, signal } from '@angular/core';
import { CdkDragHandle } from '@angular/cdk/drag-drop';

import { RequirementEdit } from '../../../models/devolution.models';

type EditableField = 'legal_topic' | 'legal_basis' | 'suggested_solution';

@Component({
  selector: 'app-requirement-card',
  imports: [CdkDragHandle],
  template: `
    <div class="rounded-lg border bg-surface shadow-sm" [class]="r().grounded ? 'border-line' : 'border-warn-line'">
      <div class="flex items-center gap-2 px-3 py-2">
        @if (!readOnly()) {
          <button cdkDragHandle type="button" class="cursor-grab px-1 text-muted hover:text-ink" aria-label="Arrastar para reordenar"
                  title="Arrastar para reordenar">⠿</button>
        }
        <button type="button" class="flex min-w-0 flex-1 items-center gap-2 text-left" (click)="expanded.set(!expanded())"
                [attr.aria-expanded]="expanded()">
          <span class="text-sm font-semibold text-muted">{{ position() }}.</span>
          <span class="truncate text-sm font-semibold">{{ r().legal_topic || 'Sem título' }}</span>
        </button>
        <span class="rounded px-1.5 py-0.5 text-[11px] font-medium"
              [class]="r().source === 'ai' ? 'bg-accent/10 text-accent' : 'bg-subtle text-muted'">
          {{ r().source === 'ai' ? 'IA' : 'Manual' }}
        </span>
        @if (r().user_edited_text) {
          <span class="rounded bg-subtle px-1.5 py-0.5 text-[11px] font-medium text-muted">Editada</span>
        }
        <span class="text-muted">{{ expanded() ? '▾' : '▸' }}</span>
      </div>

      @if (!r().grounded && (!r().legal_basis.trim() || !r().suggested_solution.trim())) {
        <p class="mx-3 mb-2 rounded bg-warn-bg px-2 py-1 text-xs text-warn-ink">
          Sem fundamentação na base de precedentes: complete a fundamentação e a providência antes de emitir.
        </p>
      }

      @if (expanded()) {
        <div class="space-y-3 border-t border-line px-3 py-3">
          <label class="block">
            <span class="label">Título</span>
            <input class="field" [value]="r().legal_topic" [disabled]="readOnly()" (input)="set('legal_topic', $event)" />
          </label>
          <label class="block">
            <span class="label">Fundamentação legal</span>
            <textarea class="field min-h-14" [value]="r().legal_basis" [disabled]="readOnly()"
                      (input)="set('legal_basis', $event)" placeholder="Ex.: Lei 6.015/1973, art. 195"></textarea>
            @if (r().precedent_ids.length) {
              <span class="mt-1 block text-[11px] text-muted">Fichas: {{ r().precedent_ids.join(', ') }}</span>
            }
          </label>
          <label class="block">
            <span class="label flex items-center justify-between">
              Justificativa
              @if (r().user_edited_text && !readOnly()) {
                <button type="button" class="text-[11px] font-normal normal-case text-accent hover:underline"
                        (click)="restore()">Restaurar texto original</button>
              }
            </span>
            <textarea class="field min-h-36 font-serif text-[14px] leading-relaxed" [value]="text()" [disabled]="readOnly()"
                      (input)="setText($event)"></textarea>
          </label>
          <label class="block">
            <span class="label">Providência para sanar</span>
            <textarea class="field min-h-20" [value]="r().suggested_solution" [disabled]="readOnly()"
                      (input)="set('suggested_solution', $event)"></textarea>
          </label>
          @if (!readOnly()) {
            <div class="flex justify-end">
              <button type="button" class="btn btn-danger" (click)="remove.emit()">Excluir exigência</button>
            </div>
          }
        </div>
      }
    </div>
  `,
})
export class RequirementCard {
  readonly r = input.required<RequirementEdit>({ alias: 'requirement' });
  readonly position = input.required<number>();
  readonly readOnly = input(false);
  readonly startExpanded = input(false);

  readonly changed = output<RequirementEdit>();
  readonly remove = output<void>();

  readonly expanded = signal(false);

  ngOnInit(): void {
    this.expanded.set(this.startExpanded());
  }

  text(): string {
    return this.r().user_edited_text ?? this.r().justification_draft;
  }

  set(field: EditableField, event: Event): void {
    this.changed.emit({ ...this.r(), [field]: (event.target as HTMLInputElement).value });
  }

  setText(event: Event): void {
    // O texto original (IA ou fatos informados) é preservado em justification_draft para auditoria
    const value = (event.target as HTMLTextAreaElement).value;
    this.changed.emit({ ...this.r(), user_edited_text: value === this.r().justification_draft ? null : value });
  }

  restore(): void {
    this.changed.emit({ ...this.r(), user_edited_text: null });
  }
}
