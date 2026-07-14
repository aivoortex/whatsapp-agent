# WhatsApp Agent Core

Núcleo multiempresa para transformar um chatbot de WhatsApp em um agente modular. O projeto inclui onboarding, pacotes de nicho, base de conhecimento alimentada pelo website, recuperação de contexto, API de mensagens e transferência para atendimento humano.

> Este repositório não envia mensagens diretamente ao WhatsApp. Ele expõe um adaptador HTTP estável para ser conectado ao webhook/API oficial que seu chatbot já utiliza.

## Recursos do MVP

- isolamento lógico por cliente (`tenant_id`);
- onboarding web e por API;
- pacotes de nicho configuráveis em JSON;
- importação controlada de páginas do website;
- bloqueio básico de SSRF e limite de páginas/tamanho;
- respostas com contexto recuperado e fontes;
- integração opcional com OpenAI;
- fallback seguro quando não há modelo configurado;
- regras de transferência humana;
- SQLite para desenvolvimento, com interfaces simples de substituir;
- Docker, testes e documentação automática em `/docs`.

## Executar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --reload
```

Abra `http://localhost:8000` para o onboarding e `http://localhost:8000/docs` para a API.

Para respostas geradas por IA, preencha `OPENAI_API_KEY` e, se necessário, altere `OPENAI_MODEL`. Sem a chave, o agente devolve os trechos mais relevantes encontrados no site e sinaliza quando precisa de atendimento humano.

## Fluxo de integração com o chatbot existente

1. O webhook atual recebe uma mensagem do WhatsApp.
2. Seu chatbot chama `POST /v1/tenants/{tenant_id}/messages`.
3. O núcleo consulta as regras e a base do cliente.
4. A resposta retorna em `reply`, junto com `sources` e `handoff_required`.
5. O chatbot envia a resposta ou abre o atendimento humano.

Exemplo:

```bash
curl -X POST http://localhost:8000/v1/tenants/acme/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"Qual é o horário de atendimento?","contact_id":"5511999999999"}'
```

## Criar um pacote de nicho

Copie `niches/general.json` para `niches/<nome>.json`. Um pacote define personalidade, objetivos, ações permitidas, termos de transferência e perguntas adicionais de onboarding. Reinicie a aplicação para carregar alterações.

## Endpoints principais

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `/health` | Saúde da aplicação |
| `GET` | `/v1/niches` | Nichos disponíveis |
| `POST` | `/v1/tenants` | Cria/configura cliente |
| `GET` | `/v1/tenants/{id}` | Consulta configuração |
| `POST` | `/v1/tenants/{id}/knowledge/sync` | Sincroniza website |
| `GET` | `/v1/tenants/{id}/knowledge` | Lista páginas importadas |
| `POST` | `/v1/tenants/{id}/messages` | Processa mensagem |

## Limites intencionais do MVP

- autenticação do painel e criptografia de segredos devem ser adicionadas antes de produção;
- filas de trabalho são recomendadas para sites grandes;
- conversas não alteram automaticamente a base de conhecimento;
- ações como agenda, CRM e pagamento devem entrar como ferramentas explícitas e autorizadas;
- revise requisitos de privacidade e retenção aplicáveis ao país e ao negócio.

## Testes

```bash
pytest
```

## Licença

MIT
