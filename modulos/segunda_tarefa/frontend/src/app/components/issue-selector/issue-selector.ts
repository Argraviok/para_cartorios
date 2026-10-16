import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, FormGroup, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { catchError, of } from 'rxjs';

import { Vicio, VicioCode } from '../../models/devolution.models';
import { DevolutionService, apiErrorMessage } from '../../services/devolution.service';

const UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE',
  'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'];

const ACT_TYPES = ['Escritura de compra e venda', 'Escritura de doação', 'Instrumento particular com força de escritura pública',
  'Formal de partilha', 'Carta de adjudicação', 'Cédula de crédito'];

type IssueGroup = FormGroup<{
  vicio_code: FormControl<VicioCode>;
  title: FormControl<string>;
  case_facts: FormControl<string>;
}>;

function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

@Component({
  selector: 'app-issue-selector',
  imports: [ReactiveFormsModule],
  templateUrl: './issue-selector.html',
})
export class IssueSelector {
  private fb = inject(FormBuilder).nonNullable;
  private api = inject(DevolutionService);
  private router = inject(Router);

  readonly ufs = UFS;
  readonly actTypes = ACT_TYPES;

  readonly loadError = signal<string | null>(null);
  readonly vicios = toSignal(
    this.api.getVicios().pipe(catchError((e) => (this.loadError.set(apiErrorMessage(e)), of([] as Vicio[])))),
    { initialValue: [] as Vicio[] },
  );
  readonly catalogued = computed(() => this.vicios().filter((v) => v.code !== 'outro'));

  readonly submitting = signal(false);
  readonly submitError = signal<string | null>(null);
  readonly submitted = signal(false);

  readonly form = this.fb.group({
    protocol_number: ['', [Validators.required, Validators.pattern(/\d/)]],
    protocol_date: [localToday(), Validators.required],
    act_type: [ACT_TYPES[0], Validators.required],
    presenter_name: ['', Validators.required],
    uf: ['SP', Validators.required],
    issues: this.fb.array<IssueGroup>([]),
  });

  get issues(): FormArray<IssueGroup> {
    return this.form.controls.issues;
  }

  labelOf(code: VicioCode): string {
    return this.vicios().find((v) => v.code === code)?.label ?? code;
  }

  isSelected(code: VicioCode): boolean {
    return this.issues.controls.some((g) => g.controls.vicio_code.value === code);
  }

  toggle(code: VicioCode): void {
    const idx = this.issues.controls.findIndex((g) => g.controls.vicio_code.value === code);
    if (idx >= 0) this.issues.removeAt(idx);
    else this.issues.push(this.issueGroup(code));
  }

  addOther(): void {
    this.issues.push(this.issueGroup('outro'));
  }

  remove(index: number): void {
    this.issues.removeAt(index);
  }

  private issueGroup(code: VicioCode): IssueGroup {
    return this.fb.group({
      vicio_code: this.fb.control<VicioCode>(code),
      title: this.fb.control('', code === 'outro' ? Validators.required : []),
      case_facts: this.fb.control('', [Validators.required, Validators.minLength(20)]),
    });
  }

  showError(ctrl: FormControl<string>): boolean {
    return ctrl.invalid && (ctrl.touched || this.submitted());
  }

  submit(): void {
    this.submitted.set(true);
    this.submitError.set(null);
    if (this.form.invalid || this.issues.length === 0) return;

    const v = this.form.getRawValue();
    this.submitting.set(true);
    this.api
      .generate({
        ...v,
        issues: v.issues.map((i) => ({
          vicio_code: i.vicio_code,
          title: i.vicio_code === 'outro' ? i.title : null,
          case_facts: i.case_facts.trim(),
        })),
      })
      .subscribe({
        next: (note) => this.router.navigate(['/notas', note.id], { state: { warnings: note.warnings } }),
        error: (e) => {
          this.submitError.set(apiErrorMessage(e));
          this.submitting.set(false);
        },
      });
  }
}
