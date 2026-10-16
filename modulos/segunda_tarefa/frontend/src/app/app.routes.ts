import { Routes } from '@angular/router';

import { IssueSelector } from './components/issue-selector/issue-selector';
import { NoteEditor } from './components/note-editor/note-editor';

export const routes: Routes = [
  { path: '', component: IssueSelector, title: 'Nova nota devolutiva' },
  { path: 'notas/:id', component: NoteEditor, title: 'Editar nota devolutiva' },
  { path: '**', redirectTo: '' },
];
