import { Component, HostListener, input, output, signal } from '@angular/core';
import { ChecklistItem, DOC_STATUS_META } from '../../models/triage.models';
import { isPdf } from '../../format';
import { SafeResourcePipe } from '../../safe-resource.pipe';

export interface ReviewEvent {
  status: 'VALIDADO' | 'REJEITADO' | 'PENDENTE';
  reason: string | null;
}

@Component({
  selector: 'app-doc-lightbox',
  imports: [SafeResourcePipe],
  templateUrl: './doc-lightbox.html',
})
export class DocLightbox {
  item = input.required<ChecklistItem>();
  position = input('');
  busy = input(false);
  canReview = input(true);
  close = output<void>();
  review = output<ReviewEvent>();
  prev = output<void>();
  next = output<void>();

  protected zoom = signal(false);
  protected rejecting = signal(false);
  protected reason = signal('');
  protected readonly meta = DOC_STATUS_META;
  protected readonly isPdf = isPdf;

  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if ((ev.target as HTMLElement)?.tagName === 'TEXTAREA') return;
    if (ev.key === 'Escape') this.close.emit();
    if (ev.key === 'ArrowLeft') this.prev.emit();
    if (ev.key === 'ArrowRight') this.next.emit();
  }

  protected confirmReject(): void {
    const r = this.reason().trim();
    if (!r) return;
    this.review.emit({ status: 'REJEITADO', reason: r });
    this.rejecting.set(false);
    this.reason.set('');
  }

  protected formatDate(d: string | null): string {
    if (!d) return 'Não identificada';
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : d;
  }
}
