# MVP — Confrontação de Matrículas e Memoriais Descritivos

Auditoria para Registro de Imóveis: lê a certidão de matrícula, o memorial descritivo e (opcionalmente)
o título/contrato — em **PDF, DOCX ou DOC** —; verifica continuidade dominial e ônus vigentes; reconstrói o perímetro, mede
fechamento e área e plota o imóvel no mapa.

## Rodando

```bash
cp backend/.env.example backend/.env   # preencha MONGO_URI e GEMINI_API_KEY (ou OPENAI_API_KEY)
npm run setup                          # 1ª vez: venv Python + dependências do Angular
npm run dev                            # API em :8010 (com --reload) + web em http://localhost:4210
npm test                               # 49 testes do backend (não chamam Gemini nem Atlas)
```

`npm run dev:api` / `npm run dev:web` sobem só um dos lados. A API usa a porta 8010 porque a 8000 já é
usada por outro serviço nesta máquina; o Angular repassa `/api` para ela (`frontend/proxy.conf.json`).
O npm 9 do sistema tem um bug de resolução de dependências, por isso o setup usa `npx npm@10` e há
`legacy-peer-deps=true` nos `.npmrc`.

Formatos aceitos: PDF (PyMuPDF; escaneado só com LLM), DOCX (python-docx, inclusive tabelas de vértices)
e DOC (convertido com LibreOffice headless — precisa de `soffice` instalado no servidor). O formato é
detectado pelo conteúdo do arquivo, não pela extensão.

Documentos fictícios para demonstração: `backend/test_samples/` (regenerar com
`python test_samples/generate_samples.py`).

## Comportamento sem configuração

| Item | Sem variável definida | Com variável |
|---|---|---|
| Banco | repositório em memória (perde dados ao reiniciar) | `MONGO_URI`/`MONGO_DB` (ou `MONGODB_*`) → Atlas, coleção `land_registry_analyses`, índice `2dsphere` em `geometry.location_geojson` |
| Extração | `heuristic`: regex para layout padronizado (só serve para os PDFs de exemplo) | `GEMINI_API_KEY` ou `OPENAI_API_KEY` → Structured Outputs (aceita PDF escaneado) |

### Gemini: cota e fallback

O plano gratuito do Gemini permite **20 requisições/dia por modelo**, e cada análise completa usa até 3
(matrícula, memorial, título). Por isso:

- `GEMINI_FALLBACK_MODELS` (separados por vírgula) são tentados em ordem quando o modelo principal
  responde 429/503 ou estoura o tempo limite (`LLM_TIMEOUT_S`, padrão 180 s).
- Um 429 de cota diária (que pede horas de espera) **não** é repetido: passa direto ao próximo modelo.
  Sobrecarga momentânea (503) é repetida com espera crescente.
- `GEMINI_THINKING_LEVEL=low` reduz a latência dos modelos Gemini 3.x.
- O modelo usado em cada extração aparece no log do backend (`Extração ... feita com ...`).

## Localização no mapa

| O que os documentos trazem | Resultado |
|---|---|
| Vértices com coordenadas (memorial **ou a própria matrícula**) | Polígono georreferenciado. Se o fuso UTM não vier no texto, é inferido pela localização do endereço; se o polígono ficar longe do endereço, alerta `COORDENADAS_LONGE_DO_ENDERECO` |
| Só azimutes/rumos e distâncias | O mapa abre no endereço aproximado e pede um clique no 1º vértice (`POST /api/parcels/{id}/anchor`). A posição fica marcada como **manual**, sem valor de georreferenciamento, e pode ser refeita |
| Nenhum vértice (descrição urbana por frente/fundos) | Pino com círculo de incerteza no endereço (precisão: endereço, rua, bairro ou cidade) |

A geocodificação usa o Nominatim público do OpenStreetMap (1 requisição/s, com cache). Envia apenas o
endereço do imóvel. Para desligar: `GEOCODING_ENABLED=false`; para volume maior: `NOMINATIM_URL` de uma
instância própria.

## API

- `POST /api/parcels/analyze` — multipart: `matricula` (obrigatório), `memorial`, `titulo`, `seller_name`
  (separar vários com `;`, prevalece sobre o título), `utm_zone`. Grava e retorna a análise completa.
- `POST /api/parcels/{id}/anchor` — `{"lat": .., "lon": ..}` do 1º vértice para perímetros sem coordenadas.
- `GET /api/parcels`, `GET /api/parcels/{id}`
- `POST /api/continuity/analyze`, `POST /api/geometry/analyze` — análises isoladas, sem gravar.

## Regras implementadas

- **Continuidade**: ordena os atos pelo número (R/AV compartilham a sequência); cada transmitente deve
  ser titular no ato de transmissão anterior; vendedor do título deve ser o titular atual
  (normaliza acentos e "Espólio de", com tolerância a pequenas grafias). Coproprietário ausente → ALERTA.
- **Ônus**: atos de ônus não cancelados por averbação posterior (`cancels_act_code`).
- **Geometria**: UTM SIRGAS 2000 (EPSG 31960+fuso; SAD-69/WGS84 também) → WGS84 via pyproj. Com
  azimute/rumo + distância calcula a poligonal e o erro de fechamento (perfeito < 2 cm, não fecha
  > 0,50 m). Área/perímetro com Shapely em metros. Divergência de área > 5% → alerta crítico.
  Distância declarada × coordenadas, polígono auto-intersectante e sobreposição com análises já
  gravadas (`$geoIntersects`) também geram alertas. Confrontantes com nº de matrícula são listados.
