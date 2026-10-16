# Cartório AI — Prevenção à Fraude e Due Diligence (MVP)

Backend FastAPI + MongoDB e frontend Angular 20 (standalone + Tailwind), conforme `SPEC_MVP_PREVENCAO_FRAUDE_AI`.

## Subir localmente

```bash
docker compose up -d                       # MongoDB na porta 27020
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                       # preencha STORAGE_ENCRYPTION_KEY (comando no arquivo)
.venv/bin/python seed_signatures.py --samples   # cartões de firma + imagens de teste em samples/
.venv/bin/uvicorn app.main:app --reload --port 8060    # http://localhost:8060/docs
.venv/bin/python -m pytest                 # testes

cd ../frontend && npm install && npx ng serve --port 4260   # http://localhost:4260
```

## Camadas de verificação

| Camada | Implementação | Observações |
|---|---|---|
| Análise forense | ELA por blocos 16×16, normalizado por faixa de textura (z-score robusto), metadados EXIF/PDF, VLM opcional para tipografia/elementos de segurança | ELA só é confiável em JPEG de origem; PNG/PDF rasterizado pesa metade. PDF com JPEG embutido é extraído sem recompressão. |
| Cotejo de assinatura | 8 atributos (forma HOG, perfis, inclinação global, proporção, continuidade, densidade, calibre, variação de pressão) + VLM opcional | Triagem — não substitui perícia grafotécnica. |
| Procuração / CENSEC | Regras sobre livro/folha/origem, idade (> 5 anos), revogação declarada e data da consulta de não-revogação (válida 30 dias) | A CENSEC não tem API pública: o escrevente informa a data da consulta. `CensecGateway` permite plugar integração oficial. |
| Biometria facial | **Não implementada** (status `NAO_EXECUTADO`) | Prevista na arquitetura, fora do escopo do MVP. |

Score consolidado: média ponderada (45/35/20) com piso de 85% do pior sinal; procuração revogada ≥ 90; adulteração + assinatura divergente ≥ 85; reincidência do CPF soma até +15.

## API

- `POST /api/fraud/audit-document` — multipart: `document`, `signature_image?`, `protocol_number`, `service_type`, `document_type`, `presenter_cpf?`, `procuration_*`, `censec_confirmed_on?`
- `GET /api/fraud/audits`, `GET /api/fraud/audits/{id}`, `GET /api/fraud/stats`
- `GET /api/fraud/audits/{id}/files/{document|heatmap|ela|signature|signature_card}`
- `PATCH /api/fraud/audits/{id}/decision` — `APROVAR_FE_PUBLICA` | `SOLICITAR_PRESENCIAL` | `REJEITAR_FALSIDADE`, com justificativa obrigatória. Decisão final é imutável (409); histórico append-only.
- `POST/GET /api/signature-cards`, `GET /api/signature-cards/by-cpf/{cpf}`, `GET /api/signature-cards/{id}/image`

## Segurança e LGPD

- Arquivos criptografados em repouso (Fernet); servidos apenas pela API com `Cache-Control: no-store`.
- `API_TOKEN` habilita autenticação Bearer em todas as rotas `/api` (defina também em `frontend/src/environments/environment.ts`).
- `purge_expired_files.py` apaga as imagens de auditorias decididas após `RETENTION_DAYS`, mantendo laudo e log. Agende diariamente.
- Logs mascaram CPF.

## Pendências para produção

Autenticação de usuários com identidade do oficial (hoje o nome é digitado no despacho), biometria facial com liveness, integração oficial CENSEC, calibração dos limiares com documentos reais da serventia, armazenamento em objeto (S3/GCS) com KMS.
