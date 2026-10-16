import { Component, computed, input, output } from '@angular/core';
import { ChecklistItem, DOC_STATUS_META } from '../../models/triage.models';
import { isPdf } from '../../format';

@Component({
  selector: 'app-checklist-inspector',
  template: `
    <section class="rounded-xl bg-white shadow-sm ring-1 ring-stone-200">
      <header class="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <h3 class="text-sm font-semibold text-slate-900">Checklist de documentos</h3>
        <span class="text-xs text-slate-500 tabular-nums">{{ validated() }} de {{ required() }} validados</span>
      </header>
      @if (items().length) {
        <ul class="divide-y divide-stone-100">
          @for (item of items(); track item.doc_name; let i = $index) {
            <li>
              <button
                type="button"
                class="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-stone-50 disabled:cursor-default disabled:hover:bg-transparent"
                [disabled]="!item.image_url && !interactiveWithoutImage()"
                (click)="open.emit(i)"
              >
                <div class="relative h-12 w-12 shrink-0 overflow-hidden rounded-md bg-stone-100 ring-1 ring-stone-200">
                  @if (item.image_url) {
                    @if (isPdf(item.image_url, item.content_type)) {
                      <div class="flex h-full items-center justify-center text-[10px] font-bold text-rose-700">PDF</div>
                    } @else {
                      <img [src]="item.image_url" alt="" class="h-full w-full object-cover" loading="lazy" />
                    }
                  } @else {
                    <div class="flex h-full items-center justify-center text-slate-300">
                      <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
                    </div>
                  }
                </div>
                <div class="min-w-0 flex-1">
                  <p class="text-sm leading-snug font-medium text-slate-800">{{ item.doc_name }}</p>
                  @if (item.status === 'REJEITADO' && item.rejection_reason) {
                    <p class="mt-0.5 line-clamp-2 text-xs text-rose-700">{{ item.rejection_reason }}</p>
                  } @else if (item.validated_by) {
                    <p class="mt-0.5 text-xs text-slate-500">{{ item.validated_by === 'ai' ? 'Validado pela IA' : 'Conferido pelo escrevente' }}</p>
                  } @else if (item.status === 'ENVIADO') {
                    <p class="mt-0.5 text-xs text-sky-700">Clique para conferir</p>
                  }
                </div>
                <span class="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold" [class]="meta[item.status].cls">
                  {{ meta[item.status].icon }} {{ meta[item.status].label }}
                </span>
              </button>
            </li>
          }
        </ul>
      } @else {
        <p class="px-4 py-6 text-sm text-slate-500">O checklist é criado assim que o serviço for identificado.</p>
      }
    </section>
  `,
})
export class ChecklistInspector {
  items = input.required<ChecklistItem[]>();
  interactiveWithoutImage = input(true);
  open = output<number>();

  protected readonly meta = DOC_STATUS_META;
  protected readonly isPdf = isPdf;
  protected required = computed(() => this.items().filter((i) => i.required).length);
  protected validated = computed(() => this.items().filter((i) => i.required && i.status === 'VALIDADO').length);
}
