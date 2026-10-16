# ESPECIFICAÇÃO DE DESENVOLVIMENTO - MVP TRANSCRIÇÃO E INDEXAÇÃO DE LIVROS HISTÓRICOS DE CARTÓRIO

## 1. OBJETIVO DO SISTEMA
Construir um sistema para transcrição paleográfica automatizada, extração de entidades-chave (NER) e busca de acervos históricos (manuscritos e datilografados) de Registro de Imóveis (Livro 3 de Transcrições) e Registro Civil (Nascimento, Casamento e Óbito).

---

## 2. STACK TECNOLÓGICA
* **Frontend:** Angular 17+ (Standalone Components, TailwindCSS ou Angular Material, visualizador de imagem com suporte a Deep Zoom/Pan).
* **Backend:** Python 3.11+, FastAPI, OpenCV (`opencv-python-headless`), Motor (MongoDB driver assíncrono), Pydantic v2.
* **Banco de Dados:** MongoDB Atlas (com Atlas Search indexado para busca textual/fuzzy).
* **VLM Engine:** Gemini 2.5 Flash Multimodal ou Claude Haiku 3.5 (com envio da imagem e enforcement de Pydantic Schema).

---

## 3. BANCO DE DADOS (MONGODB ATLAS)

### Coleção: `historical_records`
- `book_type`: string ("transcricao_imobiliaria", "nascimento", "casamento", "obito")
- `book_number`: string
- `page_number`: number
- `entry_number`: string
- `entry_date_iso`: string (YYYY-MM-DD ou null)
- `image_url_or_base64`: string
- `transcription_raw`: string
- `status`: "analyzed" | "verified"
- `parties`: array de objetos:
  - `role`: string
  - `name_standardized`: string
  - `name_original`: string
- `confrontants_or_relatives`: array de strings
- `confidence_score`: number
- `created_at`: datetime

---

## 4. BACKEND (FASTAPI)

### Estrutura de Diretórios:
```
backend/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── ingest.py
│   │       └── search.py
│   ├── core/
│   │   ├── config.py
│   │   └── database.py
│   ├── schemas/
│   │   └── transcription_schema.py
│   ├── services/
│   │   ├── image_service.py
│   │   └── vlm_service.py
│   └── main.py
├── requirements.txt
└── seed_demo_data.py
```

### Funcionalidades do Backend:
1. `image_service.py`: Tratamento de imagem com OpenCV (conversão em tons de cinza, CLAHE para aumento de contraste de tintas antigas).
2. `vlm_service.py`: Envio da imagem tratada para a API multimodal instruindo o modelo com diretrizes paleográficas:
   - Decifrar caligrafia cursiva antiga e arcaísmos em português ("escriptura", "freguezia", "baptizado", "d'Oliveira").
   - Retornar o Pydantic Schema estruturado com `transcription_raw`, nomes normalizados e número do registro/folha.
3. `POST /api/historical/transcribe`: Endpoint multipart que recebe a imagem do livro, metadados (tipo de livro, livro, folha), processa via VLM e salva na base.
4. `GET /api/historical/search`: Endpoint que aceita termo de busca por nome de pessoa, número de registro ou confrontante, retornando resultados ordenados por relevância.
5. `PATCH /api/historical/records/{id}`: Permite ao operador humano corrigir termos lidos incorretamente pela IA e homologar a transcrição.

---

## 5. FRONTEND (ANGULAR)

### Estrutura de Diretórios:
```
frontend/
├── src/
│   ├── app/
│   │   ├── components/
│   │   │   ├── search-dashboard/
│   │   │   ├── batch-upload/
│   │   │   └── transcription-review/
│   │   │       ├── image-viewer/
│   │   │       └── entity-editor/
│   │   ├── services/
│   │   │   └── historical.service.ts
│   │   └── models/
│   └── ...
```

### Telas e Comportamentos:
1. **Painel de Busca Histórica:** Campo de busca rápida com filtros (Tipo de Livro, Período aproximado). Lista cartões com os assentos localizados e destaque nos nomes das partes.
2. **Tela de Revisão e Validação (Split-Screen):**
   - **Lado Esquerdo:** Visualizador de imagem do manuscrito original com ferramentas de Zoom, Pan e inversão de cores (facilita leitura de tintas claras).
   - **Lado Direito:** Formulário com os campos extraídos:
     - Transcrição completa em texto corrida.
     - Badges de partes envolvidas com opção de edição inline.
     - Indicador de confiança da IA (ex: 88% de precisão).
     - Botão "Homologar / Confirmar Registro".

---

## 6. DIRETRIZES DE PALEOGRAFIA E QUALIDADE
- Nomes próprios nunca devem ser abreviados na normalização ("Manoel" deve vir grafado como "MANOEL", mas se no original estiver "M.el", preservar a forma curta em `name_original`).
- Os campos devem tolerar trechos ilegíveis marcando com a tag `[ilegível]` na transcrição para revisão do usuário.
