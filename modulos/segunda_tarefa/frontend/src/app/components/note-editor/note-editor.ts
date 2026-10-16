import { CdkDrag, CdkDragDrop, CdkDragPlaceholder, CdkDropList, moveItemInArray } from '@angular/cdk/drag-drop';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, OnInit, computed, inject, input, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, Subject, catchError, debounceTime, finalize, firstValueFrom, switchMap } from 'rxjs';

import { DevolutionNote, Requirement, RequirementEdit } from '../../models/devolution.models';
import { DevolutionService, apiErrorMessage } from '../../services/devolution.service';
import { NotePreview } from '../note-preview/note-preview';
import { RequirementCard } from './requirement-card/requirement-card';

interface Item {
  key: number;
  r: RequirementEdit;
}

type SaveState = 'saved' | 'pending' | 'saving' | 'conflict' | 'error';

const PREVIEW_DEBOUNCE_MS = 400;
const SAVE_DEBOUNCE_MS = 1500;

function toEdit({ order: _order, ...r }: Requirement): RequirementEdit {
  return r;
}

/** Envolve o HTML com estilos inline para colar em editores (Word, sistemas do cartório). */
function clipboardHtml(html: string): string {
  return `<div style="font-family:'Times New Roman',serif;font-size:12pt;line-height:1.5;text-align:justify">${html}</div>`;
}

@Component({
  selector: 'app-note-editor',
  imports: [CdkDropList, CdkDrag, CdkDragPlaceholder, RequirementCard, NotePreview],
  templateUrl: './note-editor.html',
})
export class NoteEditor implements OnInit {
  private api = inject(DevolutionService);
  private destroyRef = inject(DestroyRef);

  /** Parâmetro de rota :id (withComponentInputBinding). */
  readonly id = input.required<string>();

  readonly note = signal<DevolutionNote | null>(null);
  readonly loadError = signal<string | null>(null);
  readonly items = signal<Item[]>([]);
  readonly preview = signal('');
  readonly previewUpdating = signal(false);
  readonly saveState = signal<SaveState>('saved');
  readonly actionError = signal<string | null>(null);
  readonly toast = signal<string | null>(null);
  readonly confirmingIssue = signal(false);
  readonly issuing = signal(false);
  readonly warnings = signal<string[]>((history.state?.warnings as string[] | undefined) ?? []);

  readonly readOnly = computed(() => this.note()?.status !== 'draft');
  readonly incomplete = computed(() =>
    this.items()
      .map((it, i) => ({ n: i + 1, r: it.r }))
      .filter(({ r }) => !r.legal_basis.trim() || !r.suggested_solution.trim())
      .map(({ n }) => n),
  );

  private readonly previewCmp = viewChild(NotePreview);
  private readonly edits$ = new Subject<void>();
  private nextKey = 0;
  private version = 0;
  private editSeq = 0;
  private savedSeq = 0;
  private saveChain: Promise<void> = Promise.resolve();
  private toastTimer?: ReturnType<typeof setTimeout>;

  constructor() {
    this.edits$
      .pipe(
        debounceTime(PREVIEW_DEBOUNCE_MS),
        switchMap(() => {
          this.previewUpdating.set(true);
          return this.api.preview(this.id(), this.requirements()).pipe(
            catchError(() => EMPTY),
            finalize(() => this.previewUpdating.set(false)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((md) => this.preview.set(md));

    this.edits$.pipe(debounceTime(SAVE_DEBOUNCE_MS), takeUntilDestroyed()).subscribe(() => this.enqueueSave());
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loadError.set(null);
    this.api
      .get(this.id())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (note) => this.applyNote(note),
        error: (e) => this.loadError.set(apiErrorMessage(e)),
      });
  }

  private applyNote(note: DevolutionNote): void {
    this.note.set(note);
    this.version = note.version;
    this.items.set(note.requirements.map((r) => ({ key: this.nextKey++, r: toEdit(r) })));
    this.preview.set(note.full_compiled_text);
    this.editSeq = this.savedSeq = 0;
    this.saveState.set('saved');
  }

  private requirements(): RequirementEdit[] {
    return this.items().map((it) => it.r);
  }

  // ---------- edição ----------
  private touched(): void {
    this.editSeq++;
    if (this.saveState() !== 'conflict') this.saveState.set('pending');
    this.edits$.next();
  }

  update(key: number, r: RequirementEdit): void {
    this.items.update((items) => items.map((it) => (it.key === key ? { ...it, r } : it)));
    this.touched();
  }

  removeItem(key: number): void {
    const item = this.items().find((it) => it.key === key);
    if (!item || !confirm(`Excluir a exigência "${item.r.legal_topic || 'sem título'}"?`)) return;
    this.items.update((items) => items.filter((it) => it.key !== key));
    this.touched();
  }

  addManual(): void {
    this.items.update((items) => [
      ...items,
      {
        key: this.nextKey++,
        r: {
          vicio_code: 'outro',
          legal_topic: 'Nova exigência',
          precedent_ids: [],
          legal_basis: '',
          justification_draft: '',
          user_edited_text: null,
          suggested_solution: '',
          source: 'manual',
          grounded: false,
        },
      },
    ]);
    this.touched();
  }

  drop(event: CdkDragDrop<Item[]>): void {
    if (event.previousIndex === event.currentIndex) return;
    this.items.update((items) => {
      const copy = [...items];
      moveItemInArray(copy, event.previousIndex, event.currentIndex);
      return copy;
    });
    this.touched();
  }

  // ---------- salvamento (serializado: nunca dois PATCH com a mesma versão) ----------
  enqueueSave(): Promise<void> {
    this.saveChain = this.saveChain.then(() => this.doSave());
    return this.saveChain;
  }

  private async doSave(): Promise<void> {
    if (this.editSeq === this.savedSeq || this.saveState() === 'conflict' || this.readOnly()) return;
    const seq = this.editSeq;
    this.saveState.set('saving');
    try {
      const note = await firstValueFrom(this.api.update(this.id(), this.version, this.requirements()));
      this.version = note.version;
      this.note.set(note);
      this.savedSeq = seq;
      this.saveState.set(this.editSeq === seq ? 'saved' : 'pending');
    } catch (e) {
      if (e instanceof HttpErrorResponse && e.status === 409) {
        this.saveState.set('conflict');
        this.actionError.set(apiErrorMessage(e));
      } else {
        this.saveState.set('error');
      }
    }
  }

  private async ensureSaved(): Promise<boolean> {
    await this.enqueueSave();
    if (this.saveState() !== 'saved') {
      this.actionError.set('Há alterações não salvas. Resolva o salvamento antes de continuar.');
      return false;
    }
    return true;
  }

  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent): void {
    if (this.saveState() !== 'saved') event.preventDefault();
  }

  // ---------- ações ----------
  async copy(formatted: boolean): Promise<void> {
    const snap = this.previewCmp()?.snapshot();
    if (!snap) return;
    try {
      if (formatted && typeof ClipboardItem !== 'undefined') {
        await navigator.clipboard.write([
          new ClipboardItem({
            'text/html': new Blob([clipboardHtml(snap.html)], { type: 'text/html' }),
            'text/plain': new Blob([snap.text], { type: 'text/plain' }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(snap.text);
      }
      this.showToast(formatted ? 'Texto formatado copiado.' : 'Texto sem formatação copiado.');
    } catch {
      this.actionError.set('O navegador bloqueou o acesso à área de transferência.');
    }
  }

  async download(format: 'md' | 'txt'): Promise<void> {
    this.actionError.set(null);
    if (!(await this.ensureSaved())) return;
    const a = document.createElement('a');
    a.href = this.api.exportUrl(this.id(), format);
    a.download = '';
    a.click();
  }

  async issue(): Promise<void> {
    this.actionError.set(null);
    this.issuing.set(true);
    try {
      if (!(await this.ensureSaved())) return;
      const note = await firstValueFrom(this.api.issue(this.id()));
      this.applyNote(note);
      this.warnings.set([]);
      this.confirmingIssue.set(false);
      this.showToast(`Nota nº ${note.note_number} emitida.`);
    } catch (e) {
      this.actionError.set(apiErrorMessage(e));
      this.confirmingIssue.set(false);
    } finally {
      this.issuing.set(false);
    }
  }

  dismissWarnings(): void {
    this.warnings.set([]);
  }

  private showToast(message: string): void {
    this.toast.set(message);
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toast.set(null), 2500);
  }

  formatProtocol(n: string): string {
    return /^\d+$/.test(n) ? Number(n).toLocaleString('pt-BR') : n;
  }
}
