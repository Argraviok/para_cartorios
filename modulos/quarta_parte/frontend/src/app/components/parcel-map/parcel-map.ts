import { Component, computed, input, output, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { LeafletModule } from '@bluehalo/ngx-leaflet';
import * as L from 'leaflet';

import { ApproximateLocation, GeometryAnalysis, Segment } from '../../models/parcel.model';

const PERFECT_CLOSURE_M = 0.02;

/** Raio de incerteza exibido para cada precisão da geocodificação (m). */
const PRECISION_RADIUS_M: Record<ApproximateLocation['precision'], number> = {
  ENDERECO: 60,
  RUA: 350,
  BAIRRO: 1200,
  CIDADE: 6000,
};
const PRECISION_LABEL: Record<ApproximateLocation['precision'], string> = {
  ENDERECO: 'endereço',
  RUA: 'rua',
  BAIRRO: 'bairro/loteamento',
  CIDADE: 'cidade',
};
const BRAZIL = L.latLngBounds([-33.8, -74], [5.3, -34.8]);

type Mode = 'geo' | 'anchor' | 'pin' | 'none';

@Component({
  selector: 'app-parcel-map',
  imports: [LeafletModule, DecimalPipe],
  templateUrl: './parcel-map.html',
})
export class ParcelMap {
  readonly geometry = input<GeometryAnalysis | null>(null);
  readonly location = input<ApproximateLocation | null>(null);
  readonly busy = input(false);
  /** Primeiro vértice escolhido no mapa (ponto de amarração). */
  readonly anchor = output<{ lat: number; lon: number }>();

  readonly selected = signal<Segment | null>(null);
  readonly repositioning = signal(false);

  private readonly satellite = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 21, maxNativeZoom: 19, attribution: 'Imagens &copy; Esri, Maxar, Earthstar Geographics' },
  );
  private readonly streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 21,
    maxNativeZoom: 19,
    attribution: '&copy; colaboradores do OpenStreetMap',
  });

  readonly options: L.MapOptions = { layers: [this.satellite], zoom: 18, center: L.latLng(-22.9, -47.06) };
  readonly layersControl = { baseLayers: { Satélite: this.satellite, Ruas: this.streets }, overlays: {} };

  readonly mode = computed<Mode>(() => {
    const g = this.geometry();
    if (g && (this.repositioning() || g.georeference_method === 'NONE')) return 'anchor';
    if (g?.is_georeferenced) return 'geo';
    if (this.location()) return 'pin';
    return 'none';
  });

  readonly firstVertex = computed(() => this.geometry()?.segments[0]?.from_point ?? 'inicial');
  readonly canReposition = computed(() => this.geometry()?.georeference_method === 'MANUAL_ANCHOR');
  readonly precisionLabel = computed(() => {
    const loc = this.location();
    return loc ? PRECISION_LABEL[loc.precision] : '';
  });

  readonly closure = computed(() => {
    const g = this.geometry();
    if (!g) return null;
    if (g.closure_method === 'COORDINATES') {
      return { tone: 'ok', text: 'Perímetro fechado por coordenadas' };
    }
    if (!g.is_closed) {
      return { tone: 'bad', text: `Perímetro não fecha (erro de ${fmt(g.gap_meters)} m)` };
    }
    if (g.gap_meters < PERFECT_CLOSURE_M) {
      return { tone: 'ok', text: `Fechamento topográfico perfeito (erro de ${fmt(g.gap_meters * 100, 1)} cm < 2 cm)` };
    }
    return { tone: 'warn', text: `Fechamento dentro da tolerância (erro de ${fmt(g.gap_meters)} m)` };
  });

  /** Anel em [lat, lng] a partir das arestas (funciona mesmo para polígono inválido). */
  private readonly ring = computed(() => {
    const g = this.geometry();
    if (!g?.is_georeferenced) return [];
    return g.segments.filter((s) => s.coordinates).map((s) => L.latLng(s.coordinates![0][1], s.coordinates![0][0]));
  });

  readonly bounds = computed(() => {
    const ring = this.ring();
    if (ring.length) return L.latLngBounds(ring).pad(0.35);
    const loc = this.location();
    if (loc) return L.latLng(loc.lat, loc.lon).toBounds(PRECISION_RADIUS_M[loc.precision] * 2.5);
    return BRAZIL;
  });

  readonly layers = computed<L.Layer[]>(() => {
    const mode = this.mode();
    const layers: L.Layer[] = [...this.locationLayers()];
    if (mode === 'geo') layers.push(...this.parcelLayers(true));
    if (mode === 'anchor' && this.ring().length) layers.push(...this.parcelLayers(false));
    return layers;
  });

  onMapClick(event: L.LeafletMouseEvent) {
    if (this.mode() !== 'anchor' || this.busy()) return;
    this.repositioning.set(false);
    this.anchor.emit({ lat: event.latlng.lat, lon: event.latlng.lng });
  }

  private locationLayers(): L.Layer[] {
    const loc = this.location();
    if (!loc) return [];
    const center = L.latLng(loc.lat, loc.lon);
    const label = `Localização aproximada (${PRECISION_LABEL[loc.precision]}): ${loc.display_name ?? loc.query}`;
    return [
      L.circle(center, {
        radius: PRECISION_RADIUS_M[loc.precision],
        color: '#38bdf8',
        weight: 1.5,
        dashArray: '5 5',
        fillOpacity: 0.08,
        interactive: false,
      }),
      L.circleMarker(center, { radius: 7, color: '#fff', weight: 2, fillColor: '#0284c7', fillOpacity: 1 }).bindTooltip(
        label,
        { className: 'edge-tooltip' },
      ),
    ];
  }

  private parcelLayers(interactive: boolean): L.Layer[] {
    const g = this.geometry()!;
    const ok = g.is_valid_polygon && g.is_closed;
    const layers: L.Layer[] = [
      L.polygon(this.ring(), {
        color: ok ? '#facc15' : '#ef4444',
        weight: 1,
        fillColor: ok ? '#facc15' : '#ef4444',
        fillOpacity: interactive ? 0.18 : 0.08,
        dashArray: ok && interactive ? undefined : '6 4',
        interactive: false,
      }),
    ];
    if (!interactive) return layers;

    if (g.closure_gap_line) {
      const [start, end] = g.closure_gap_line.map(([lon, lat]) => L.latLng(lat, lon));
      layers.push(
        L.polyline([start, end], { color: '#ef4444', weight: 3, dashArray: '4 4' }).bindTooltip(
          `Erro de fechamento: ${fmt(g.gap_meters)} m`,
          { sticky: true, className: 'edge-tooltip' },
        ),
        L.circleMarker(end, { radius: 6, color: '#fff', weight: 2, fillColor: '#ef4444', fillOpacity: 1 }).bindTooltip(
          'Fim da poligonal (azimutes e distâncias)',
          { className: 'edge-tooltip' },
        ),
      );
    }

    for (const seg of g.segments) {
      if (!seg.coordinates) continue;
      const line = L.polyline(
        seg.coordinates.map(([lon, lat]) => L.latLng(lat, lon)),
        { color: '#facc15', weight: 4, opacity: 0.95 },
      );
      const label = seg.confrontant ? `Confronta com ${seg.confrontant}` : 'Confrontante não informado';
      line.bindTooltip(`${seg.from_point} → ${seg.to_point}: ${label}`, { sticky: true, className: 'edge-tooltip' });
      line.bindPopup(this.popupHtml(seg));
      line.on('mouseover', () => line.setStyle({ color: '#38bdf8', weight: 7 }));
      line.on('mouseout', () => line.setStyle({ color: '#facc15', weight: 4 }));
      line.on('click', () => this.selected.set(seg));
      layers.push(line);

      const [lon, lat] = seg.coordinates[0];
      layers.push(
        L.circleMarker(L.latLng(lat, lon), { radius: 5, color: '#0f172a', weight: 2, fillColor: '#fff', fillOpacity: 1 })
          .bindTooltip(seg.from_point, { permanent: true, direction: 'top', offset: [0, -6], className: 'vertex-label' }),
      );
    }
    return layers;
  }

  // --- Croqui SVG (miniatura usada no modo de posicionamento) -------------
  readonly sketch = computed(() => {
    const g = this.geometry();
    const segs = g?.segments.filter((s) => s.coordinates) ?? [];
    if (!segs.length) return null;
    // Em lon/lat (já posicionado) corrige a escala da longitude pela latitude
    const kx = g!.is_georeferenced ? Math.cos((segs[0].coordinates![0][1] * Math.PI) / 180) : 1;
    const pts = segs.flatMap((s) => s.coordinates!);
    const xs = pts.map((p) => p[0] * kx);
    const ys = pts.map((p) => p[1]);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const span = Math.max(maxX - minX, maxY - minY) || 1;
    const pad = span * 0.22;
    const tx = (x: number) => x * kx - minX + pad;
    const ty = (y: number) => maxY - y + pad;
    return {
      viewBox: `0 0 ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`,
      stroke: span / 60,
      font: span / 9,
      edges: segs.map((s) => ({
        seg: s,
        x1: tx(s.coordinates![0][0]),
        y1: ty(s.coordinates![0][1]),
      })),
      polygon: segs.map((s) => `${tx(s.coordinates![0][0])},${ty(s.coordinates![0][1])}`).join(' '),
    };
  });

  private popupHtml(seg: Segment): string {
    const esc = (s: string) => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
    const rows = [
      ['Lado', `${seg.from_point} → ${seg.to_point}`],
      ['Confrontante', seg.confrontant ?? '—'],
      ['Azimute', seg.azimuth ?? '—'],
      ['Distância declarada', seg.declared_distance_m != null ? `${fmt(seg.declared_distance_m, 2)} m` : '—'],
      ['Distância calculada', `${fmt(seg.computed_distance_m, 3)} m`],
    ];
    return `<table style="font-size:12px">${rows
      .map(([k, v]) => `<tr><td style="color:#64748b;padding-right:8px">${k}</td><td><b>${esc(v)}</b></td></tr>`)
      .join('')}</table>`;
  }
}

function fmt(n: number, digits = 3): string {
  return n.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
