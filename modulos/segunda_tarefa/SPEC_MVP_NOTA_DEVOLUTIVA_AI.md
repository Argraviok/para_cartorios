# ESPECIFICAÇÃO DE DESENVOLVIMENTO — MVP GERADOR DE NOTAS DEVOLUTIVAS COM IA

> Instruções para o agente de código: implemente exatamente o que está aqui. Onde houver dúvida, prefira a opção mais simples que respeite as **Regras Invioláveis** (seção 7). Não invente dados jurídicos (artigos, ementas, números de processo) em nenhum arquivo.

## 1. ESCOPO

Microsserviço + módulo web para cartórios que transforma apontamentos fáticos de vícios, informados pelo escrevente, em minuta de Nota Devolutiva fundamentada, usando RAG sobre uma base curada de fundamentos (`legal_precedents`). A minuta é sempre revisada e emitida por um humano.

**Fora do MVP** (não implementar agora): autenticação/perfis, exportação .docx/PDF assinado, integração com sistemas de gestão do cartório, uso do histórico de notas como base de RAG, regeneração de exigência individual.

---

## 2. STACK

- **Frontend:** Angular 17+ (standalone components, signals, Reactive Forms, Angular CDK drag-drop), TailwindCSS.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, **PyMongo Async API (`AsyncMongoClient`)** — não usar Motor (descontinuado).
- **Banco:** MongoDB Atlas, com índice **Vector Search** e índice **Atlas Search** (texto) na coleção `legal_precedents`.
- **LLM:** abstraído atrás de uma interface; provedor escolhido por variável de ambiente.
  - `LLM_PROVIDER=gemini` (padrão) → SDK `google-genai`, saída estruturada com `response_mime_type="application/json"` + `response_schema=<modelo Pydantic>`.
  - `LLM_PROVIDER=openai` → SDK `openai`, `client.responses.parse(..., text_format=<modelo Pydantic>)`.
  - `LLM_PROVIDER=offline` → sem LLM: a minuta usa a `recommended_text` da ficha mais relevante + os `case_facts` (contingência e uso sem chave).
  - Nome do modelo em `LLM_MODEL` (não fixar no código). `temperature` ≤ 0.2.
- **Embeddings:** dimensão fixa **768** para qualquer provedor.
  - Gemini: `gemini-embedding-001` com `output_dimensionality=768`.
  - OpenAI: `text-embedding-3-small` com `dimensions=768`.
  - Gravar `embedding_model` em cada documento. Trocar de modelo exige reindexar tudo (script `reindex_embeddings.py`).

---

## 3. MODELAGEM (MongoDB Atlas)

### 3.1 Enum `VicioCode` (fonte única, usada no back e servida ao front)

`quebra_continuidade`, `itbi_nao_recolhido`, `procuracao_sem_censec`, `outorga_conjugal`, `descricao_tabular_divergente`, `debito_condominial`, `cnd_municipal_ausente`, `averbacao_casamento_pendente`, `outro`.

Cada código tem `label` em português para exibição (ex.: `cnd_municipal_ausente` → "Ausência de CND Municipal").

### 3.2 Coleção `legal_precedents` (fichas curadas)

| Campo | Tipo | Observação |
|---|---|---|
| `_id` | string | slug legível, ex. `prec_outorga_conjugal_01` |
| `vicio_code` | VicioCode | filtro do vector search |
| `title` | string | |
| `scope` | `"nacional"` \| `"estadual"` | |
| `uf` | string \| null | obrigatório se `scope="estadual"`; fichas nacionais são encontradas pelo filtro `scope="nacional"` |
| `normative_refs` | `[{diploma: str, artigo: str \| null}]` | ex. `{diploma: "Lei 6.015/1973", artigo: "195"}` |
| `jurisprudence` | `[{orgao, numero, ementa, source_url}]` | **pode ser lista vazia** |
| `recommended_text` | string | modelo de redação da serventia |
| `suggested_solution` | string | providência padrão |
| `embedding_text` | string | `title + recommended_text + ementas` — único texto que vira vetor |
| `embedding` | float[768] | |
| `embedding_model` | string | |
| `vigente` | bool | filtro |
| `verified` | bool | `false` até revisão por jurista |
| `verified_by` / `verified_at` | string / Date \| null | |
| `updated_at` | Date | |

**Índice vetorial** (`precedents_vector`):
```json
{ "fields": [
  { "type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine" },
  { "type": "filter", "path": "vicio_code" },
  { "type": "filter", "path": "vigente" },
  { "type": "filter", "path": "scope" },
  { "type": "filter", "path": "uf" }
]}
```

**Índice de texto** (`precedents_text`):
```json
{ "mappings": { "dynamic": false, "fields": {
  "title":          { "type": "string", "analyzer": "lucene.portuguese" },
  "embedding_text": { "type": "string", "analyzer": "lucene.portuguese" },
  "normative_refs": { "type": "document", "fields": { "diploma": { "type": "string" } } },
  "vicio_code":     { "type": "token" },
  "scope":          { "type": "token" },
  "uf":             { "type": "token" },
  "vigente":        { "type": "boolean" }
}}}
```

Script `create_indexes.py` cria os dois índices via `create_search_index` e os índices comuns de `devolution_notes`. Deve ser idempotente.

### 3.3 Coleção `devolution_notes`

| Campo | Tipo | Observação |
|---|---|---|
| `_id` | ObjectId | |
| `note_number` | string \| null | `"192/2026"`; **atribuído só na emissão** |
| `protocol_number` | string | só dígitos, sem pontuação |
| `protocol_date` | Date | |
| `act_type` | string | |
| `presenter_name` | string | |
| `uf` | string | |
| `status` | `"draft"` \| `"issuing"` \| `"issued"` | `issuing` é a trava transitória da emissão; `issued` é imutável |
| `requirements` | `Requirement[]` | ver abaixo |
| `full_compiled_text` | string | **sempre derivado** de `requirements` pelo template; nunca editado diretamente |
| `llm_model` / `prompt_version` | string | auditoria |
| `version` | int | controle de concorrência otimista |
| `created_at` / `updated_at` / `issued_at` | Date | BSON Date, nunca string |

`Requirement`:
`order: int`, `vicio_code: VicioCode`, `legal_topic: str`, `precedent_ids: list[str]`, `legal_basis: str` (montado pelo backend a partir de `normative_refs` das fichas citadas, agrupado por diploma: `Lei 6.015/1973, arts. 195 e 237`), `justification_draft: str` (texto do LLM), `user_edited_text: str | null`, `suggested_solution: str`, `source: "ai" | "manual"`, `grounded: bool`.

Índices comuns: `{status: 1, created_at: -1}`, `{protocol_number: 1}`, `{note_number: 1}` (único, `partialFilterExpression: {note_number: {$type: "string"}}`).

### 3.4 Coleção `counters`

`{_id: "devolution_note_2026", seq: int}`. Incremento atômico com `find_one_and_update({_id}, {$inc: {seq: 1}}, upsert=True, return_document=AFTER)`.

---

## 4. BACKEND (FastAPI)

### 4.1 Estrutura

```
backend/
├── app/
│   ├── api/endpoints/
│   │   ├── precedents.py
│   │   ├── vicios.py
│   │   └── devolution.py
│   ├── core/
│   │   ├── config.py          # pydantic-settings; lê .env
│   │   └── database.py        # AsyncMongoClient, lifespan
│   ├── schemas/
│   │   ├── enums.py           # VicioCode + labels
│   │   ├── precedent_schema.py
│   │   └── devolution_schema.py
│   ├── services/
│   │   ├── embedding_service.py
│   │   ├── search_service.py      # busca híbrida
│   │   ├── llm_service.py         # interface + GeminiClient + OpenAIClient
│   │   ├── generator_service.py   # orquestra busca → LLM → validação
│   │   └── render_service.py      # template Jinja2 → Markdown
│   ├── templates/
│   │   └── nota_devolutiva.md.j2
│   └── main.py
├── scripts/
│   ├── create_indexes.py
│   ├── seed_precedents.py
│   └── reindex_embeddings.py
├── tests/
├── .env.example
└── requirements.txt
```

`config.py` também carrega os dados da serventia (`SERVENTIA_NOME`, `SERVENTIA_CNS`, `OFICIAL_NOME`, `SERVENTIA_ENDERECO`, `SERVENTIA_CIDADE_UF`, `PRENOTACAO_DIAS`). Nada disso fica fixo no template.

### 4.2 Busca híbrida (`search_service.py`)

`async def search_precedents(vicio_code, case_facts, uf, k=4) -> list[dict]`

1. Gera o embedding de `case_facts`.
2. Executa em paralelo (`asyncio.gather`):
   - `$vectorSearch` em `precedents_vector`, `numCandidates=100`, `limit=10`, `filter: {vicio_code, vigente: true, $or: [{scope: "nacional"}, {uf}]}`;
   - `$search` em `precedents_text`, `compound.should` no texto de `case_facts` + `filter` por `vicio_code`, `vigente` e (`scope="nacional"` ou `uf`), `limit=10`.
3. Funde as duas listas por **Reciprocal Rank Fusion** em Python (`score = Σ 1/(60 + rank)`), deduplica por `_id` e retorna os `k` primeiros.
4. Não usar `$rankFusion` (depende da versão do cluster).
5. Se uma das metades falhar (índice ausente, provedor de embedding fora), a outra continua respondendo.

### 4.3 Geração (`generator_service.py`)

Fluxo de `generate(req: GenerateNoteRequest)`:

1. Para cada `issue` com `vicio_code != "outro"`: `search_precedents` em paralelo.
2. Separa os vícios **com** resultado (grounded) dos vícios **sem** resultado ou `outro` (ungrounded).
3. Chama o LLM **uma única vez** com todos os grounded, para que a nota contenha todas as exigências de uma só vez (art. 198 da LRP).
   - Prompt de sistema: papel de escrevente/oficial, tom técnico-impessoal, regras da seção 7.
   - Contexto: cada ficha delimitada por `<ficha id="...">...</ficha>`; fatos de cada vício delimitados por `<fatos vicio="...">...</fatos>`.
   - Schema de saída (`LLMNoteDraft`): `requirements: [{vicio_code, legal_topic, precedent_ids, justification_draft, suggested_solution}]`. **O LLM não gera** `order`, `legal_basis`, `protocol_number`, introdução, fecho nem texto completo.
4. **Validação obrigatória:** cada `precedent_ids` deve ser não vazio e estar contido nos IDs recuperados para aquele `vicio_code`. Em falha: uma nova tentativa com a mensagem de erro anexada ao prompt; se falhar de novo, HTTP 502 com detalhe.
5. Monta `Requirement` com `order` sequencial e `legal_basis` formatado a partir de `normative_refs` das fichas citadas.
6. Para cada ungrounded: `Requirement` placeholder com `source="manual"`, `grounded=false`, `legal_topic=label do vício`, `justification_draft=case_facts`, `legal_basis=""` e aviso em `warnings`.
7. Renderiza `full_compiled_text` via `render_service`.
8. Persiste como `draft` e retorna.

### 4.4 Template (`nota_devolutiva.md.j2`)

Ordem: cabeçalho da serventia (nome, CNS, endereço) → `NOTA DEVOLUTIVA Nº {{ note_number or "MINUTA" }}` → protocolo nº e data, ato, apresentante → parágrafo introdutório fixo ("Em cumprimento ao disposto no art. 198 da Lei nº 6.015/1973, ...") → exigências numeradas (título, fundamentação, justificativa usando `user_edited_text` se houver, senão `justification_draft`, e providência) → parágrafo de prazo ("O título deverá ser reapresentado com o cumprimento integral das exigências no prazo de vigência da prenotação, nos termos do art. 205 da Lei nº 6.015/1973.", com `PRENOTACAO_DIAS` de config) → local e data → bloco de assinatura (Oficial/Substituto). Rascunho exibe `MINUTA — SEM VALOR OFICIAL`.

### 4.5 Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/vicios` | lista `[{code, label}]` |
| GET | `/api/precedents` | lista fichas (sem `embedding`) |
| POST | `/api/precedents` | cria ficha (gera embedding; `verified=false`) |
| POST | `/api/devolution-notes/generate` | body `GenerateNoteRequest` → `DevolutionNoteResponse` (inclui `note_id`, `warnings`) |
| GET | `/api/devolution-notes/{id}` | lê nota |
| PATCH | `/api/devolution-notes/{id}` | atualiza `requirements` (edição, reordenação, exclusão); recebe `version`; 409 se divergir; 409 se `issued`; re-renderiza `full_compiled_text` |
| POST | `/api/devolution-notes/{id}/preview` | renderiza Markdown a partir de `requirements` enviados, sem salvar |
| POST | `/api/devolution-notes/{id}/issue` | trava `draft → issuing` atomicamente, valida (≥1 exigência, todas com fundamentação e providência; senão 422 e destrava), atribui `note_number` pelo contador, `status=issued`; irreversível |
| GET | `/api/devolution-notes/{id}/export.md` | download do Markdown |
| GET | `/api/devolution-notes/{id}/export.txt` | download em texto puro (Markdown removido) |

`GenerateNoteRequest`:
```json
{
  "protocol_number": "184920",
  "protocol_date": "2026-10-14",
  "act_type": "escritura_compra_venda",
  "presenter_name": "Banco do Brasil S.A.",
  "uf": "SP",
  "issues": [
    { "vicio_code": "quebra_continuidade",
      "case_facts": "Na matrícula 12.345 o transmitente consta como solteiro; no título qualifica-se como casado no regime da comunhão parcial com Maria dos Santos." }
  ]
}
```
Validações: `issues` com 1+ itens; `case_facts` com no mínimo 20 caracteres; `uf` com 2 letras.

### 4.6 `seed_precedents.py`

- Cria **uma ficha por `VicioCode`** (exceto `outro`), 8 no total, para compra e venda.
- `normative_refs` preenchidos **apenas** com dispositivos de lei federal amplamente conhecidos e estáveis. Na dúvida, deixe o artigo `null` e cite só o diploma.
- `jurisprudence: []` em todas. **Não inventar ementas nem números de processo.**
- `verified: false` em todas. O script imprime ao final: "N fichas criadas com verified=false — revisão jurídica obrigatória antes do uso em produção."
- Idempotente (upsert por `_id`).

### 4.7 Testes mínimos (`pytest`)

- Validação de citações: LLM mockado retornando `precedent_id` inexistente → nova tentativa → 502.
- Vício sem precedente → placeholder `grounded=false` + `warning`, e o LLM não recebe esse vício.
- PATCH em nota `issued` → 409; PATCH com `version` antiga → 409.
- Emissão concorrente de duas notas → números distintos e sequenciais.
- Render: `user_edited_text` tem precedência sobre `justification_draft`.

---

## 5. FRONTEND (Angular)

### 5.1 Estrutura

```
frontend/src/app/
├── components/
│   ├── issue-selector/
│   ├── note-editor/
│   │   └── requirement-card/
│   └── note-preview/
├── services/
│   └── devolution.service.ts
├── models/
│   └── devolution.models.ts   # espelha os schemas Pydantic
└── app.routes.ts
```

### 5.2 Telas

1. **Entrada (`issue-selector`)**
   - Campos: protocolo, data do protocolo, tipo de ato, apresentante, UF.
   - Checkboxes carregados de `GET /api/vicios`. Ao marcar um vício, abre textarea **obrigatória** "Fatos observados" (`case_facts`).
   - Opção "Outro" com título livre + fatos.
   - Botão "Gerar minuta" → `POST /generate` → navega para o editor com o `note_id`. Exibir `warnings` em destaque.

2. **Editor (`note-editor`), layout dividido**
   - **Esquerda:** um `requirement-card` expansível por exigência, com os campos Título, Fundamentação, Justificativa e Providência. Badges "IA" / "Manual" e "Sem fundamentação na base" quando `grounded=false`. A edição da justificativa grava em `user_edited_text`. Reordenar por CDK drag-drop; excluir com confirmação; adicionar exigência manual.
   - **Direita (`note-preview`):** prévia ao vivo. Chamar `POST /preview` com debounce de 400 ms; converter Markdown com `marked` e sanitizar com `DOMPurify` antes de exibir.
   - Salvamento automático: `PATCH` com debounce de 1,5 s, enviando `version`. Em 409, avisar e oferecer recarregar.
   - Nota `issued`: tudo somente leitura.

3. **Ações**
   - "Copiar texto formatado": `navigator.clipboard.write([new ClipboardItem({"text/html": ..., "text/plain": ...})])`.
   - "Copiar sem formatação": somente `text/plain`.
   - "Baixar .md" / "Baixar .txt": endpoints de export.
   - "Emitir nota": diálogo de confirmação ("a nota receberá número oficial e não poderá mais ser editada") → `POST /issue`.

---

## 6. ESTILO DA REDAÇÃO

- Tom técnico-jurídico, impessoal e administrativo: "Verifica-se que...", "Constata-se...", "Cumpre ao apresentante...", "Nos termos do art. X da Lei nº Y...".
- Cada justificativa deve descrever o fato concreto informado em `case_facts`, sem acrescentar fatos não informados.
- A providência deve ser objetiva e executável (o que apresentar, onde obter, para qual ato).

---

## 7. REGRAS INVIOLÁVEIS

1. **O LLM só cita fundamentos das fichas recuperadas**, por `precedent_id`. A fundamentação exibida é montada pelo backend a partir das fichas, não pelo texto do LLM.
2. **Sem ficha na base → sem citação.** O vício vira exigência manual (`grounded=false`) sinalizada ao escrevente. **Não** substituir por "normas genéricas".
3. **Nenhum dado jurídico inventado** em seed, testes, fixtures ou prompts: nada de ementas, números de processo ou artigos fictícios.
4. **Nenhum fato inventado** além de `case_facts`.
5. **Nota emitida é imutável**; o número só é atribuído na emissão.
6. **Prazos e dados da serventia vêm de configuração**, nunca fixos no código. Confirmar `PRENOTACAO_DIAS` com a redação vigente do art. 205 da LRP e as normas da CGJ local antes de colocar em produção.
7. Chaves de API apenas em `.env` (fornecer `.env.example`); nunca commitadas.
