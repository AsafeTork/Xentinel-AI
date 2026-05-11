# 🏆 Xentinel-AI Case Studies

## Case 01: Vazamento de Checkout (Gateway Timeout)

### 📈 Versão Comercial (Vendas / Pitch)
**Problema**: Instabilidade intermitente no gateway de pagamento em horários de pico.
**Impacto Estimado (Xentinel)**: **R$ 2.800 — R$ 3.400 / dia**.
**Ação**: Redução de timeout no frontend e injeção de redundância via Edge.
**Resultado Observado (Pós-Fix)**: Recuperação de **R$ 2.900 / dia** (Aumento de 87% nas transações mobile).
**Precisão da Estimativa**: Variância de ~12% (**Resultado consolidado dentro da faixa projetada**).
**ROI Final**: Recuperação total de **~R$ 87.000 / mês**.

---

### ⚙️ Versão Técnica (Debug / Engenharia)
**Finding**: `payment_gateway_timeout`
**Evidence**: `POST /api/v1/checkout/pay -> HTTP 504 (timeout after 5s)`
**Technical Analysis**:
- O frontend aguardava 10s pelo gateway, mas a latência da conexão mobile causava timeouts do navegador antes disso.
- O script de rastreio bloqueava a thread principal durante a falha.
**Fix Implemented**:
- Injeção de redundância via CDN (Edge).
- Redução do timeout para 3s com retry automático assíncrono.
**Validation**:
- Baseline: 72% de erro no POST payment.
- After-Fix: < 2% de erro.
