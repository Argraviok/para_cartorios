import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Busca histórica · Arquivo Digital',
    loadComponent: () =>
      import('./components/search-dashboard/search-dashboard').then((m) => m.SearchDashboard),
  },
  {
    path: 'upload',
    title: 'Digitalização em lote · Arquivo Digital',
    loadComponent: () => import('./components/batch-upload/batch-upload').then((m) => m.BatchUpload),
  },
  {
    path: 'records/:id',
    title: 'Revisão paleográfica · Arquivo Digital',
    loadComponent: () =>
      import('./components/transcription-review/transcription-review').then((m) => m.TranscriptionReview),
  },
  { path: '**', redirectTo: '' },
];
