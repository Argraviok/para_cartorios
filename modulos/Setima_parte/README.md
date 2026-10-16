# Cartório AI — Anonimização e Tarjamento LGPD (MVP)

Este MVP detecta dados sensíveis de terceiros em certidões e autos em PDF e mostra cada sugestão ao escrevente para revisão. Depois que o escrevente aprova, o sistema aplica um tarjamento **destrutivo** no binário do PDF. O conteúdo sob a tarja é apagado do arquivo, não apenas coberto.

```
backend/   FastAPI + PyMuPDF + PyMongo (async)
frontend/  Angular 21 (standalone, signals, zoneless)
```

## Como rodar

```bash
npm run setup   # só na primeira vez: venv + deps Python, .env, PDFs de exemplo, deps do Angular
npm run dev     # MongoDB (docker) + API :8000 + frontend :4200 → http://localhost:4200
npm test        # testes do backend
```

Passo a passo manual, se preferir:

```bash
# MongoDB local (porta 27021). Em produção, aponte MONGODB_URI para o Atlas.
docker compose -p setima_lgpd up -d

# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python test_samples/generate_samples.py   # PDFs fictícios de exemplo
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/python -m pytest -q                       # testes, incl. o teste de seleção de texto

# Frontend (proxy /api -> localhost:8000)
cd frontend
npm install      # .npmrc já define legacy-peer-deps (contorna bug do npm 9 do Debian)
npx ng serve     # http://localhost:4200
```

## Fluxo

1. **Upload em lote** (`POST /api/redact/analyze`) de **PDF, DOCX ou DOC**. O formato é identificado pelo conteúdo do arquivo, não pela extensão. Documentos Word são convertidos para PDF pelo LibreOffice headless, e o tarjamento opera sobre esse PDF, que contém exatamente o que o revisor vê. O resultado é sempre um **PDF tarjado**. O original (o Word enviado e o PDF de trabalho) é gravado uma única vez, em modo somente leitura, e seus SHA-256 ficam registrados.
2. **Detecção híbrida.** As regras regex cobrem conta e agência, PIX, cartão (com validação Luhn), CPF (com validação dos dígitos verificadores), CID, condições de saúde, valores patrimoniais e menções à origem da filiação. Se o LLM estiver habilitado, ele procura o contexto sensível e devolve **trechos literais**. O sistema localiza esses trechos nas palavras extraídas pelo PyMuPDF. Por isso o modelo nunca inventa coordenadas.
3. **Revisão** no Redaction Studio:
   - clique na marcação para alternar entre tarjar e manter visível;
   - aprove ou rejeite por categoria;
   - desenhe tarjas manuais;
   - salve a revisão (`PUT /api/redact/jobs/{id}/items`).
4. **Homologação** (`POST /api/redact/apply`, exige `confirm_irreversible: true`). O sistema executa os passos abaixo, nesta ordem:
   - `apply_redactions` remove o texto, os pixels de imagem e os vetores que tocam a tarja;
   - as anotações sobrepostas às tarjas são excluídas;
   - `scrub` remove metadados, anexos, JavaScript e miniaturas;
   - o arquivo é regravado com `garbage=4`;
   - a **verificação obrigatória** reabre o PDF e testa se ainda existe texto extraível sob cada tarja. Se encontrar algum, retorna HTTP 500 e não entrega o arquivo.
5. **Auditoria** (`lgpd_audit_logs`). Cada registro guarda o evento, o operador, a data e hora, a contagem por categoria, as fundamentações e os hashes do original e do sanitizado. **Nenhum conteúdo tarjado é registrado.** Após a homologação, o `detected_text` também é apagado do job no MongoDB. Os relatórios estão em `/audit.pdf` e `/audit.csv`.

## Decisões e desvios em relação à spec

- **`bboxes` (lista) no lugar de `bbox`.** Um trecho que quebra de linha precisa de um retângulo por linha. Um retângulo único englobando as linhas tarjaria texto que não deveria.
- **PyMongo `AsyncMongoClient` no lugar de Motor.** O Motor foi descontinuado e chegou ao fim do suporte em maio de 2026.
- **`import pymupdf` no lugar de `import fitz`.** O nome `fitz` está deprecado.
- **Angular 21 no lugar de 22.** O Angular 22 exige Node ≥ 22.22.3, e a máquina tem a versão 22.22.1. A interface usa CSS próprio, sem Tailwind ou Material, e tem tema claro e escuro.
- **Nova categoria `DOCUMENTO_PESSOAL` (CPF).** As sugestões dessa categoria **nascem não aprovadas**, porque o CPF das partes geralmente integra o teor do ato. As demais categorias nascem aprovadas.
- **Estratégia para vetores.** Os vetores são removidos com `REMOVE_IF_TOUCHED`, que privilegia a segurança sobre a estética. Bordas de tabela que tocam uma tarja somem junto.

## Limitações conhecidas

- **Documentos Word exigem LibreOffice no servidor** (`soffice`; configurável por `SOFFICE_PATH`). A paginação do PDF convertido pode diferir levemente da do Microsoft Word. Comentários e texto oculto do Word não entram no PDF. Revisões controladas (track changes) aparecem conforme estavam configuradas para exibição no documento.
- **PDFs digitalizados** (sem camada de texto) geram um aviso e precisam de tarja manual. O apagamento de pixels funciona e está testado. A detecção automática nesses casos exige OCR, que fica como próxima etapa.
- **Sem autenticação.** O operador é um campo livre. Em produção, ele deve vir do login (SSO ou certificado ICP-Brasil).
- **Fundamentações legais.** Os textos ficam em `backend/app/core/legal_basis.py` e são sugestões que **devem ser validadas pelo jurídico**. O Provimento CNJ 134/2022 foi incorporado ao Código Nacional de Normas (Provimento 149/2023).
- **LLM externo.** Habilitar Gemini ou OpenAI envia o texto integral do documento ao provedor. Isso é uma transferência internacional de dados (LGPD art. 33) e exige base legal e contrato com o provedor. Por isso o padrão é `LLM_PROVIDER=none`.
