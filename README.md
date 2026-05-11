# Xentinel AI

**Revenue Protection System para e-commerce.**

O produto foi reposicionado para responder três perguntas:
- sua loja está perdendo vendas agora?
- quanto isso pode custar?
- o que corrigir primeiro para proteger checkout, conversão, confiança e receita?

Hoje a base já entrega:
- dashboard comercial orientado a perda de vendas
- priorização automática por impacto financeiro
- demo state convincente para e-commerce
- motor de impacto de receita (`revenue_impact.py`)
- auditorias, filas, histórico e monitoramento contínuo
- worker assíncrono com Redis + RQ
- integração com LLM via gateway OpenAI-compatible
- billing via Stripe

## Posicionamento

**Plataforma que mostra onde seu e-commerce pode estar perdendo dinheiro e o que corrigir primeiro para recuperar vendas.**

## Rodar local
1) Copie `.env.example` para `.env` e preencha as chaves
2) Suba:
```bash
docker compose up --build
```
3) Migrações:
```bash
docker compose exec web flask db upgrade
```
4) Abra:
`http://localhost:8000`


> Dica: se o comando `flask` não reconhecer o app, rode com:
> `docker compose exec -e FLASK_APP=app.py web flask db upgrade`

## Deploy
### Opção A (recomendada): Railway/Render
- Postgres gerenciado
- Redis gerenciado
- Deploy do web + worker

#### Render (passo a passo)
1) Crie um Postgres e um Redis no Render
2) Crie um novo “Blueprint” apontando para este repositório e o arquivo `render.yaml`
3) Configure env vars (Render → Environment):
   - `DATABASE_URL` (Postgres)
   - `REDIS_URL` (Redis)
   - `SECRET_KEY`
   - `LLM_BASE_URL_V1`, `LLM_API_KEY`, `LLM_DEFAULT_MODEL`
   - Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`
   - OAuth (opcional):
     - Google: `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`
     - GitHub: `OAUTH_GITHUB_CLIENT_ID`, `OAUTH_GITHUB_CLIENT_SECRET`
4) Rode as migrações uma vez (Render Shell):
   - `FLASK_APP=app.py flask db upgrade`
5) Abra o Web URL e crie sua conta (Register).

## OAuth Google (login com Google)
1) Google Cloud Console → APIs & Services → Credentials → Create Credentials → OAuth client ID → **Web application**
2) Authorized redirect URI:
   - `https://SEU_DOMINIO/oauth/google/callback`
   - (local) `http://localhost:8000/oauth/google/callback`
3) Copie o **Client ID** e o **Client secret** para as env vars:
   - `OAUTH_GOOGLE_CLIENT_ID`
   - `OAUTH_GOOGLE_CLIENT_SECRET`

> Segurança: nunca commite secrets no Git. Configure `OAUTH_*_CLIENT_SECRET` somente no Render/host (Environment) ou no seu `.env` local (que deve estar no `.gitignore`).

## Continuous monitoring (cron)

O sistema suporta monitoramento contínuo via um scheduler simples acionado por cron:

1) Defina `MONITOR_TICK_TOKEN` (string aleatória) no Render (Web Service).
2) Crie um Render Cron Job (a cada 1 minuto) chamando:

```
POST https://SEU_DOMINIO/admin/monitor/tick?token=SEU_TOKEN
```

3) Configure os targets em Admin → Monitoring (frequência + modo).

Notas:
- O tick é “at-least-once”: ao enfileirar ele já avança o `next_run_utc`.
- Para escalar, aumente réplicas do worker; a fila é centralizada no Redis.

## Safety & policy engine (actions gate)

Mesmo antes de executar ações automaticamente, toda ação sugerida passa por um **Safety Gate** determinístico, baseado na policy do target.

Defaults (env vars):
- `POLICY_DEFAULT_MAX_RISK_LEVEL=HIGH`
- `POLICY_DEFAULT_MAX_RATE_RPS=20`

Regras hard:
- CSP deve começar em **Report-Only** (staged rollout).
- Rate limits são **capados** por policy.
- Ações sem rollback são **bloqueadas**.

### Opção B: VPS Ubuntu (controle total)
- Use `docker compose`
- Nginx como reverse proxy (TLS via LetsEncrypt)

## Teste completo
- Testes automatizados com `pytest` (ver pasta `tests/`)
- Smoke test manual:
  1) Criar conta
  2) Adicionar site
  3) Iniciar auditoria
  4) Ver streaming + download .md/.csv
  5) Abrir o **Dossiê** (print-ready) para enviar ao cliente

## Notas sobre “outros provedores”
O sistema usa **OpenAI-compatible**:
- `POST /v1/chat/completions`
- opcional: `GET /v1/models`

Se o provedor não tiver `/models`, use um proxy como **LiteLLM** e aponte o Base URL para o proxy:
`http://127.0.0.1:4000/v1`

## Como colocar no mercado
1) **Domínio**: compre um domínio e aponte para o Render/VPS
2) **Posicionamento**: venda como proteção de receita para e-commerce, não como scanner técnico
3) **Stripe**:
   - crie um Product + Price mensal
   - copie o `price_id` para `STRIPE_PRICE_ID`
   - configure o webhook apontando para `/billing/webhook`
4) **Onboarding**:
   - cadastre uma loja demo
   - deixe o demo state ativo para primeira impressão forte
   - mostre o fluxo: loja em risco → dinheiro em risco → correção prioritária
