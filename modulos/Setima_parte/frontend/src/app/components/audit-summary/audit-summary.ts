import { DatePipe } from '@angular/common';
import { Component, ElementRef, computed, inject, input, output, viewChild } from '@angular/core';

import { RedactionItem, RedactionJob, STATUS_LABEL } from '../../models/redaction.models';
import { RedactionService } from '../../services/redaction.service';

@Component({
  selector: 'app-audit-summary',
  imports: [DatePipe],
  templateUrl: './audit-summary.html',
  styleUrl: './audit-summary.css',
})
export class AuditSummary {
  private readonly api = inject(RedactionService);

  readonly job = input.required<RedactionJob>();
  readonly items = input.required<RedactionItem[]>();
  readonly dirty = input(false);
  readonly busy = input(false);

  readonly save = output<void>();
  readonly finalize = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('confirmDialog');

  protected readonly statusLabel = STATUS_LABEL;
  protected readonly approved = computed(() => this.items().filter((i) => i.approved).length);
  protected readonly manual = computed(() => this.items().filter((i) => i.source === 'manual').length);
  protected readonly sanitized = computed(() => this.job().status === 'sanitized');

  protected sanitizedUrl(): string {
    return this.api.sanitizedUrl(this.job().job_id);
  }

  protected auditUrl(format: 'csv' | 'pdf'): string {
    return this.api.auditUrl(this.job().job_id, format);
  }

  protected openConfirm(): void {
    this.dialog().nativeElement.showModal();
  }

  protected confirm(): void {
    this.dialog().nativeElement.close();
    this.finalize.emit();
  }
}
