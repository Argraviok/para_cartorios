# Cartório AI — sistema integrado

Os 7 MVPs reunidos num só lugar, com um portal único.

```bash
npm run dev          # sobe o portal + todos os módulos → http://localhost:4000
node subir_todos.mjs fraude lgpd   # só alguns módulos (pelo slug)
npm run testes       # roda os testes de todos os módulos e atualiza o relatório
```

| Módulo (slug) | Pasta em `modulos/` | API / web |
|---|---|---|
| exame | Triagem_de_Documentos | 8030 / 4230 |
| notas | segunda_tarefa | 8040 / 4240 |
| transcricao | terceira_tarefa | 8050 / 4250 |
| matricula | quarta_parte | 8010 / 4210 |
| atendimento | Quinta_parte | 8020 / 4220 |
| fraude | Sexta_parte | 8060 / 4260 |
| lgpd | Setima_parte | 8000 / 4200 |

- `portal/` — servidor (porta 4000) e casca com menu; cada módulo aparece dentro dela.
- `modulos/` — cópias dos projetos. As pastas originais em `~/` continuam existindo como estavam.
- Como as cópias usam as mesmas portas dos originais, não rode o original e a cópia do mesmo módulo ao mesmo tempo
  (o `npm run dev` pula módulos com porta ocupada).
- Primeira vez numa máquina nova: em cada módulo, `npm run setup` (ou o passo a passo do README dele).
