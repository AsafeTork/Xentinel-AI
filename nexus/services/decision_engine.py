from __future__ import annotations

import json
from typing import Dict, List

from .action_engine import generate_action_block
from .finding_types import Finding
from .revenue_impact import calculate_revenue_impact, ShopContext, RevenueImpact


def parse_csv_findings(csv_text: str) -> List[Finding]:
    findings: List[Finding] = []
    if not csv_text:
        return findings
    for ln in csv_text.splitlines():
        row = (ln or "").strip()
        if not row:
            continue
        if row.lower().startswith("categoria;"):
            continue
        parts = [p.strip() for p in row.split(";")]
        if len(parts) < 2:
            continue
            
        # Suporte a 8 colunas (v1) e 9 colunas (Fase 2.5)
        if len(parts) >= 9:
            # Novo formato: Categoria;Technical_Type;Título;Prova;Explicação;Mecanismo;Solução;Prioridade;Complexidade
            cat, ttype, title, proof, expl, loss, sol, prio, compl = parts[:9]
        else:
            # Formato antigo: Categoria;Título;Prova;Explicação;Mecanismo;Solução;Prioridade;Complexidade
            while len(parts) < 8:
                parts.append("")
            cat, title, proof, expl, loss, sol, prio, compl = parts[:8]
            ttype = "legacy_finding"

        # Key única baseada no tipo técnico para estabilidade
        key = (cat.lower() + "|" + ttype.lower()).strip()
        if ttype == "legacy_finding":
            key = (cat.lower() + "|" + title.lower()).strip()

        findings.append(
            Finding(
                key=key,
                category=cat,
                technical_type=ttype,
                failure=title,  # O título comercial do prompt agora entra como 'failure'
                proof=proof,
                explanation=expl,
                loss=loss,
                solution=sol,
                priority=prio,
                complexity=compl,
            )
        )
    return findings


def _priority_severity(priority: str) -> int:
    p = (priority or "").strip().lower()
    if p in ("crítica", "critica", "critical"):
        return 95
    if p in ("alta", "high"):
        return 80
    if p in ("média", "media", "medium"):
        return 55
    if p in ("baixa", "low"):
        return 30
    return 45


def score_finding(f: Finding, *, recurrence_count: int = 1, shop: ShopContext | None = None) -> Dict:
    severity = _priority_severity(f.priority)
    
    # Calculate real revenue impact (Passando technical_type da Fase 2.5)
    impact: RevenueImpact = calculate_revenue_impact(
        f.key,
        category=f.category,
        failure=f.failure,
        solution=f.solution,
        severity_level=f.priority,
        shop=shop,
        technical_type=f.technical_type,
    )
    
    # Action recommendation
    rec = (f.solution or "").strip()
    if not rec:
        cat = (f.category or "").lower()
        if "headers" in cat or "infra" in cat:
            rec = "Ative a proteção na borda (CDN/Proxy) para proteger vendas."
        else:
            rec = "Corrija este ponto para blindar o fluxo de checkout e cadastro."

    evidence = (f.proof or "").strip()
    if evidence:
        rec = rec + " Evidência técnica: " + evidence[:220]

    loss_24h = float(getattr(impact, "revenue_at_risk_24h", 0) or 0)
    if loss_24h >= 2500:
        urgency = "Agir agora"
    elif loss_24h >= 800:
        urgency = "Próximas 24h"
    elif loss_24h > 0:
        urgency = "Esta semana"
    else:
        urgency = "Monitorar"

    # Encapsulamento de 3 Camadas (Fase 2.5)
    # 🔒 technical: sinal técnico puro e debug
    # 💰 business: narrativa WOW e impacto financeiro
    # 🧠 explanation: detalhamento do mecanismo de falha
    
    technical = {
        "type": f.technical_type,
        "category": f.category,
        "raw_evidence": f.proof,
    }
    
    business = {
        "title": f.failure, # O Título ⚠️ Antes/Depois do LLM
        "impact": f.explanation[:160], # Resumo do impacto no cliente
        "money_loss": f"R$ {int(impact.revenue_at_risk_24h):,.0f}".replace(",", "."),
        "urgency": urgency,
    }
    
    explanation = {
        "what_is_happening": f.explanation,
        "why_it_matters": f.loss,
        "solution": rec,
    }

    return {
        "key": f.key,
        "category": f.category,
        "technical": technical,
        "business": business,
        "explanation": explanation,
        "priority_raw": f.priority,
        "complexity": f.complexity,
        "severity_base": severity,
        "recurrence_count": int(recurrence_count or 1),
        "score": 0, # Computed in build_decision_report
        "level": "MEDIUM", # Computed in build_decision_report
        "recommendation": rec,
        "impact_data": impact, # Mantemos como OBJETO para processamento no loop posterior
    }


def build_decision_report(
    findings: List[Finding],
    *,
    recurrence_map: Dict[str, int],
    learning_map: Dict[str, dict] | None = None,
    policy=None,
    safety_gate_fn=None,
    context: dict | None = None,
    top_n: int = 3,
    shop: ShopContext | None = None,
) -> Dict:
    top_n = max(1, min(10, int(top_n or 3)))
    learning_map = learning_map or {}
    items = []
    
    for f in findings:
        it = score_finding(f, recurrence_count=int(recurrence_map.get(f.key, 1)), shop=shop)
        hist = learning_map.get(f.key) or {}
        
        impact: RevenueImpact = it["impact_data"]
        
        # O score agora não é o severity técnico, mas o ROI (Impacto Financeiro / Esforço)
        base_score = min(100, max(0, int(impact.roi_score / 100.0))) 
        if base_score < 10 and impact.revenue_at_risk_24h > 0:
            base_score = 30 # mínimo se perde dinheiro
            
        # Nível financeiro (não mais tech severity)
        loss_24h = impact.revenue_at_risk_24h
        if loss_24h >= 2500:
            level = "CRITICAL"
            base_score = max(base_score, 85)
        elif loss_24h >= 800:
            level = "HIGH"
            base_score = max(base_score, 70)
        elif loss_24h > 0:
            level = "MEDIUM"
            base_score = max(base_score, 45)
        else:
            level = "LOW"
            base_score = max(base_score, 10)
            
        # Confiança agora une o modelo de ML com dados históricos
        model_confidence = impact.confidence
        sr = float(hist.get("success_rate") or 0.0)
        sample = int(hist.get("sample_size") or 0)
        if sample > 0:
            shrink = min(1.0, sample / 10.0)
            confidence = (shrink * sr) + ((1.0 - shrink) * model_confidence)
        else:
            confidence = model_confidence
            
        confidence = max(0.0, min(1.0, confidence))

        it["confidence"] = round(confidence, 3)
        it["score"] = base_score
        it["level"] = level
        it["historical_effectiveness"] = {
            "success_rate": round(sr, 4),
            "sample_size": sample,
        }

        # Logging para Validação do WOW Moment (Em modo Debug)
        import logging
        import json
        log = logging.getLogger("DecisionEngine")
        log.debug(json.dumps({
            "event": "financial_impact_calculated",
            "finding_id": str(f.id)[:8] if hasattr(f, "id") else "unknown",
            "finding_key": f.key,
            "level": level,
            "revenue_at_risk_24h": impact.revenue_at_risk_24h,
            "revenue_at_risk_monthly": impact.revenue_at_risk_monthly,
            "roi_score": impact.roi_score,
            "inputs": {
                "sessions_per_hour": impact.affected_sessions, # Usando sessões afetadas
                "conversion_rate": impact.conversion_rate,
                "aov": impact.avg_order_value
            }
        }))

        # Block de ação (MOCK EXECUTE e Agent Loop)
        try:
            ab = generate_action_block(f)
            if "agent_loop" in ab:
                ab["agent_loop"]["baseline_impact"] = f"Risco de perder {_format_brl(impact.revenue_at_risk_24h)} nas próximas 24h caso a falha persista."
                ab["agent_loop"]["after_impact"] = f"Ação recomendada retém {_format_brl(impact.revenue_at_risk_monthly)} de faturamento mensal."
            it["action"] = ab
        except Exception:
            it["action"] = {
                "classification": "MANUAL_REQUIRED",
                "title": "Correção manual necessária",
                "steps": ["Aplique correção na base e valide o checkout."],
            }

        # Safety Gate
        try:
            if safety_gate_fn and policy:
                gr = safety_gate_fn(
                    action_block=it.get("action") or {},
                    finding_level=str(it.get("level") or ""),
                    policy=policy,
                    context=context or {},
                )
                it["safety_gate"] = {"status": gr.status, "reasons": gr.reasons}
                it["action"] = gr.action
            else:
                it["safety_gate"] = {"status": "REQUIRES_CONFIRMATION", "reasons": ["Aprovação manual requerida por segurança."]}
        except Exception:
            it["safety_gate"] = {"status": "REQUIRES_CONFIRMATION", "reasons": ["Erro no safety gate."]}

        # Ecommerce View format (para consumo no frontend)
        def _format_brl(val: float) -> str:
            v = int(max(0, round(val)))
            return f"R$ {v:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")

        urgency_map = {"CRITICAL": "Agir agora", "HIGH": "Próximas 24h", "MEDIUM": "Esta semana", "LOW": "Monitorar"}
        urgency = urgency_map.get(level, "Monitorar")

        it["ecommerce"] = {
            "severidade_financeira": f"Impacto {level}",
            "severidade_financeira_curta": "Receita em risco" if level in ("CRITICAL", "HIGH") else "Vendas em atenção",
            "resumo_financeiro": impact.consequence_24h,
            "problema": impact.narrative or (f.failure[:110]),
            "impacto": f"Pode custar até {_format_brl(impact.revenue_at_risk_24h)} nas próximas 24h.",
            "dinheiro_em_risco": _format_brl(impact.revenue_at_risk_per_hour) + "/hora",
            "urgencia": urgency,
            "acao_recomendada": it["recommendation"],
            "confianca": it["confidence"],
            "risk_of_action": impact.risk_of_action,
            "blast_radius": impact.blast_radius,
            "reversibility": impact.reversibility,
        }

        items.append(it)

    # Ordena por prioridade financeira absoluta + esforço logístico (Híbrido)
    items.sort(key=lambda x: x["impact_data"].priority_score, reverse=True)
    
    # Remover o objeto RevenueImpact puro antes de serializar (para evitar falhas no json.dumps)
    # E achatar campos para compatibilidade com Dashboard UI antiga
    for it in items:
        # Camada de Compatibilidade (UI consome ecommerce.problema etc)
        imp_obj = it["impact_data"]
        it["impact_data"] = imp_obj.to_dict()
        
        # Flatten para compatibilidade Legada
        it["failure"] = it["business"]["title"]
        it["explanation"] = it["explanation"]["what_is_happening"]
        it["loss"] = it["explanation"]["why_it_matters"]

    top = items[:top_n]

    rubric = {
        "score_range": "0-100",
        "weights": "Scoring baseado em Risco Financeiro (ROI) e não em Severidade Técnica",
        "adaptive_adjustment": "Confiança ajustada via sample histórico baseada no modelo de e-commerce",
        "financial_levels": {
            "LOW": "Risco baixo, monitorar perdas futuras",
            "MEDIUM": "Risco de perda gradual de vendas ao longo de meses",
            "HIGH": "Impacto pesado e observável nas próximas semanas",
            "CRITICAL": "Checkout travando ou perda explícita imediata",
        },
    }

    return {"top": top, "items": items, "rubric": rubric}


def decision_markdown(decision: Dict) -> str:
    top = decision.get("top") or []
    if not top:
        return "\n\n## Decision engine\n- Nenhum finding prioritário detectado.\n"

    lines: List[str] = []
    lines.append("\n\n## Impacto Comercial e Prioridades\n")
    lines.append("Recomendação principal para proteger fluxo de receita:\n")
    for i, t in enumerate(top, start=1):
        ev = t.get("ecommerce") or {}
        header = (ev.get("resumo_financeiro") or t.get("failure") or "")
        lines.append(f"{i}. {header}")
        problem = (ev.get("problema") or t.get("failure") or "").strip()
        if problem:
            lines.append(f"   - O que está havendo: {problem}")
        impact = (ev.get("impacto") or "").strip()
        if impact:
            lines.append(f"   - Perda Estimada: {impact}")
        money = (ev.get("dinheiro_em_risco") or "").strip()
        if money:
            lines.append(f"   - Sangria: {money}")
        urg = (ev.get("urgencia") or "").strip()
        if urg:
            lines.append(f"   - Urgência Operacional: {urg}")
        
        # O novo layer de agente (Confidence, Risk, Blast Radius)
        lines.append("   - Assessment de Risco:")
        lines.append(f"       Confiança do Impacto: {t.get('confidence', 0) * 100:.1f}%")
        lines.append(f"       Risco de Correção: {ev.get('risk_of_action', 'low')}")
        lines.append(f"       Raio de Explosão: {ev.get('blast_radius', 'unknown')}")
        lines.append(f"       Reversibilidade: {ev.get('reversibility', 'instant_rollback')}")

        rec = (ev.get("acao_recomendada") or t.get("recommendation") or "").strip()
        if rec:
            lines.append(f"   - Solução proposta: {rec}")

        sg = t.get("safety_gate") or {}
        if sg:
            lines.append(f"   - Permissão de Execução Automática: {sg.get('status','REQUIRES_CONFIRMATION')}")

    lines.append("\n<details><summary>Scoring (Financial Context)</summary>")
    rub = decision.get("rubric") or {}
    lines.append(f"- Base do Scoring: {rub.get('weights', '')}")
    lines.append("\nDemais achados (após filtragem de receita):\n")
    items = decision.get("items") or []
    for it in items[:40]:
        ev = it.get("ecommerce") or {}
        lines.append(f"- {ev.get('severidade_financeira_curta')} — {ev.get('impacto')}")
    if len(items) > 40:
        lines.append(f"- … ({len(items) - 40} invisíveis, não afetam receita agora)")
    lines.append("</details>")

    return "\n".join(lines) + "\n"
