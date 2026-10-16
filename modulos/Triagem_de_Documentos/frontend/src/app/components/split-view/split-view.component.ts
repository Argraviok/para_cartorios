import { Component, input, output, signal } from '@angular/core';

import { Qualification } from '../../models/qualification.model';
import { DevolutionModalComponent } from '../devolution-modal/devolution-modal.component';
import { ChecklistPanelComponent } from './checklist-panel/checklist-panel.component';
import { PdfViewerComponent } from './pdf-viewer/pdf-viewer.component';

@Component({
  selector: 'app-split-view',
  imports: [PdfViewerComponent, ChecklistPanelComponent, DevolutionModalComponent],
  template: `
    <section class="h-full w-3/5 border-r border-slate-300">
      <app-pdf-viewer [file]="file()" [(page)]="page" />
    </section>
    <aside class="h-full w-2/5">
      <app-checklist-panel
        [result]="result()"
        (pageSelected)="page.set($event)"
        (devolutionRequested)="modalOpen.set(true)"
        (restart)="restart.emit()"
      />
    </aside>
    @if (modalOpen()) {
      <app-devolution-modal [result]="result()" (closed)="modalOpen.set(false)" />
    }
  `,
  host: { class: 'flex h-full' },
})
export class SplitViewComponent {
  readonly file = input.required<File>();
  readonly result = input.required<Qualification>();
  readonly restart = output<void>();

  readonly page = signal<number | undefined>(1);
  readonly modalOpen = signal(false);
}
