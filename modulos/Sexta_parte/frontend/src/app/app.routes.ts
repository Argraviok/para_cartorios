import { Routes } from '@angular/router';
import { FraudDashboard } from './components/fraud-dashboard/fraud-dashboard';

export const routes: Routes = [
  { path: '', component: FraudDashboard, title: 'Cockpit Antifraude' },
  { path: 'audits/new', loadComponent: () => import('./components/new-audit/new-audit').then((m) => m.NewAudit), title: 'Nova auditoria' },
  { path: 'audits/:id', loadComponent: () => import('./components/forensic-inspector/forensic-inspector').then((m) => m.ForensicInspector), title: 'Inspeção forense' },
  { path: 'signature-cards', loadComponent: () => import('./components/signature-cards/signature-cards').then((m) => m.SignatureCards), title: 'Cartões de firma' },
  { path: '**', redirectTo: '' },
];
