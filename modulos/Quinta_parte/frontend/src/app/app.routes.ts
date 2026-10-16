import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'painel' },
  {
    path: 'painel',
    loadComponent: () => import('./pages/attendant-panel/attendant-panel').then((m) => m.AttendantPanel),
  },
  {
    path: 'painel/:protocolId',
    loadComponent: () => import('./pages/attendant-panel/attendant-panel').then((m) => m.AttendantPanel),
  },
  {
    path: 'atendimento',
    loadComponent: () => import('./pages/citizen-widget/citizen-widget').then((m) => m.CitizenWidget),
  },
  { path: '**', redirectTo: 'painel' },
];
