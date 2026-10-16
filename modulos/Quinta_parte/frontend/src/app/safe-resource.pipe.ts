import { Pipe, PipeTransform, inject } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

/** Só para URLs do próprio backend (/media/...), usadas no iframe de PDF. */
@Pipe({ name: 'safeResource' })
export class SafeResourcePipe implements PipeTransform {
  private sanitizer = inject(DomSanitizer);

  transform(url: string): SafeResourceUrl {
    if (!url.startsWith('/media/')) throw new Error('URL de documento não permitida');
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  }
}
