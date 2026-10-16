# Gerador de Notas Devolutivas (MVP)

Implementação de [SPEC_MVP_NOTA_DEVOLUTIVA_AI.md](SPEC_MVP_NOTA_DEVOLUTIVA_AI.md): FastAPI + MongoDB (Vector Search + Atlas Search) + Angular 20.

> **As 8 fichas do seed têm `verified=false`.** Citam apenas dispositivos de lei federal e não têm jurisprudência. Precisam de revisão jurídica antes do uso em produção.

## Rodar localmente

**1. MongoDB com busca vetorial**: use um cluster Atlas (`MONGO_URI`) ou a imagem local:

```bash
docker run -d --name notas-atlas-local -p 27018:27017 mongodb/mongodb-atlas-local:8.0
```

**Atalho:** na raiz, `npm install` (uma vez) e depois `npm run dev` sobe a API (:8040, com reload) e o Angular (:4240) juntos. `npm run setup` instala as dependências dos dois lados; `npm test` roda os testes.

**2. Backend**

```bash
cd backend
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env              # MONGO_URI, MONGO_DB e GEMINI_API_KEY ou OPENAI_API_KEY
.venv/bin/python -m scripts.create_indexes
.venv/bin/python -m scripts.seed_precedents          # sem chave de API: --skip-embeddings
.venv/bin/uvicorn app.main:app --port 8040
```

Documentação interativa da API: http://localhost:8040/docs

**3. Frontend**

```bash
cd frontend
npm install
npx ng serve                      # http://localhost:4240 (proxy /api → :8040)
```

## Modos do LLM (`LLM_PROVIDER`)

Sem `LLM_PROVIDER`, o provedor é o da chave preenchida (`GEMINI_API_KEY` ou `OPENAI_API_KEY`). Com as duas chaves, defina-o explicitamente. O modelo vem de `GEMINI_MODEL` / `OPENAI_MODEL`; os embeddings seguem o mesmo provedor.

| Valor | Comportamento |
|---|---|
| `gemini` | `google-genai`, saída estruturada com `response_schema`. Em sobrecarga (429/500/503), tenta `GEMINI_FALLBACK_MODELS` em ordem; a nota registra o modelo que respondeu |
| `openai` | `responses.parse` com `text_format` |
| `offline` | Sem IA: usa a redação-modelo da ficha mais relevante + os fatos informados. Serve para demonstração e contingência. |

Em todos os modos, a fundamentação exibida é montada pelo backend a partir das fichas recuperadas. Uma resposta do LLM que cite um ID não recuperado é rejeitada: o backend tenta mais uma vez e, se falhar de novo, devolve 502.

## Testes

```bash
cd backend && .venv/bin/python -m pytest          # 45 testes; os de integração usam o Mongo local em :27018 (TEST_MONGODB_URI)
```

Os testes de integração (`-m integration`) usam um banco descartável e verificam:
- busca vetorial e textual reais, com filtros por vício e por UF;
- numeração concorrente sem duplicidade;
- trava de emissão;
- controle de versão.

Se o Mongo não estiver acessível, eles são pulados.

## Trocar o modelo de embedding

1. Ajuste `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` e `EMBEDDING_DIMS`.
2. Se a dimensão mudou, rode `python -m scripts.create_indexes`.
3. Rode `python -m scripts.reindex_embeddings`.
