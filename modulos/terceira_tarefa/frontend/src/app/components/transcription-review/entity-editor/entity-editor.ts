import { DecimalPipe } from '@angular/common';
import { Component, computed, input, linkedSignal, output, signal } from '@angular/core';

import { HistoricalRecord, Party, RecordUpdate, RELATIVES_LABEL } from '../../../models/historical-record';

const ILLEGIBLE = /\[ileg[íi]vel\]/gi;

/** Formulário de correção humana da transcrição e das entidades extraídas pela IA. */
@Component({
  selector: 'app-entity-editor',
  imports: [DecimalPipe],
  templateUrl: './entity-editor.html',
  host: { '(keydown)': 'onKeydown($event)' },
})
export class EntityEditor {
  readonly record = input.required<HistoricalRecord>();
  readonly saving = input(false);
  readonly save = output<RecordUpdate>();

  protected readonly entryNumber = linkedSignal(() => this.record().entry_number ?? '');
  protected readonly entryDateText = linkedSignal(() => this.record().entry_date_text ?? '');
  protected readonly entryDateIso = linkedSignal(() => this.record().entry_date_iso ?? '');
  protected readonly transcription = linkedSignal(() => this.record().transcription_raw);
  protected readonly parties = linkedSignal<Party[]>(() => this.record().parties.map((p) => ({ ...p })));
  protected readonly relatives = linkedSignal(() => [...this.record().confrontants_or_relatives]);
  /** Índice da parte em edição inline (null = nenhuma). */
  protected readonly editingParty = linkedSignal<number | null>(() => (this.record(), null));
  protected readonly newRelative = signal('');

  protected readonly relativesLabel = computed(() => RELATIVES_LABEL[this.record().book_type]);
  protected readonly illegibleCount = computed(() => this.transcription().match(ILLEGIBLE)?.length ?? 0);
  protected readonly dateInvalid = computed(
    () => this.entryDateIso() !== '' && !/^\d{4}-\d{2}-\d{2}$/.test(this.entryDateIso()),
  );
  protected readonly confidencePct = computed(() => this.record().confidence_score * 100);
  protected readonly confidenceTone = computed(() => {
    const s = this.record().confidence_score;
    return s >= 0.85 ? 'text-verified' : s >= 0.65 ? 'text-warn' : 'text-danger';
  });
  protected readonly dirty = computed(() => {
    const r = this.record();
    return (
      this.entryNumber() !== (r.entry_number ?? '') ||
      this.entryDateText() !== (r.entry_date_text ?? '') ||
      this.entryDateIso() !== (r.entry_date_iso ?? '') ||
      this.transcription() !== r.transcription_raw ||
      JSON.stringify(this.parties().map(stripPhonetic)) !== JSON.stringify(r.parties.map(stripPhonetic)) ||
      JSON.stringify(this.relatives()) !== JSON.stringify(r.confrontants_or_relatives)
    );
  });

  protected updateParty(index: number, field: keyof Omit<Party, 'phonetic'>, value: string): void {
    this.parties.update((list) =>
      list.map((p, i) =>
        i === index ? { ...p, [field]: field === 'name_standardized' ? value.toUpperCase() : value } : p,
      ),
    );
  }

  protected addParty(): void {
    this.parties.update((list) => [...list, { role: '', name_standardized: '', name_original: '' }]);
    this.editingParty.set(this.parties().length - 1);
  }

  protected removeParty(index: number): void {
    this.parties.update((list) => list.filter((_, i) => i !== index));
    this.editingParty.set(null);
  }

  protected addRelative(): void {
    const value = this.newRelative().trim();
    if (!value) return;
    this.relatives.update((list) => [...list, value]);
    this.newRelative.set('');
  }

  protected removeRelative(index: number): void {
    this.relatives.update((list) => list.filter((_, i) => i !== index));
  }

  protected submit(verify: boolean): void {
    if (this.dateInvalid()) return;
    const changes: RecordUpdate = {
      entry_number: this.entryNumber().trim() || null,
      entry_date_text: this.entryDateText().trim() || null,
      entry_date_iso: this.entryDateIso() || null,
      transcription_raw: this.transcription(),
      parties: this.parties()
        .filter((p) => p.name_standardized.trim() || p.name_original.trim())
        .map(stripPhonetic),
      confrontants_or_relatives: this.relatives(),
    };
    if (verify) changes.status = 'verified';
    this.save.emit(changes);
  }

  protected reopen(): void {
    this.save.emit({ status: 'analyzed' });
  }

  protected onKeydown(event: KeyboardEvent): void {
    // Ctrl/Cmd+Enter homologa; Ctrl/Cmd+S salva sem homologar.
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      if (!this.saving()) this.submit(true);
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      if (!this.saving() && this.dirty()) this.submit(false);
    }
  }
}

function stripPhonetic({ role, name_standardized, name_original }: Party): Omit<Party, 'phonetic'> {
  return { role: role.trim(), name_standardized: name_standardized.trim(), name_original: name_original.trim() };
}
