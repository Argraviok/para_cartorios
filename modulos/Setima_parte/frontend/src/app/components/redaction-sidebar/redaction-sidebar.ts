import { Component, computed, input, output } from '@angular/core';

import { CATEGORIES, CATEGORY_META, Category, RedactionItem } from '../../models/redaction.models';

const SOURCE_LABEL = { regex: 'regra', llm: 'IA', manual: 'manual' } as const;

@Component({
  selector: 'app-redaction-sidebar',
  templateUrl: './redaction-sidebar.html',
  styleUrl: './redaction-sidebar.css',
})
export class RedactionSidebar {
  readonly items = input.required<RedactionItem[]>();
  readonly selectedId = input<string | null>(null);
  readonly readonly = input(false);

  readonly toggle = output<string>();
  readonly select = output<string>();
  readonly setCategoryApproval = output<{ category: Category; approved: boolean }>();
  readonly changeCategory = output<{ id: string; category: Category }>();
  readonly remove = output<string>();

  protected readonly meta = CATEGORY_META;
  protected readonly categories = CATEGORIES;
  protected readonly sourceLabel = SOURCE_LABEL;

  protected readonly groups = computed(() =>
    CATEGORIES.map((category) => {
      const items = this.items().filter((i) => i.category === category);
      return { category, items, approved: items.filter((i) => i.approved).length };
    }).filter((g) => g.items.length),
  );

  protected onCategoryChange(id: string, event: Event): void {
    this.changeCategory.emit({ id, category: (event.target as HTMLSelectElement).value as Category });
  }
}
