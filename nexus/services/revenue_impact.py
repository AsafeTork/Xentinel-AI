"""
Revenue Impact Engine — coração do produto.

Transforma findings técnicos em dinheiro real:
    finding → { revenue_at_risk_per_hour, conversion_loss_pct, affected_sessions, consequence_24h }

Fórmula:
    revenue_at_risk_per_hour = affected_sessions × conversion_rate × avg_order_value × conversion_loss_pct

Fallbacks quando o usuário não fornece dados:
    AOV default: R$ 120
    Conversion rate default: 2%
    Sessions/hour default: 200
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Benchmarks de mercado (fallback quando o lojista não fornece dados) ──────

DEFAULT_AOV = 120            # R$ — ticket médio e-commerce BR (Abcomm 2024)
DEFAULT_CONVERSION_RATE = 0.02   # 2%
DEFAULT_SESSIONS_PER_HOUR = 200  # ~4800/dia — loja média
DEFAULT_MONTHLY_REVENUE = DEFAULT_SESSIONS_PER_HOUR * 24 * 30 * DEFAULT_CONVERSION_RATE * DEFAULT_AOV  # ~R$ 414k


# ── Tabela de impacto por categoria de finding ─────────────────────────────

# Cada categoria tem:
#   conversion_loss_pct — % da conversão que pode cair
#   session_impact_pct  — % das sessões que são afetadas
#   confidence          — confiança nessa estimativa (0..1)
#   risk_of_action      — risco de aplicar a correção
#   blast_radius        — escopo de impacto da correção
#   reversibility       — facilidade de reverter
#   fix_effort_hours    — horas estimadas para implementar

CATEGORY_IMPACT: Dict[str, Dict] = {
    "checkout": {
        "conversion_loss_pct": 0.70,
        "session_impact_pct": 0.80,
        "confidence": 0.92,
        "risk_of_action": "low",
        "blast_radius": "checkout_only",
        "reversibility": "instant_rollback",
        "fix_effort_hours": 2,
        "narrative": "Checkout pode travar e perder pedidos no momento do pagamento.",
        "consequence": "Se não corrigido, cada hora pode custar {loss_per_hour} em pedidos perdidos.",
    },
    "ssl_headers": {
        "conversion_loss_pct": 0.08,
        "session_impact_pct": 1.0,
        "confidence": 0.87,
        "risk_of_action": "low",
        "blast_radius": "site_wide",
        "reversibility": "instant_rollback",
        "fix_effort_hours": 0.5,
        "narrative": "Sinal de segurança fraco pode derrubar confiança antes do pagamento.",
        "consequence": "Se não corrigido, visitantes podem abandonar por desconfiança — até {loss_24h} nas próximas 24h.",
    },
    "session_auth": {
        "conversion_loss_pct": 0.50,
        "session_impact_pct": 1.0,
        "confidence": 0.85,
        "risk_of_action": "medium",
        "blast_radius": "logged_users",
        "reversibility": "config_change",
        "fix_effort_hours": 3,
        "narrative": "Sessão da compra pode quebrar e interromper o carrinho.",
        "consequence": "Se não corrigido, carrinhos podem ser perdidos — até {loss_24h} nas próximas 24h.",
    },
    "performance": {
        "conversion_loss_pct": 0.07,
        "session_impact_pct": 1.0,
        "confidence": 0.78,
        "risk_of_action": "low",
        "blast_radius": "all_pages",
        "reversibility": "instant_rollback",
        "fix_effort_hours": 4,
        "narrative": "Lentidão pode reduzir adição ao carrinho e conversão.",
        "consequence": "Se não corrigido, cada segundo a mais reduz conversão em 7% — até {loss_24h} nas próximas 24h.",
    },
    "forms_input": {
        "conversion_loss_pct": 0.12,
        "session_impact_pct": 0.30,
        "confidence": 0.80,
        "risk_of_action": "low",
        "blast_radius": "forms_only",
        "reversibility": "instant_rollback",
        "fix_effort_hours": 2,
        "narrative": "Formulários inseguros podem prejudicar conversão e confiança.",
        "consequence": "Se não corrigido, formulários podem ser explorados — até {loss_24h} nas próximas 24h.",
    },
    "redirect_exposure": {
        "conversion_loss_pct": 0.05,
        "session_impact_pct": 0.25,
        "confidence": 0.75,
        "risk_of_action": "low",
        "blast_radius": "specific_paths",
        "reversibility": "instant_rollback",
        "fix_effort_hours": 1,
        "narrative": "Caminhos expostos podem tirar clientes do fluxo de compra.",
        "consequence": "Se não corrigido, visitantes podem ser redirecionados para fora — até {loss_24h} nas próximas 24h.",
    },
    "dependency": {
        "conversion_loss_pct": 0.03,
        "session_impact_pct": 0.15,
        "confidence": 0.65,
        "risk_of_action": "medium",
        "blast_radius": "backend",
        "reversibility": "deploy_required",
        "fix_effort_hours": 4,
        "narrative": "Componente desatualizado pode criar risco operacional silencioso.",
        "consequence": "Se não corrigido, vulnerabilidade conhecida pode ser explorada — risco acumulado de {loss_24h} em 24h.",
    },
    "generic": {
        "conversion_loss_pct": 0.02,
        "session_impact_pct": 0.10,
        "confidence": 0.55,
        "risk_of_action": "low",
        "blast_radius": "unknown",
        "reversibility": "case_dependent",
        "fix_effort_hours": 3,
        "narrative": "Ponto detectado pode corroer conversão e confiança ao longo do tempo.",
        "consequence": "Se não corrigido, impacto pode se acumular — até {loss_24h} nas próximas 24h.",
    },
}


@dataclass
class ShopContext:
    """Dados financeiros da loja. Usados para calcular impacto real.
    Se o lojista não fornecer, usamos benchmarks de mercado."""
    avg_order_value: float = DEFAULT_AOV
    conversion_rate: float = DEFAULT_CONVERSION_RATE
    sessions_per_hour: float = DEFAULT_SESSIONS_PER_HOUR
    monthly_revenue: float = 0.0  # calculado

    def __post_init__(self):
        self.avg_order_value = max(1.0, min(10000.0, float(self.avg_order_value or DEFAULT_AOV)))
        self.conversion_rate = max(0.0001, min(0.5, float(self.conversion_rate or DEFAULT_CONVERSION_RATE)))
        self.sessions_per_hour = max(1.0, min(100000.0, float(self.sessions_per_hour or DEFAULT_SESSIONS_PER_HOUR)))
        if not self.monthly_revenue or self.monthly_revenue <= 0:
            self.monthly_revenue = self.sessions_per_hour * 24 * 30 * self.conversion_rate * self.avg_order_value


@dataclass
class RevenueImpact:
    """Resultado do cálculo de impacto financeiro de um finding."""
    category: str = ""
    affected_sessions: int = 0
    conversion_rate: float = 0.0
    avg_order_value: float = 0.0
    conversion_loss_pct: float = 0.0

    revenue_at_risk_per_hour: float = 0.0
    revenue_at_risk_24h: float = 0.0
    revenue_at_risk_monthly: float = 0.0

    confidence: float = 0.0
    risk_of_action: str = "low"
    blast_radius: str = "unknown"
    reversibility: str = "case_dependent"
    fix_effort_hours: float = 3.0

    # Prioridade = dinheiro / esforço
    roi_score: float = 0.0
    
    # Priority Score = 70% Peso Financeiro Absoluto + 30% ROI (Facilidade)
    priority_score: float = 0.0

    # Narrativa para UI (sem jargão)
    narrative: str = ""
    consequence_24h: str = ""

    # Recuperação estimada
    recovery_label: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "affected_sessions": self.affected_sessions,
            "conversion_rate": round(self.conversion_rate, 4),
            "avg_order_value": round(self.avg_order_value, 2),
            "conversion_loss_pct": round(self.conversion_loss_pct, 4),
            "revenue_at_risk_per_hour": round(self.revenue_at_risk_per_hour, 2),
            "revenue_at_risk_24h": round(self.revenue_at_risk_24h, 2),
            "revenue_at_risk_monthly": round(self.revenue_at_risk_monthly, 2),
            "confidence": round(self.confidence, 3),
            "risk_of_action": self.risk_of_action,
            "blast_radius": self.blast_radius,
            "reversibility": self.reversibility,
            "fix_effort_hours": self.fix_effort_hours,
            "roi_score": round(self.roi_score, 2),
            "priority_score": round(self.priority_score, 2),
            "narrative": self.narrative,
            "consequence_24h": self.consequence_24h,
            "recovery_label": self.recovery_label,
        }


def _format_brl(value: float) -> str:
    v = int(max(0, round(value)))
    text = f"{v:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def classify_finding_category(finding_key: str, category: str = "", failure: str = "", solution: str = "") -> str:
    """Classifica um finding em uma categoria de impacto financeiro."""
    text = " ".join([finding_key or "", category or "", failure or "", solution or ""]).lower()

    if any(k in text for k in ("checkout", "payment", "gateway", "cart", "pedido", "compra")):
        return "checkout"
    if any(k in text for k in ("ssl", "tls", "https", "certificate", "hsts", "csp", "header", "referrer-policy")):
        return "ssl_headers"
    if any(k in text for k in ("cookie", "session", "login", "auth", "jwt", "token")):
        return "session_auth"
    if any(k in text for k in ("performance", "speed", "core web", "cls", "lcp", "fcp", "ttfb", "render", "blocking")):
        return "performance"
    if any(k in text for k in ("form", "input", "xss", "script", "csrf")):
        return "forms_input"
    if any(k in text for k in ("redirect", "exposed", "exposure", "public", "admin", "panel")):
        return "redirect_exposure"
    if any(k in text for k in ("dependency", "package", "library", "version", "outdated", "vulnerable")):
        return "dependency"
    return "generic"


def calculate_revenue_impact(
    finding_key: str,
    *,
    category: str = "",
    failure: str = "",
    solution: str = "",
    severity_level: str = "MEDIUM",
    shop: ShopContext | None = None,
) -> RevenueImpact:
    """
    Calcula impacto financeiro de um finding.

    Fórmula:
        revenue_at_risk_per_hour = affected_sessions × conversion_rate × AOV × conversion_loss_pct
        prioridade (ROI) = revenue_at_risk_monthly / fix_effort_hours
    """
    if shop is None:
        shop = ShopContext()

    impact_category = classify_finding_category(finding_key, category, failure, solution)
    impact_data = CATEGORY_IMPACT.get(impact_category, CATEGORY_IMPACT["generic"])

    # Severity multiplier: CRITICAL usa 100% do impacto, LOW usa 25%
    severity_mult = {"CRITICAL": 1.0, "HIGH": 0.8, "MEDIUM": 0.5, "LOW": 0.25}.get(
        str(severity_level or "MEDIUM").upper(), 0.5
    )

    conversion_loss_pct = impact_data["conversion_loss_pct"] * severity_mult
    session_impact_pct = impact_data["session_impact_pct"]
    affected_sessions = int(round(shop.sessions_per_hour * session_impact_pct))

    base_confidence = impact_data.get("confidence", 0.55)
    
    # Fórmula core: sessões × taxa de conversão × ticket médio × % perda × % confiança
    # A confiança garante que previsões de risco não inflem caso o modelo esteja incerto
    loss_per_hour = affected_sessions * shop.conversion_rate * shop.avg_order_value * conversion_loss_pct * base_confidence
    loss_24h = loss_per_hour * 24
    loss_monthly = loss_per_hour * 24 * 30

    fix_hours = float(impact_data.get("fix_effort_hours", 3))
    roi = loss_monthly / max(0.5, fix_hours)
    
    # Prevenção contra distorção de ROI (Bugs pequenos sobrepondo os críticos)
    # 70% do score vem do volume absoluto de dinheiro, 30% da facilidade (ROI)
    priority_score = (loss_monthly * 0.70) + (roi * 0.30)

    # Narrativa
    narrative = impact_data.get("narrative", "")
    consequence_tpl = impact_data.get("consequence", "")
    consequence = consequence_tpl.format(
        loss_per_hour=_format_brl(loss_per_hour),
        loss_24h=_format_brl(loss_24h),
    ) if consequence_tpl else ""

    # Recovery label
    if loss_monthly > 0:
        recovery_label = f"Corrigir pode recuperar até {_format_brl(loss_monthly)}/mês"
    else:
        recovery_label = "Impacto baixo no momento"

    return RevenueImpact(
        category=impact_category,
        affected_sessions=affected_sessions,
        conversion_rate=shop.conversion_rate,
        avg_order_value=shop.avg_order_value,
        conversion_loss_pct=conversion_loss_pct,
        revenue_at_risk_per_hour=loss_per_hour,
        revenue_at_risk_24h=loss_24h,
        revenue_at_risk_monthly=loss_monthly,
        confidence=impact_data.get("confidence", 0.55),
        risk_of_action=impact_data.get("risk_of_action", "low"),
        blast_radius=impact_data.get("blast_radius", "unknown"),
        reversibility=impact_data.get("reversibility", "case_dependent"),
        fix_effort_hours=fix_hours,
        roi_score=roi,
        priority_score=priority_score,
        narrative=narrative,
        consequence_24h=consequence,
        recovery_label=recovery_label,
    )


def calculate_global_score(impacts: List[RevenueImpact]) -> dict:
    """
    Score global do negócio — responde: "Quanto estou perdendo por dia?"

    Retorna:
        total_loss_per_hour, total_loss_24h, total_loss_monthly
        headline: "Você pode estar perdendo até R$ X/dia"
        consequence: "Se não corrigir nada, são R$ Y em 30 dias"
        recovery_potential: "Corrigindo os 3 primeiros, recupera R$ Z/mês"
    """
    if not impacts:
        return {
            "total_loss_per_hour": 0,
            "total_loss_24h": 0,
            "total_loss_monthly": 0,
            "headline": "Conecte sua loja para medir perda de receita.",
            "consequence": "",
            "recovery_potential": "",
            "top3_recovery": 0,
        }

    total_hour = sum(i.revenue_at_risk_per_hour for i in impacts)
    total_24h = sum(i.revenue_at_risk_24h for i in impacts)
    total_monthly = sum(i.revenue_at_risk_monthly for i in impacts)

    # Top 3 by ROI (corrigir primeiro, ganhar mais rápido)
    sorted_by_roi = sorted(impacts, key=lambda i: i.roi_score, reverse=True)
    top3_monthly = sum(i.revenue_at_risk_monthly for i in sorted_by_roi[:3])

    # Headlines para UI
    daily_loss = total_24h
    if daily_loss >= 5000:
        headline = f"Sua loja pode estar perdendo até {_format_brl(daily_loss)}/dia"
    elif daily_loss >= 500:
        headline = f"Sua loja pode estar perdendo até {_format_brl(daily_loss)}/dia"
    elif daily_loss > 0:
        headline = f"Risco baixo detectado — até {_format_brl(daily_loss)}/dia"
    else:
        headline = "Receita protegida no momento."

    consequence = ""
    if total_monthly > 0:
        consequence = f"Se não corrigir nada, isso pode custar até {_format_brl(total_monthly)} nos próximos 30 dias."

    recovery = ""
    if top3_monthly > 0:
        recovery = f"Corrigindo os 3 pontos mais críticos, você pode recuperar até {_format_brl(top3_monthly)}/mês."

    return {
        "total_loss_per_hour": round(total_hour, 2),
        "total_loss_24h": round(total_24h, 2),
        "total_loss_monthly": round(total_monthly, 2),
        "headline": headline,
        "consequence": consequence,
        "recovery_potential": recovery,
        "top3_recovery": round(top3_monthly, 2),
    }
