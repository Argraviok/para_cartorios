import { Component, ElementRef, computed, input, viewChild } from '@angular/core';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

export function markdownToSafeHtml(md: string): string {
  const html = marked.parse(md, { breaks: true, gfm: true, async: false });
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
}

@Component({
  selector: 'app-note-preview',
  template: `
    <div class="relative rounded-lg border border-line bg-surface shadow-sm">
      @if (updating()) {
        <span class="absolute top-3 right-3 text-xs text-muted">atualizando…</span>
      }
      <article #doc class="nota-doc px-6 py-8 sm:px-10" [innerHTML]="html()"></article>
    </div>
  `,
})
export class NotePreview {
  readonly markdown = input.required<string>();
  readonly updating = input(false);

  readonly html = computed(() => markdownToSafeHtml(this.markdown()));
  private readonly doc = viewChild.required<ElementRef<HTMLElement>>('doc');

  /** HTML sanitizado e texto puro exatamente como exibidos, para a área de transferência. */
  snapshot(): { html: string; text: string } {
    const el = this.doc().nativeElement;
    return { html: el.innerHTML, text: el.innerText.replace(/\n{3,}/g, '\n\n').trim() + '\n' };
  }
}
