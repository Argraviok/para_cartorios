import { Component, ElementRef, afterRenderEffect, computed, inject, input, output, signal } from '@angular/core';

import { BoundingBox, CATEGORY_META, PageInfo, RedactionItem, RedactionJob } from '../../models/redaction.models';
import { RedactionService } from '../../services/redaction.service';

interface Draft {
  page: PageInfo;
  surface: HTMLElement;
  startX: number;
  startY: number;
  box: BoundingBox;
}

/** Tarjas menores que isso (em pontos PDF) são tratadas como clique acidental. */
const MIN_SIZE_PT = 4;

@Component({
  selector: 'app-redaction-viewer',
  templateUrl: './redaction-viewer.html',
  styleUrl: './redaction-viewer.css',
})
export class RedactionViewer {
  private readonly api = inject(RedactionService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly job = input.required<RedactionJob>();
  readonly items = input.required<RedactionItem[]>();
  readonly selectedId = input<string | null>(null);
  readonly drawMode = input(false);
  readonly readonly = input(false);

  readonly toggle = output<string>();
  readonly select = output<string>();
  readonly drawn = output<{ page: number; box: BoundingBox }>();

  protected readonly meta = CATEGORY_META;
  protected readonly draft = signal<Draft | null>(null);

  protected readonly itemsByPage = computed(() => {
    const map = new Map<number, RedactionItem[]>();
    for (const item of this.items()) {
      const list = map.get(item.page_number) ?? [];
      list.push(item);
      map.set(item.page_number, list);
    }
    return map;
  });

  constructor() {
    // Ao selecionar um achado na barra lateral, rola até ele.
    afterRenderEffect(() => {
      const id = this.selectedId();
      if (!id) return;
      this.host.nativeElement
        .querySelector(`[data-rid="${CSS.escape(id)}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  protected imageUrl(page: number): string {
    return this.api.pageImageUrl(this.job().job_id, page);
  }

  /** Posição em % para que o overlay acompanhe qualquer largura de renderização. */
  protected boxStyle(box: BoundingBox, page: PageInfo): Record<string, string> {
    return {
      left: `${(box.x0 / page.width) * 100}%`,
      top: `${(box.y0 / page.height) * 100}%`,
      width: `${((box.x1 - box.x0) / page.width) * 100}%`,
      height: `${((box.y1 - box.y0) / page.height) * 100}%`,
    };
  }

  protected onOverlayClick(event: MouseEvent, item: RedactionItem): void {
    event.stopPropagation();
    this.select.emit(item.redaction_id);
    if (!this.readonly() && !this.drawMode()) this.toggle.emit(item.redaction_id);
  }

  private toPdf(event: PointerEvent, page: PageInfo, surface: HTMLElement): { x: number; y: number } {
    const r = surface.getBoundingClientRect();
    const clamp = (v: number) => Math.min(1, Math.max(0, v));
    return {
      x: clamp((event.clientX - r.left) / r.width) * page.width,
      y: clamp((event.clientY - r.top) / r.height) * page.height,
    };
  }

  protected onPointerDown(event: PointerEvent, page: PageInfo): void {
    if (!this.drawMode() || this.readonly() || event.button !== 0) return;
    const surface = event.currentTarget as HTMLElement;
    surface.setPointerCapture(event.pointerId);
    const { x, y } = this.toPdf(event, page, surface);
    this.draft.set({ page, surface, startX: x, startY: y, box: { x0: x, y0: y, x1: x, y1: y } });
    event.preventDefault();
  }

  protected onPointerMove(event: PointerEvent): void {
    const d = this.draft();
    if (!d) return;
    const { x, y } = this.toPdf(event, d.page, d.surface);
    this.draft.set({
      ...d,
      box: {
        x0: Math.min(d.startX, x),
        y0: Math.min(d.startY, y),
        x1: Math.max(d.startX, x),
        y1: Math.max(d.startY, y),
      },
    });
  }

  protected onPointerUp(): void {
    const d = this.draft();
    this.draft.set(null);
    if (!d) return;
    const { box } = d;
    if (box.x1 - box.x0 >= MIN_SIZE_PT && box.y1 - box.y0 >= MIN_SIZE_PT) {
      this.drawn.emit({ page: d.page.page_number, box });
    }
  }
}
