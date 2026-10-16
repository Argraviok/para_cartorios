import {
  afterNextRender,
  Component,
  computed,
  effect,
  ElementRef,
  input,
  OnDestroy,
  signal,
  viewChild,
} from '@angular/core';
import OpenSeadragon from 'openseadragon';

/** Visualizador deep zoom do manuscrito com ajustes de leitura (inversão, contraste, brilho). */
@Component({
  selector: 'app-image-viewer',
  templateUrl: './image-viewer.html',
})
export class ImageViewer implements OnDestroy {
  readonly imageUrl = input.required<string>();
  readonly enhancedUrl = input<string | null>(null);

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('osd');
  private viewer?: OpenSeadragon.Viewer;
  private readonly ready = signal(false);

  protected readonly showEnhanced = signal(false);
  protected readonly inverted = signal(false);
  protected readonly contrast = signal(100);
  protected readonly brightness = signal(100);

  protected readonly cssFilter = computed(
    () =>
      `${this.inverted() ? 'invert(1) ' : ''}contrast(${this.contrast()}%) brightness(${this.brightness()}%)`,
  );
  private readonly currentUrl = computed(() =>
    this.showEnhanced() && this.enhancedUrl() ? this.enhancedUrl()! : this.imageUrl(),
  );

  constructor() {
    afterNextRender(() => {
      this.viewer = OpenSeadragon({
        element: this.host().nativeElement,
        showNavigationControl: false,
        showNavigator: true,
        navigatorPosition: 'BOTTOM_RIGHT',
        navigatorSizeRatio: 0.15,
        maxZoomPixelRatio: 6,
        visibilityRatio: 0.6,
        gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
        crossOriginPolicy: false,
      });
      this.ready.set(true);
    });

    effect(() => {
      const url = this.currentUrl();
      if (this.ready() && this.viewer) {
        this.viewer.open({ type: 'image', url } as unknown as OpenSeadragon.TileSourceOptions);
      }
    });
  }

  protected zoom(factor: number): void {
    this.viewer?.viewport.zoomBy(factor);
    this.viewer?.viewport.applyConstraints();
  }

  protected rotate(delta: number): void {
    if (!this.viewer) return;
    this.viewer.viewport.setRotation(this.viewer.viewport.getRotation() + delta);
  }

  protected home(): void {
    this.viewer?.viewport.goHome();
  }

  protected resetAdjustments(): void {
    this.inverted.set(false);
    this.contrast.set(100);
    this.brightness.set(100);
  }

  ngOnDestroy(): void {
    this.viewer?.destroy();
  }
}
