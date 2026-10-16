import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { AuditSummary } from './components/audit-summary/audit-summary';
import { RedactionSidebar } from './components/redaction-sidebar/redaction-sidebar';
import { RedactionViewer } from './components/redaction-viewer/redaction-viewer';
import { UploadDropzone } from './components/upload-dropzone/upload-dropzone';
import {
  BoundingBox,
  Category,
  JobSummary,
  RedactionItem,
  RedactionJob,
  STATUS_LABEL,
} from './models/redaction.models';
import {
  RedactionService,
  errorMessage,
  filenameFromDisposition,
  saveBlob,
} from './services/redaction.service';

const OPERATOR_KEY = 'lgpd-redaction.operator';

function readOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? '';
  } catch {
    return '';
  }
}

@Component({
  selector: 'app-root',
  imports: [DatePipe, FormsModule, UploadDropzone, RedactionViewer, RedactionSidebar, AuditSummary],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  private readonly api = inject(RedactionService);

  protected readonly statusLabel = STATUS_LABEL;
  protected readonly operator = signal(readOperator());
  protected readonly jobs = signal<JobSummary[]>([]);
  protected readonly job = signal<RedactionJob | null>(null);
  protected readonly items = signal<RedactionItem[]>([]);
  protected readonly selectedId = signal<string | null>(null);
  protected readonly drawMode = signal(false);
  protected readonly dirty = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);

  protected readonly readonly = computed(() => this.job()?.status === 'sanitized');

  ngOnInit(): void {
    this.refreshJobs();
  }

  protected setOperator(value: string): void {
    this.operator.set(value);
    try {
      localStorage.setItem(OPERATOR_KEY, value);
    } catch {
      /* armazenamento indisponível: apenas não lembra o nome */
    }
  }

  protected async refreshJobs(): Promise<void> {
    try {
      this.jobs.set(await firstValueFrom(this.api.listJobs()));
    } catch (err) {
      this.error.set(await errorMessage(err));
    }
  }

  protected onJobCreated(job: RedactionJob): void {
    this.jobs.update((list) => [job, ...list.filter((j) => j.job_id !== job.job_id)]);
    if (!this.job()) this.load(job);
  }

  protected async open(summary: JobSummary): Promise<void> {
    if (this.dirty() && !confirm('Há alterações não salvas na revisão atual. Descartar?')) return;
    try {
      this.load(await firstValueFrom(this.api.getJob(summary.job_id)));
    } catch (err) {
      this.error.set(await errorMessage(err));
    }
  }

  private load(job: RedactionJob): void {
    this.job.set(job);
    this.items.set(job.items);
    this.selectedId.set(null);
    this.drawMode.set(false);
    this.dirty.set(false);
    this.error.set(null);
    this.notice.set(null);
  }

  private patchItems(fn: (items: RedactionItem[]) => RedactionItem[]): void {
    this.items.update(fn);
    this.dirty.set(true);
  }

  protected toggle(id: string): void {
    this.patchItems((items) => items.map((i) => (i.redaction_id === id ? { ...i, approved: !i.approved } : i)));
  }

  protected setCategoryApproval(e: { category: Category; approved: boolean }): void {
    this.patchItems((items) => items.map((i) => (i.category === e.category ? { ...i, approved: e.approved } : i)));
  }

  protected changeCategory(e: { id: string; category: Category }): void {
    this.patchItems((items) => items.map((i) => (i.redaction_id === e.id ? { ...i, category: e.category } : i)));
  }

  protected remove(id: string): void {
    this.patchItems((items) => items.filter((i) => i.redaction_id !== id));
  }

  protected addManual(e: { page: number; box: BoundingBox }): void {
    const id = `man_${crypto.randomUUID().slice(0, 10)}`;
    const item: RedactionItem = {
      redaction_id: id,
      category: 'DOCUMENTO_PESSOAL',
      pii_type: 'MANUAL',
      detected_text: '',
      page_number: e.page,
      bboxes: [e.box],
      approved: true,
      legal_basis: '',
      source: 'manual',
    };
    this.patchItems((items) => [...items, item]);
    this.selectedId.set(id);
  }

  private requireOperator(): string | null {
    const op = this.operator().trim();
    if (!op) this.error.set('Informe o nome do operador antes de salvar ou homologar.');
    return op || null;
  }

  protected async save(): Promise<void> {
    const job = this.job();
    const op = this.requireOperator();
    if (!job || !op) return;
    this.busy.set(true);
    try {
      const updated = await firstValueFrom(this.api.saveReview(job.job_id, this.items(), op));
      this.job.set(updated);
      this.items.set(updated.items); // o servidor preenche o texto sob as tarjas manuais
      this.dirty.set(false);
      this.notice.set('Revisão salva.');
      this.error.set(null);
    } catch (err) {
      this.error.set(await errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }

  protected async finalize(): Promise<void> {
    const job = this.job();
    const op = this.requireOperator();
    if (!job || !op) return;
    this.busy.set(true);
    try {
      const resp = await firstValueFrom(this.api.apply(job.job_id, this.items(), op));
      saveBlob(resp.body!, filenameFromDisposition(resp.headers.get('Content-Disposition'), 'documento_tarjado.pdf'));
      const updated = await firstValueFrom(this.api.getJob(job.job_id));
      this.load(updated);
      this.notice.set('Documento sanitizado e verificado: nenhum texto selecionável sob as tarjas.');
      this.refreshJobs();
    } catch (err) {
      this.error.set(await errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }
}
