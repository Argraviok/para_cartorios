# Cartório AI — Triagem, Atendimento e Estimativa de Emolumentos

MVP de atendimento conversacional para cartório de notas. O cidadão conversa pelo webchat (ou WhatsApp, via
integração) e a IA identifica o serviço, calcula a estimativa de emolumentos e confere as fotos dos documentos.
O escrevente acompanha tudo num inbox em tempo real e pode assumir a conversa quando quiser.

Especificação original: [SPEC_MVP_TRIAGEM_ATENDIMENTO_AI.md](SPEC_MVP_TRIAGEM_ATENDIMENTO_AI.md).

```
Cidadão (widget /atendimento ou WhatsApp) ──► FastAPI :8020
   ├─ Engine de diálogo: máquina de estados determinística + LLM só para entender a mensagem
   ├─ Emolumentos: fee_schedules (faixas por valor declarado / atos fixos) + ISSQN, em Decimal
   ├─ Checagem de fotos: pré-filtro Pillow (resolução/nitidez) → VLM → regra de prazo no servidor
   └─ MongoDB: triages · act_requirements · fee_schedules
Painel do escrevente (/painel) ──► inbox por status · dossiê (chat + checklist + lightbox + emolumentos)
```

## Como rodar

Pré-requisitos: Python 3.11+ (testado com 3.14) e Node 22.

```bash
npm run setup      # 1ª vez: venv Python + node_modules do Angular + backend/.env a partir do exemplo
npm run dev        # API em :8020 (--reload) + web em http://localhost:4220 ; Ctrl+C encerra
npm test           # 40 testes do backend (não chamam IA nem banco reais)
npm run seed       # grava o catálogo no MongoDB (exige MONGODB_URI); --demo cria 3 atendimentos fictícios
```

- Painel do escrevente: http://localhost:4220/painel
- Simulador do cidadão (abra no celular ou com a janela estreita): http://localhost:4220/atendimento
- Documentação da API: http://localhost:8020/docs

As portas 8020 e 4220 foram escolhidas para não conflitar com os outros MVPs desta máquina (8000/8010, 4200/4210).
O `predev` encerra instâncias antigas **deste** projeto que ainda estejam nas portas.

## Comportamento sem configuração

| Item | Sem variável definida | Com variável |
|---|---|---|
| Banco | repositório em memória (perde dados ao reiniciar) | `MONGODB_URI` / `MONGODB_DB` → Atlas. O catálogo é semeado sozinho se estiver vazio |
| Diálogo | regras locais: palavras-chave por ato, leitura de valores ("450 mil", "R$ 1,2 milhão"), pedido de atendente | `GEMINI_API_KEY` ou `OPENAI_API_KEY` → entendimento por LLM com Structured Outputs e respostas a dúvidas livres |
| Fotos | pré-filtro de qualidade; fotos nítidas ficam "Aguardando conferência" para o escrevente | VLM identifica o tipo, a legibilidade e a data de emissão |
| Demonstração | `DEMO_DATA=true` cria 3 atendimentos fictícios se o banco estiver vazio | — |

O `backend/.env` atual reaproveita as chaves Gemini/OpenAI do projeto `quarta_parte` e está **sem** `MONGODB_URI`,
ou seja, em memória. Para usar o Atlas, preencha `MONGODB_URI`. O banco padrão é `cartorio_triagem`, separado dos
outros projetos.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/triage/sessions` | Abre um atendimento (`customer_contact`, `customer_name?`). O bot já cumprimenta |
| `POST` | `/api/triage/message` | Mensagem do cidadão. Sem `protocol_id`, retoma o atendimento aberto do `customer_contact` (formato pensado para webhook de WhatsApp) |
| `POST` | `/api/triage/upload-doc` | multipart: `protocol_id`, `file`, `doc_index?` (vazio = próximo pendente). Valida e atualiza o checklist |
| `POST` | `/api/triage/verify-photo` | Checagem avulsa de foto (`expected_doc_type`, `file`), sem gravar nada |
| `GET` | `/api/triage/sessions` | Inbox do escrevente (`status?`), com contagem de documentos validados |
| `GET` | `/api/triage/sessions/{id}` | Atendimento completo |
| `POST` | `/api/triage/sessions/{id}/takeover` | Transfere para atendimento humano (o bot para de responder) |
| `POST` | `/api/triage/sessions/{id}/attendant-message` | Mensagem do escrevente (escrever já assume o atendimento) |
| `POST` | `/api/triage/sessions/{id}/release` | Devolve ao assistente virtual |
| `PATCH` | `/api/triage/sessions/{id}/checklist/{i}` | Conferência manual: `VALIDADO`, `REJEITADO` (com motivo) ou `PENDENTE`. Avisa o cidadão no chat |
| `POST` | `/api/triage/sessions/{id}/counter-ticket` | Gera a senha prioritária de balcão (P001, P002… por dia) |
| `GET` | `/api/acts` · `/api/fees/schedules` · `/api/fees/estimate` | Catálogo de atos, tabelas e simulação avulsa |

## Decisões de implementação

- **O LLM não decide valores nem prazos.** Ele só classifica a mensagem (intenção, ato, valor declarado, nome)
  e redige respostas a dúvidas usando o contexto que recebe. Os emolumentos vêm de `fee_schedules` e são calculados
  em `Decimal` com arredondamento comercial. O checklist vem de `act_requirements`. A validade "atualizada há 90 dias"
  é conferida pelo servidor a partir da data de emissão lida pelo VLM, inclusive quando só aparece o ano
  ("emitida em 2021"). Assim o modelo não erra conta de data nem inventa preço.
- **Pré-filtro de foto:** antes de chamar o VLM, o Pillow corrige a rotação EXIF e recusa fotos com menos de 480 px
  no menor lado ou visivelmente borradas (desvio-padrão do mapa de bordas abaixo de 5, medido em ~1000 px). O limite
  é conservador; casos duvidosos ficam com o VLM. Fotos de câmera são reduzidas para 1600 px antes do envio.
- **Status a mais:** além dos quatro da spec, o VLM pode devolver `REVISAO_MANUAL` (legível, mas sem data de
  emissão identificável, ou IA indisponível). Nesse caso o item fica `ENVIADO` ("aguardando conferência") e o
  escrevente valida no lightbox.
- **Inbox:** 🟡 `in_progress` (em triagem com IA), 🟢 `ready_for_counter` (todos os obrigatórios validados) e
  🔴 `human_takeover` (pediu atendente ou o escrevente assumiu). Os pedidos de atendente aparecem no topo.
- **Concorrência:** mensagens entram com `$push` e campos com `$set`, sem sobrescrever o documento inteiro. Se o
  escrevente assumir enquanto o LLM ainda responde, a resposta do bot é descartada.
- **Driver:** a spec pede Motor, mas o Motor foi descontinuado. O código usa o `AsyncMongoClient` do PyMongo, seu
  sucessor oficial, com a mesma API assíncrona.
- **Modelo:** a spec cita Gemini 2.5 Flash. O padrão é `gemini-3.8-flash`, o mesmo do quarta_parte, com
  `GEMINI_FALLBACK_MODELS` em caso de 429/503, e o modelo que respondeu fica registrado no campo `engine` do
  parecer. `OPENAI_MODEL=gpt-4o-mini` também funciona.
- **Tempo real:** feito com polling: o painel atualiza a cada 3 s e o widget a cada 4 s, o que basta para um MVP.

## Atenção antes de usar com o público

- **As tabelas de emolumentos são ILUSTRATIVAS** ([backend/app/catalog.py](backend/app/catalog.py)). Os valores
  foram escolhidos para reproduzir o exemplo da spec (inventário de R$ 450 mil = R$ 2.450,80), não a tabela
  oficial. Substitua pela tabela vigente da Corregedoria (em SP, Lei 11.331/2002 e tabelas anuais) e rode
  `npm run seed`.
- **Não há autenticação.** O painel e a API estão abertos, e as fotos de documentos ficam em `/media` com nome
  aleatório, mas sem controle de acesso. Login de escrevente e URLs assinadas são pré-requisitos de LGPD para
  produção.
- Habilitação de casamento é ato do Registro Civil, não do Tabelionato de Notas. Ela está no catálogo porque a
  spec pediu.
- Fora do escopo: webhook do WhatsApp (o `/message` já aceita `customer_contact` para essa integração), botão
  "Iniciar minuta" (aparece desabilitado) e transcrição de áudios.
