# Arquivo Digital — Transcrição paleográfica de livros históricos de cartório

MVP que transcreve com IA páginas manuscritas e datilografadas de livros do Registro de Imóveis (Livro 3) e do
Registro Civil (nascimento, casamento, óbito). Ele extrai as partes envolvidas e indexa tudo para busca fuzzy e
fonética. Toda transcrição passa por revisão humana antes de ser homologada.

Especificação original: [SPEC_MVP_TRANSCRICAO_HISTORICA_AI.md](SPEC_MVP_TRANSCRICAO_HISTORICA_AI.md).

```
Upload em lote (Angular) ──► FastAPI /transcribe
                               ├─ OpenCV: tons de cinza → deskew (perfil de projeção) → denoise → CLAHE
                               ├─ Claude (claude-haiku-5-5) + saída estruturada Pydantic
                               └─ MongoDB `historical_records` + chave fonética PT-BR
Busca (Angular) ──► /search ──► Atlas Search (frase + fuzzy + fonética) │ fallback fonético/regex
Revisão split-screen ──► PATCH /records/{id} ──► status "verified"
```

## Como rodar

Pré-requisitos: Docker, Python 3.11+ (testado com 3.12), Node 22.

```bash
npm run setup      # uma vez: venv Python + node_modules do frontend + backend/.env a partir do exemplo
npm run seed       # opcional: 4 assentos de demonstração
npm run dev        # MongoDB (Docker) + API :8050 (--reload) + Angular :4250; Ctrl+C encerra
```

Passo a passo manual, equivalente:

```bash
# 1. MongoDB Atlas Local (inclui Atlas Search), exposto na porta 27019
docker compose up -d

# 2. Backend
cd backend
uv venv --python 3.12 .venv && uv pip install -p .venv -r requirements.txt   # ou python -m venv + pip
cp .env.example .env            # preencha ANTHROPIC_API_KEY
.venv/bin/python seed_demo_data.py --reset     # 4 assentos de demonstração (não chama a IA)
.venv/bin/uvicorn app.main:app --port 8050

# 3. Frontend (proxy de /api e /media para :8050)
cd frontend
npm install                     # .npmrc já define legacy-peer-deps
npx ng serve                    # http://localhost:4250
```

Documentação interativa da API: http://localhost:8050/docs

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/historical/transcribe` | multipart: `image`, `book_type`, `book_number`, `page_number`. Pré-processa a imagem, chama o VLM e grava com `status=analyzed` |
| `GET` | `/api/historical/search` | `q`, `book_type`, `status`, `year_from`, `year_to`, `limit`, `skip`. Resultados por relevância, com trechos destacados |
| `GET` | `/api/historical/records/{id}` | Assento completo |
| `PATCH` | `/api/historical/records/{id}` | Correção humana (campos parciais). `status: "verified"` homologa e `"analyzed"` reabre a revisão |
| `GET` | `/api/health` | Mostra se o Atlas Search está ativo e qual modelo de VLM está configurado |

## Decisões de implementação

- **VLM:** Claude Haiku 5.5 (`claude-haiku-5-5`), o Haiku atual, já que o Haiku 3.5 citado na spec foi aposentado.
  A chamada usa `messages.parse` com o schema Pydantic `HistoricalTranscriptionResult`, e o modelo devolve JSON
  validado. O prompt pede duas camadas: a transcrição diplomática, que preserva "mez", "d'Oliveira", "M.el" e
  `[ilegível]`, e os nomes normalizados em CAIXA ALTA sem abreviações. Modelo e esforço podem ser trocados por
  `VLM_MODEL` e `VLM_EFFORT`. Se um modelo mais forte ler melhor seus livros, `claude-sonnet-5-5` e
  `claude-opus-5-5` funcionam sem mudar o código.
- **Imagem:** a imagem enviada à IA fica em tons de cinza com CLAHE e **não** é binarizada, porque o Otsu apaga
  traços finos de pena. O Otsu serve só para medir a inclinação. O deskew usa perfil de projeção, que nos testes
  ficou a até ±0,2° do ângulo real numa faixa de ±10°. São gravadas duas versões: a original colorida, para o
  escrevente, e a realçada, que vai para a IA e pode ser alternada no visualizador.
- **Busca:** índice Atlas Search `historical_records_search`, criado automaticamente no startup. A consulta combina:
  frase exata no nome (peso 6), fuzzy de até 2 edições nos nomes, confrontantes e transcrição, número de registro
  exato e **chave fonética PT-BR** própria ([phonetic_service.py](backend/app/services/phonetic_service.py)). A
  chave fonética casa Manoel/Manuel, Thereza/Teresa, Ignacio/Inácio, Souza/Sousa, Phelippe/Felipe,
  Christovão/Cristóvão e Joaquim/Joaquin. Em um MongoDB sem Atlas Search, ou enquanto o índice está sendo
  construído, a API cai automaticamente para busca fonética com regex.
- **Revisão:** o visualizador é OpenSeadragon, com zoom, pan, rotação, inversão de cores, contraste, brilho e a
  alternância original/realce. O editor tem badges de partes editáveis inline e chips de
  confrontantes/filiação, além de um contador de `[ilegível]`. Atalhos: **Ctrl+S** salva e **Ctrl+Enter**
  homologa. O link "Próximo pendente" abre o próximo assento da fila.

### Diferenças em relação à spec

- `image_url_or_base64` virou `image_url` + `image_enhanced_url`, com as imagens servidas em `/media`. Guardar
  base64 no documento estouraria o limite de 16 MB do MongoDB com folhas em alta resolução.
- Campos extras no documento: `entry_date_text` (data por extenso, como escrita), `parties[].phonetic`,
  `search_phonetic` (uso interno da busca), `vlm_model`, `updated_at` e `verified_at`.
- O digitalizador TWAIN não é acessado direto pelo navegador. O fluxo previsto é o digitalizador salvar os
  arquivos numa pasta e o operador arrastá-los para a tela de lote. As folhas são numeradas pela ordem natural
  dos nomes dos arquivos.
- O Angular é a versão 21. O Angular 22 exige Node ≥ 22.22.3, e esta máquina tem o 22.22.1.

## Pendências conhecidas

- Não há autenticação nem trilha de auditoria de quem homologou. Isso é necessário antes de usar em produção num
  cartório.
- A transcrição é síncrona: cada requisição espera a resposta do VLM, e o lote envia 2 folhas por vez. Para
  acervos grandes, vale usar uma fila (ou a Batch API da Anthropic, com 50% de desconto).
- Ainda não há testes automatizados. A validação foi manual: API via curl, deskew com ângulos conhecidos,
  equivalências fonéticas e um fluxo E2E com Playwright.
