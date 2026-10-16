import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { map, of, switchMap } from 'rxjs';

import { SplitViewComponent } from './components/split-view/split-view.component';
import { UploadComponent, UploadRequest } from './components/upload/upload.component';
import { Qualification } from './models/qualification.model';
import { QualificationService } from './services/qualification.service';

@Component({
  selector: 'app-root',
  imports: [UploadComponent, SplitViewComponent],
  host: { class: 'block h-full' },
  template: `
    @if (result(); as result) {
      <app-split-view [file]="file()!" [result]="result" (restart)="reset()" />
    } @else {
      <app-upload [loading]="loading()" [error]="error()" (submitted)="analyze($event)" />
    }
  `,
})
export class App {
  private readonly service = inject(QualificationService);

  readonly file = signal<File | null>(null);
  readonly result = signal<Qualification | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  analyze({ file, actType }: UploadRequest): void {
    this.loading.set(true);
    this.error.set(null);
    // Word é convertido em PDF antes, para que o visualizador e as páginas citadas coincidam.
    const pdf$ = file.name.toLowerCase().endsWith('.pdf')
      ? of(file)
      : this.service.convertToPdf(file).pipe(
          map((blob) => new File([blob], file.name.replace(/\.docx?$/i, '.pdf'), { type: 'application/pdf' })),
        );
    pdf$
      .pipe(switchMap((pdf) => this.service.analyze(pdf, actType).pipe(map((result) => ({ pdf, result })))))
      .subscribe({
        next: ({ pdf, result }) => {
          this.file.set(pdf);
          this.result.set(result);
          this.loading.set(false);
        },
        error: (err: HttpErrorResponse) => this.fail(err),
      });
  }

  private async fail(err: HttpErrorResponse): Promise<void> {
    // Na conversão a resposta é um Blob, inclusive quando o servidor devolve erro em JSON.
    let body = err.error;
    if (body instanceof Blob) {
      try {
        body = JSON.parse(await body.text());
      } catch {
        body = null;
      }
    }
    this.error.set(
      typeof body?.detail === 'string'
        ? body.detail
        : 'Não foi possível concluir a análise. Verifique se o servidor está em execução.',
    );
    this.loading.set(false);
  }

  reset(): void {
    this.result.set(null);
    this.file.set(null);
  }
}
