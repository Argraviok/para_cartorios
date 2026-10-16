import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { ContinuityTimeline } from './components/continuity-timeline/continuity-timeline';
import { GeometryMetrics } from './components/geometry-metrics/geometry-metrics';
import { ParcelMap } from './components/parcel-map/parcel-map';
import { ParcelUpload } from './components/parcel-upload/parcel-upload';
import { ParcelAnalysis, ParcelSummary } from './models/parcel.model';
import { ParcelService } from './services/parcel.service';

@Component({
  selector: 'app-root',
  imports: [ParcelUpload, ParcelMap, GeometryMetrics, ContinuityTimeline, DatePipe],
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly api = inject(ParcelService);

  readonly analysis = signal<ParcelAnalysis | null>(null);
  readonly recent = signal<ParcelSummary[]>([]);
  readonly error = signal<string | null>(null);
  readonly anchoring = signal(false);

  ngOnInit() {
    const id = new URLSearchParams(location.search).get('id');
    if (id) this.open(id);
    this.loadRecent();
  }

  loadRecent() {
    this.api.list().subscribe({ next: (r) => this.recent.set(r), error: () => this.recent.set([]) });
  }

  open(id: string) {
    this.error.set(null);
    this.api.get(id).subscribe({
      next: (a) => this.show(a),
      error: (e: Error) => this.error.set(e.message),
    });
  }

  show(a: ParcelAnalysis) {
    this.analysis.set(a);
    history.replaceState(null, '', `?id=${a.id}`);
    this.loadRecent();
  }

  anchorParcel(id: string, point: { lat: number; lon: number }) {
    this.anchoring.set(true);
    this.error.set(null);
    this.api.anchor(id, point.lat, point.lon).subscribe({
      next: (a) => {
        this.anchoring.set(false);
        this.analysis.set(a);
      },
      error: (e: Error) => {
        this.anchoring.set(false);
        this.error.set(e.message);
      },
    });
  }

  reset() {
    this.analysis.set(null);
    history.replaceState(null, '', location.pathname);
  }
}
