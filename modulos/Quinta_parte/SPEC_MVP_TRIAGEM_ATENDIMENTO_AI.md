# ESPECIFICAÇÃO DE DESENVOLVIMENTO - MVP ATENDIMENTO, TRIAGEM E ESTIMATIVA DE EMOLUMENTOS COM IA

## 1. OBJETIVO DO SISTEMA
Construir um sistema de triagem conversacional inteligente para cartórios. O sistema atende o cidadão via chat (web/WhatsApp), pré-qualifica o serviço desejado (ex: Inventário, Casamento, Procuração, Certidão), valida fotos dos documentos obrigatórios via IA visual e calcula uma estimativa precisa de emolumentos com base na tabela da Corregedoria.

---

## 2. STACK TECNOLÓGICA
* **Frontend:** Angular 17+ (Standalone Components, TailwindCSS ou Angular Material, visualizador de galeria/lightbox).
* **Backend:** Python 3.11+, FastAPI, Motor (MongoDB driver assíncrono), Pydantic v2.
* **Banco de Dados:** MongoDB Atlas (Coleções `triages`, `fee_schedules`, `act_requirements`).
* **LLM/VLM Engine:** Gemini 2.5 Flash ou OpenAI GPT-4o-mini (com processamento multimodal de imagens e Structured Outputs).

---

## 3. BANCO DE DADOS (MONGODB ATLAS)

### Coleção: `act_requirements`
Lista de documentos e regras prévias para cada serviço. Criar script `seed_requirements.py` contendo:
1. *Inventário Extrajudicial* (Óbito, CENSEC, Certidão de casamento atualizada, Docs dos herdeiros, IPTU/ITR).
2. *Habilitação de Casamento* (Nascimento atualizada 90 dias, Documento de identidade, Comprovante de residência).
3. *Procuração Pública de Imóvel* (RG/CPF outorgante, Certidão de matrícula, Estado civil).
4. *Certidão de Breve Relato / Inteiro Teor*.

### Coleção: `fee_schedules`
Tabela com valores de emolumentos e faixas progressivas conforme Provimento da Corregedoria.

### Coleção: `triages`
- `protocol_id`: string
- `customer_name`: string
- `customer_contact`: string (telefone ou email)
- `act_type`: string
- `status`: "in_progress" | "ready_for_counter" | "human_takeover"
- `estimated_total`: number
- `checklist`: array de objetos:
  - `doc_name`: string
  - `status`: "PENDENTE" | "ENVIADO" | "VALIDADO" | "REJEITADO"
  - `image_url`: string | null
  - `rejection_reason`: string | null
- `chat_history`: array de `{ sender: "user" | "bot" | "attendant", message: string, timestamp: datetime }`
- `created_at`: datetime

---

## 4. REQUISITOS DO BACKEND (FASTAPI)

### Estrutura de Diretórios:
```
backend/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── chat.py
│   │       ├── documents.py
│   │       └── fees.py
│   ├── core/
│   │   ├── config.py
│   │   └── database.py
│   ├── schemas/
│   │   └── triage_schema.py
│   ├── services/
│   │   ├── chat_service.py
│   │   ├── fee_calculator_service.py
│   │   └── doc_vision_service.py
│   └── main.py
├── seed_requirements.py
└── requirements.txt
```

### Funcionalidades do Backend:
1. `fee_calculator_service.py`: Calcula emolumentos somando taxa notarial, fundos institucionais e ISSQN para valores declarados ou atos fixos.
2. `doc_vision_service.py`: Recebe fotos enviadas pelo cidadão, verifica com o VLM se correspondem ao documento exigido e aponta se estão legíveis ou com data vencida.
3. `POST /api/triage/message`: Endpoint que recebe mensagens do usuário, mantém o contexto do diálogo, orienta sobre o ato e identifica intenções.
4. `POST /api/triage/upload-doc`: Recebe upload da imagem, dispara a validação e atualiza o checklist da sessão no banco.
5. `GET /api/triage/sessions`: Lista sessões ativas para o painel administrativo do escrevente.

---

## 5. REQUISITOS DO FRONTEND (ANGULAR)

### Estrutura de Diretórios:
```
frontend/
├── src/
│   ├── app/
│   │   ├── components/
│   │   │   ├── triage-inbox/
│   │   │   ├── customer-chat/
│   │   │   ├── checklist-inspector/
│   │   │   └── fee-summary-card/
│   │   ├── services/
│   │   │   └── triage.service.ts
│   │   └── models/
│   └── ...
```

### Telas e Comportamentos:
1. **Painel do Atendente (Inbox de Triagens):**
   - Lista de atendimentos com filtros por status e badges coloridos.
   - Indicador de completude (ex: "3 de 4 documentos validados").
2. **Visão Central (Dossiê do Atendimento):**
   - Histórico completo da conversa entre o cidadão e o bot.
   - Painel lateral com o checklist de documentos. Ao clicar em um documento enviado, abre lightbox com a imagem e o parecer da IA.
   - Card com a simulação de emolumentos detalhada.
   - Botão **"Transferir para Atendimento Humano"** (permite ao escrevente mandar mensagem diretamente no chat).
3. **Simulador / Widget Público do Cidadão:**
   - Interface minimalista e responsiva (mobile-first) simulando o atendimento webchat onde o usuário interage, responde às perguntas da IA e envia fotos dos documentos pela câmera ou galeria.

---

## 6. DIRETRIZES DE COMUNICAÇÃO E SEGURANÇA
- A IA conversacional deve manter linguagem simples, acolhedora e desprovida de jargões jurídicos excessivos com o público.
- Toda estimativa de custo deve conter o aviso padrão: *"Este valor é uma estimativa preliminar baseada nas informações prestadas. A conferência definitiva de valores ocorrerá na lavratura do ato."*
