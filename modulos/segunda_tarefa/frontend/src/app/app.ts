import { Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="border-b border-line bg-surface">
      <div class="mx-auto flex max-w-[1400px] items-center justify-between px-4 py-3">
        <a routerLink="/" class="flex items-center gap-2 font-semibold text-ink">
          <span class="grid size-8 place-items-center rounded-md bg-accent text-sm text-white">ND</span>
          Notas Devolutivas
        </a>
        <a routerLink="/" class="rounded-md px-3 py-1.5 text-sm text-muted hover:bg-subtle hover:text-ink">+ Nova nota</a>
      </div>
    </header>
    <main class="mx-auto max-w-[1400px] px-4 py-6">
      <router-outlet />
    </main>
  `,
})
export class App {}
