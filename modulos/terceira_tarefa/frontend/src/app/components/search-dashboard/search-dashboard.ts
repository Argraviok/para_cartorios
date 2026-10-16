import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, debounceTime, EMPTY, Subject, switchMap, tap } from 'rxjs';

import {
  BOOK_TYPE_LABELS,
  BOOK_TYPES,
  BookType,
  RecordStatus,
  SearchHit,
  SearchParams,
} from '../../models/historical-record';
import { apiErrorMessage, HistoricalService } from '../../services/historical.service';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-search-dashboard',
  imports: [RouterLink, DatePipe, DecimalPipe],
  templateUrl: './search-dashboard.html',
})
export class SearchDashboard implements OnInit {
  private readonly api = inject(HistoricalService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly searches = new Subject<{ params: SearchParams; append: boolean }>();

  protected readonly bookTypes = BOOK_TYPES;
  protected readonly bookTypeLabels = BOOK_TYPE_LABELS;

  protected readonly query = signal('');
  protected readonly bookType = signal<BookType | ''>('');
  protected readonly status = signal<RecordStatus | ''>('');
  protected readonly yearFrom = signal<number | null>(null);
  protected readonly yearTo = signal<number | null>(null);

  protected readonly results = signal<SearchHit[]>([]);
  protected readonly total = signal(0);
  protected readonly engine = signal<'atlas_search' | 'fallback' | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.searches
      .pipe(
        debounceTime(250),
        tap(() => {
          this.loading.set(true);
          this.error.set(null);
        }),
        switchMap(({ params, append }) =>
          this.api.search(params).pipe(
            tap((res) => {
              this.results.set(append ? [...this.results(), ...res.results] : res.results);
              this.total.set(res.total);
              this.engine.set(res.engine);
              this.loading.set(false);
            }),
            catchError((err) => {
              this.error.set(apiErrorMessage(err));
              this.loading.set(false);
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
    this.runSearch();
  }

  protected runSearch(append = false): void {
    this.searches.next({
      append,
      params: {
        q: this.query(),
        book_type: this.bookType(),
        status: this.status(),
        year_from: this.yearFrom(),
        year_to: this.yearTo(),
        limit: PAGE_SIZE,
        skip: append ? this.results().length : 0,
      },
    });
  }

  protected setQuery(value: string): void {
    this.query.set(value);
    this.runSearch();
  }

  protected setYear(which: 'from' | 'to', value: string): void {
    const year = /^\d{4}$/.test(value) ? Number(value) : null;
    (which === 'from' ? this.yearFrom : this.yearTo).set(year);
    if (value === '' || year !== null) this.runSearch();
  }

  protected clearFilters(): void {
    this.query.set('');
    this.bookType.set('');
    this.status.set('');
    this.yearFrom.set(null);
    this.yearTo.set(null);
    this.runSearch();
  }

  protected confidenceClass(score: number): string {
    if (score >= 0.85) return 'bg-verified';
    if (score >= 0.65) return 'bg-warn';
    return 'bg-danger';
  }
}
