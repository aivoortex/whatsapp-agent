# WhatsApp Agent Core

Núcleo modular e multiempresa para transformar um chatbot de WhatsApp em um agente de atendimento, vendas e suporte. A versão 0.2 combina conversação natural, conhecimento aprovado, memória controlada, qualificação progressiva e transferência humana com contexto.

> O núcleo expõe uma API HTTP para ser conectada ao webhook/API oficial que seu chatbot já utiliza. Ele não envia mensagens ao WhatsApp diretamente.

## Diferenciais da versão 0.2

- detecção de intenção, idioma e sentimento;
- respostas naturais: responde primeiro e faz no máximo uma pergunta por vez;
- RAG com normalização de acentos, relevância, confiança, fontes e melhores trechos;
- memória progressiva do contato sem treinar o modelo com conversas;
- qualificação configurável de leads;
- handoff com resumo, perfil e transcrição recente;
- ações sugeridas com confirmação para agenda, pedido e CRM;
- idempotência por `message_id`, essencial para webhooks;
- feedback, taxa de resolução, handoff rate e intenções mais frequentes;
- entrada preparada para texto, imagem, áudio, vídeo e documento;
- isolamento lógico por `tenant_id` e autenticação opcional por API key;
- fallback seguro quando o provedor de IA estiver indisponível;
- pacotes de nicho plugáveis;
- bloqueio de SSRF e limites na importação de websites.

## Executar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env
python -m uvicorn app.main:app --reload
```

Abra `http://localhost:8000` para o onboarding e `http://localhost:8000/docs` para a documentação interativa.

Configure `OPENAI_API_KEY` para habilitar geração natural e extração estruturada. Sem essa chave, o núcleo usa recuperação determinística e encaminha quando a confiança é baixa. Em produção, configure `APP_API_KEY` e envie o header `X-API-Key`.

## Fluxo de uma mensagem

1. O webhook recebe a mensagem do WhatsApp.
2. Seu adaptador chama `POST /v1/tenants/{tenant_id}/messages`.
3. O núcleo verifica duplicidade, recupera perfil, histórico e conhecimento.
4. O agente detecta intenção, responde, captura dados e sugere ações autorizadas.
5. O webhook envia `reply` ou abre um handoff usando o contexto retornado pela API.

```bash
curl -X POST http://localhost:8000/v1/tenants/acme/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: troque-esta-chave" \
  -d '{
    "message_id":"wamid.123",
    "contact_id":"5511999999999",
    "text":"Quero saber o preço e agendar uma demonstração"
  }'
```

Resposta resumida:

```json
{
  "reply": "Claro — posso ajudar com isso. Qual horário funciona melhor para você?",
  "intent": "scheduling",
  "confidence": 0.86,
  "sources": [],
  "captured_fields": {},
  "missing_fields": [],
  "suggested_actions": [
    {"type": "book_appointment", "label": "Consultar agenda", "requires_confirmation": true, "payload": {}}
  ],
  "handoff_required": false,
  "trace_id": "..."
}
```

O núcleo não afirma que uma ação foi executada. O conector deve processar `suggested_actions`, validar permissões e devolver o resultado ao fluxo.

## Qualificação progressiva

Configure os campos no onboarding/API. O agente não repete perguntas de dados já conhecidos.

```json
{
  "lead_qualification_fields": [
    {"name":"name", "label":"Nome", "question":"Como você gostaria de ser chamado?"},
    {"name":"email", "label":"E-mail", "question":"Qual é o melhor e-mail para contato?"}
  ]
}
```

## Endpoints principais

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `/health` | Saúde e versão |
| `POST` | `/v1/tenants` | Onboarding/configuração |
| `POST` | `/v1/tenants/{id}/knowledge/sync` | Sincronização do website |
| `POST` | `/v1/tenants/{id}/messages` | Processamento de mensagem |
| `GET` | `/v1/tenants/{id}/contacts/{contact}` | Perfil e histórico recente |
| `GET` | `/v1/tenants/{id}/handoffs/{contact}` | Pacote de transferência humana |
| `POST` | `/v1/tenants/{id}/messages/{trace}/feedback` | Feedback/CSAT |
| `GET` | `/v1/tenants/{id}/analytics` | Indicadores operacionais |

## Pacotes de nicho

Copie `niches/general.json` para `niches/<nome>.json`. Cada pacote define instruções, ações permitidas, termos de transferência e perguntas especializadas. Os pacotes iniciais são `general`, `clinica` e `imobiliaria`.

## Limites antes de produção

- substitua SQLite por PostgreSQL em múltiplas instâncias;
- execute sincronizações grandes em uma fila de trabalhos;
- implemente adaptadores explícitos para CRM, agenda, pedidos e pagamentos;
- processe áudio/imagem com um serviço multimodal antes de enviar o texto ao núcleo;
- adicione política de retenção, criptografia de campos sensíveis e RBAC no painel;
- mantenha opt-in, templates e janela de atendimento em conformidade com as regras do WhatsApp.

## Testes

```bash
python -m pytest
```

## Licença

MIT
