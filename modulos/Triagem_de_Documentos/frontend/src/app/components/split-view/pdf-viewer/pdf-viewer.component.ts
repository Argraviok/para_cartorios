import { Component, input, model } from '@angular/core';
import { NgxExtendedPdfViewerModule } from 'ngx-extended-pdf-viewer';

@Component({
  selector: 'app-pdf-viewer',
  imports: [NgxExtendedPdfViewerModule],
  template: `
    <ngx-extended-pdf-viewer
      [src]="file()"
      [(page)]="page"
      [height]="'100%'"
      [zoom]="'page-width'"
      [language]="'pt-BR'"
      [textLayer]="true"
      [showSidebarButton]="false"
      [showOpenFileButton]="false"
      [showDownloadButton]="false"
      [showPrintButton]="false"
      [showSecondaryToolbarButton]="false"
      [showDrawEditor]="false"
      [showTextEditor]="false"
      [showStampEditor]="false"
      [showHighlightEditor]="false"
    />
  `,
  host: { class: 'block h-full' },
})
export class PdfViewerComponent {
  readonly file = input.required<File>();
  readonly page = model<number | undefined>(1);
}
