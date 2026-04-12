"""Solution Factory — Interactive Streamlit UI.

A step-by-step, guided interface for the multi-agent solution pipeline.
Before Phase 0, a Topic Explorer helps narrow broad domains into specific
angles. After each phase, the app summarizes results, suggests next steps,
and lets you steer the pipeline before continuing.

Run with:
    py -3.12 -m streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import time
import traceback

import streamlit as st

from agents.topic_explorer import TopicExplorerAgent
from agents.trend_explorer import OnlineTrendExplorerAgent
from agents.trend_researcher import TrendResearchAgent
from agents.market_intel import MarketIntelligenceAgent
from agents.ideator import IdeationAgent
from agents.validator import ValidationAgent
from agents.architect import SolutionArchitectAgent
from agents.execution_planner import ExecutionPlannerAgent
from agents.critic import CriticalReviewAgent
from utils.export import export_results, save_session, list_sessions, load_session, update_idea_stage, delete_session
from utils.pdf_export import build_pdf_bytes
from utils.prompt_generator import build_claude_code_prompt
from utils.trend_metrics import render_exploration_metrics, render_trend_metrics

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_AUTH_PLACEHOLDER_PREFIXES = (
    "REPLACE_WITH_",
    "YOUR_",
    "CHANGE_ME",
)


def _is_missing_or_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    upper = text.upper()
    return any(prefix in upper for prefix in _AUTH_PLACEHOLDER_PREFIXES)

def _auth_is_configured() -> bool:
    """True only when auth secrets are present and not placeholders."""
    try:
        auth = st.secrets.get("auth", {})
        required = (
            auth.get("client_id", ""),
            auth.get("client_secret", ""),
            auth.get("cookie_secret", ""),
        )
        return all(not _is_missing_or_placeholder(v) for v in required)
    except Exception:
        return False


def _has_auth_block_but_invalid() -> bool:
    """Detect partially configured auth blocks so we can show a helpful message."""
    try:
        auth = st.secrets.get("auth", {})
        if not auth:
            return False
        required = (
            auth.get("client_id", ""),
            auth.get("client_secret", ""),
            auth.get("cookie_secret", ""),
        )
        return any(_is_missing_or_placeholder(v) for v in required)
    except Exception:
        return False


def _handle_login() -> None:
    """Run Streamlit login with a user-facing error instead of a full traceback."""
    try:
        st.login()
    except Exception as exc:
        st.error(
            "Login com Google falhou. Verifique auth.client_id, auth.client_secret, cookie_secret e redirect URI nos secrets do Streamlit.",
            icon="🚫",
        )
        st.caption(str(exc))


def _current_user_email() -> str:
    """Return the logged-in user's email, or empty string if not logged in / no auth."""
    try:
        if st.user.is_logged_in:
            return st.user.email or ""
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Fábrica de Soluções",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not os.getenv("ANTHROPIC_API_KEY"):
    st.warning(
        "ANTHROPIC_API_KEY não está definida. Adicione nas variáveis do Railway para que os agentes funcionem. "
        "A interface vai carregar, mas as chamadas do pipeline vão falhar sem essa chave.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Login gate — only shown when OAuth is configured
# ---------------------------------------------------------------------------
_AUTH_CONFIGURED = _auth_is_configured()
_AUTH_INVALID = _has_auth_block_but_invalid()

if _AUTH_INVALID:
    st.info(
        "OAuth está desabilitado localmente porque os secrets de autenticação estão ausentes ou com valores placeholder. "
        "Defina valores reais em [auth] no .streamlit/secrets.toml para habilitar o login com Google.",
        icon="ℹ️",
    )

if _AUTH_CONFIGURED:
    if not st.user.is_logged_in:
        st.markdown("## Fábrica de Soluções")
        st.markdown("Faça login para salvar e acessar seu histórico de sessões.")
        st.button("Entrar com Google", on_click=_handle_login, type="primary")
        st.stop()

_USER_EMAIL = _current_user_email()
LIFECYCLE_STAGES = [
    "Backlog",
    "Descoberta",
    "Validação",
    "Arquitetura",
    "Plano de Build",
    "Pronto para Build",
    "Revisão Necessária",
    "Estacionado",
]


def _phase_to_stage(current_phase: int, context: dict) -> str:
    """Map phase index to a user-facing production stage."""
    if current_phase < 0:
        return "Backlog"

    phase_stage = {
        0: "Descoberta",
        1: "Descoberta",
        2: "Validação",
        3: "Validação",
        4: "Arquitetura",
        5: "Plano de Build",
    }

    if current_phase == 6:
        verdict = context.get("critical_review", {}).get("go_no_go", "")
        return {
            "go": "Pronto para Build",
            "conditional_go": "Revisão Necessária",
            "no_go": "Estacionado",
        }.get(verdict, "Revisão")

    return phase_stage.get(current_phase, "Em Progresso")


def _checkpoint_session(context: dict, current_phase: int) -> None:
    """Persist an incremental checkpoint for long-running sessions."""
    context["production_stage"] = _phase_to_stage(current_phase, context)
    context["session_path"] = save_session(context, current_phase, user_email=_USER_EMAIL)


def _is_credit_balance_error(exc: Exception) -> bool:
    """Return True for known Anthropic insufficient-credit failures."""
    text = str(exc).lower()
    return (
        "credit balance is too low" in text
        or "plans & billing" in text
        or "insufficient" in text and "credit" in text
    )


def _offline_exploration_fallback(domain: str, mode: str) -> dict:
    """Provide deterministic exploration suggestions when API credits are unavailable."""
    if mode == "online_trends":
        paths = [
            {
                "broad_area": "Automação de Processos",
                "mid_area": "Inteligência Operacional",
                "narrow_area": f"Copilotos de automação para {domain}",
                "opportunity_hypothesis": "Times vão pagar para reduzir tarefas repetitivas e tempo de ciclo.",
                "why_now": "Ferramentas de automação e expectativas dos usuários aceleraram.",
                "momentum": "warm",
                "source_signals": [
                    "Demanda recorrente por automação de processos em PMEs.",
                    "Adoção crescente de copilotos IA em software empresarial.",
                ],
                "starter_queries": [
                    f"principais workflows repetitivos em {domain}",
                    f"{domain} pontos de dor automação",
                ],
            },
            {
                "broad_area": "Compliance & Risco",
                "mid_area": "Auditabilidade",
                "narrow_area": f"Workflows de compliance para {domain}",
                "opportunity_hypothesis": "Domínios com alto risco precisam de sistemas simples e auditáveis.",
                "why_now": "Pressão regulatória está aumentando enquanto times permanecem enxutos.",
                "momentum": "warm",
                "source_signals": [
                    "Crescente carga de compliance em setores regulados.",
                    "Preferência por ferramentas que previnem multas e retrabalho.",
                ],
                "starter_queries": [
                    f"{domain} desafios de compliance 2026",
                    f"requisitos de auditoria para times de {domain}",
                ],
            },
            {
                "broad_area": "Experiência do Cliente",
                "mid_area": "Velocidade de Resposta",
                "narrow_area": f"Suporte e onboarding mais rápidos em {domain}",
                "opportunity_hypothesis": "Melhorar primeira resposta e onboarding aumenta retenção.",
                "why_now": "Usuários comparam todo produto com as melhores experiências de suporte.",
                "momentum": "hot",
                "source_signals": [
                    "Atrasos em suporte e onboarding aparecem em diversos canais de avaliação.",
                    "Pressão por retenção torna melhorias de CX alta prioridade.",
                ],
                "starter_queries": [
                    f"{domain} fricção no onboarding de clientes",
                    f"reclamações comuns sobre ferramentas de {domain}",
                ],
            },
        ]
        broad_areas = []
        for title in sorted({p["broad_area"] for p in paths}):
            broad_areas.append(
                {
                    "title": title,
                    "signal_summary": "Gerado a partir de fallback local devido a limites de crédito da API.",
                }
            )
        return {
            "exploration_domain": domain,
            "broad_areas": broad_areas,
            "exploration_paths": paths,
        }

    return {
        "exploration_domain": domain,
        "exploration_angles": [
            {
                "category": "technology",
                "title": f"Copilotos IA em {domain}",
                "description": "Foco em decisões repetitivas que podem ser assistidas com prompts estruturados de IA.",
                "example_questions": [
                    f"Quais tarefas em {domain} são baseadas em regras e repetitivas?",
                    f"Onde os times perdem mais tempo por semana em {domain}?",
                ],
                "heat_level": "warm",
            },
            {
                "category": "pain_point",
                "title": f"Workflows de alta fricção em {domain}",
                "description": "Procure gargalos que causam atrasos, erros ou retrabalho.",
                "example_questions": [
                    f"Qual workflow em {domain} gera mais retrabalho?",
                    f"Qual handoff falha com mais frequência em times de {domain}?",
                ],
                "heat_level": "hot",
            },
            {
                "category": "business_model",
                "title": f"SaaS vertical B2B para {domain}",
                "description": "Estreite para times com forte disposição a pagar por ROI mensurável.",
                "example_questions": [
                    f"Quem controla o orçamento para melhoria de processos em {domain}?",
                    f"Qual melhoria de KPI justificaria uma ferramenta paga em {domain}?",
                ],
                "heat_level": "warm",
            },
        ],
    }

# ---------------------------------------------------------------------------
# Phase registry (Phase 0-6, exploration is pre-phase)
# ---------------------------------------------------------------------------
PHASES = [
    {"key": "trend_research",       "label": "Pesquisa de Tendências",    "num": 0, "agent_cls": TrendResearchAgent,     "critical": False},
    {"key": "opportunity_discovery", "label": "Descoberta de Oportunidades", "num": 1, "agent_cls": MarketIntelligenceAgent, "critical": True},
    {"key": "ideation",             "label": "Ideação de Soluções",       "num": 2, "agent_cls": IdeationAgent,           "critical": True},
    {"key": "validation",           "label": "Validação de Conceitos",    "num": 3, "agent_cls": ValidationAgent,         "critical": True},
    {"key": "architecture",         "label": "Arquitetura da Solução",    "num": 4, "agent_cls": SolutionArchitectAgent,  "critical": True},
    {"key": "execution_planning",   "label": "Planejamento de Execução",  "num": 5, "agent_cls": ExecutionPlannerAgent,   "critical": True},
    {"key": "critical_review",      "label": "Revisão Crítica",           "num": 6, "agent_cls": CriticalReviewAgent,     "critical": True},
]
TOTAL_PHASES = len(PHASES)

# ---------------------------------------------------------------------------
# Country/region options for search targeting
# ---------------------------------------------------------------------------
COUNTRY_OPTIONS = {
    "worldwide": "🌍 Mundial",
    "BR": "🇧🇷 Brasil",
    "US": "🇺🇸 Estados Unidos",
    "GB": "🇬🇧 Reino Unido",
    "DE": "🇩🇪 Alemanha",
    "FR": "🇫🇷 França",
    "JP": "🇯🇵 Japão",
    "IN": "🇮🇳 Índia",
    "CA": "🇨🇦 Canadá",
    "AU": "🇦🇺 Austrália",
    "PT": "🇵🇹 Portugal",
    "ES": "🇪🇸 Espanha",
    "MX": "🇲🇽 México",
    "AR": "🇦🇷 Argentina",
    "CL": "🇨🇱 Chile",
    "CO": "🇨🇴 Colômbia",
    "CN": "🇨🇳 China",
    "KR": "🇰🇷 Coreia do Sul",
    "IL": "🇮🇱 Israel",
    "AE": "🇦🇪 Emirados Árabes",
    "NG": "🇳🇬 Nigéria",
    "KE": "🇰🇪 Quênia",
    "SG": "🇸🇬 Singapura",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
DEFAULTS = {
    "context": {},
    "current_phase": -1,           # -1 = waiting for input
    "history": [],
    # Exploration state
    "step": "prompt",              # "prompt" | "exploring" | "explored" | "pipeline"
    "exploration_angles": [],
    "exploration_paths": [],
    "exploration_domain": "",
    "exploration_mode": "brainstorm",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Fábrica de Soluções")
    st.caption("Pipeline passo-a-passo da ideia à execução")

    if _AUTH_CONFIGURED and _USER_EMAIL:
        st.divider()
        st.caption(f"Conectado como **{st.user.name}**")
        st.caption(_USER_EMAIL)
        st.button("Sair", on_click=st.logout, use_container_width=True)

    st.divider()
    st.subheader("Progresso do Pipeline")
    current = st.session_state.current_phase
    step = st.session_state.step

    # Exploration indicator
    if step in ("exploring", "explored"):
        st.markdown("  **:blue[>> Exploração de Temas]**")
    elif step == "pipeline" and current < 0:
        st.markdown("  :green[Exploração de Temas]")
    else:
        st.markdown("  :gray[Exploração de Temas]")

    for phase in PHASES:
        num = phase["num"]
        label = phase["label"]
        if current >= 0 and num < current + 1:
            st.markdown(f"  :green[Phase {num}: {label}]")
        elif step == "pipeline" and num == current + 1:
            st.markdown(f"  **:blue[>> Phase {num}: {label}]**")
        else:
            st.markdown(f"  :gray[Phase {num}: {label}]")

    st.divider()
    st.subheader("Histórico de Sessões")
    saved_sessions = list_sessions(user_email=_USER_EMAIL)
    if saved_sessions:
        stage_counts: dict[str, int] = {}
        for s in saved_sessions:
            stage = s.get("production_stage", "Desconhecido")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        st.caption("Ideias por estágio")
        for stage, count in sorted(stage_counts.items(), key=lambda x: x[0]):
            st.markdown(f"- {stage}: {count}")

    if saved_sessions:
        st.divider()
        st.subheader("Gerenciar Sessões Anteriores")
        session_query = st.text_input(
            "Buscar",
            placeholder="Buscar prompt, ID da ideia, conceito...",
            key="session_manage_query",
        ).strip().lower()
        session_stage_filter = st.selectbox(
            "Estágio da sessão",
            ["Todos"] + LIFECYCLE_STAGES,
            key="session_manage_stage_filter",
        )

        filtered_sessions = saved_sessions
        if session_stage_filter != "Todos":
            filtered_sessions = [
                s for s in filtered_sessions
                if (s.get("production_stage") or "") == session_stage_filter
            ]
        if session_query:
            filtered_sessions = [
                s for s in filtered_sessions
                if session_query in (s.get("user_prompt") or "").lower()
                or session_query in (s.get("idea_id") or "").lower()
                or session_query in (s.get("selected_concept") or "").lower()
            ]

        st.caption(f"Mostrando {len(filtered_sessions)} de {len(saved_sessions)} sessão(ões)")

        for s in filtered_sessions[:20]:  # cap at 20
            v = s.get("verdict", "")
            color = {"go": "green", "conditional_go": "orange", "no_go": "red"}.get(v, "gray")
            verdict_label = {"go": "VAI", "conditional_go": "COND", "no_go": "NÃO VAI"}.get(v, "WIP")
            prompt_preview = (s.get("user_prompt") or "")[:40]
            ts = (s.get("timestamp") or "")[:10]
            stage = s.get("production_stage") or "Desconhecido"
            with st.expander(f":{color}[{verdict_label}] {prompt_preview}", expanded=False):
                st.caption(ts)
                st.caption(f"Estágio: {stage}")
                idea_id = s.get("idea_id") or ""
                if idea_id:
                    st.caption(f"ID da Ideia: {idea_id}")
                concept = s.get("selected_concept") or ""
                if concept:
                    st.caption(f"Conceito: {concept[:60]}")
                score = s.get("score") or 0
                if score:
                    st.caption(f"Score: {score}/10")
                act_col1, act_col2, act_col3 = st.columns(3)
                with act_col1:
                    if st.button("Abrir", key=f"open_{s['filename']}", use_container_width=True):
                        ctx_loaded, phase_loaded = load_session(s["path"])
                        for k, dv in DEFAULTS.items():
                            st.session_state[k] = dv
                        st.session_state.context = ctx_loaded
                        st.session_state.current_phase = phase_loaded
                        st.session_state.step = "pipeline"
                        st.rerun()
                with act_col2:
                    if st.button("Arquivar", key=f"archive_{s['filename']}", use_container_width=True):
                        idea_id = s.get("idea_id") or ""
                        if not idea_id:
                            st.warning("Esta sessão não tem ID de ideia, não é possível arquivar como investigação.")
                        else:
                            updated = update_idea_stage(
                                idea_id=idea_id,
                                new_stage="Estacionado",
                                user_email=_USER_EMAIL,
                            )
                            if updated:
                                st.success(f"{updated} sessão(ões) arquivada(s) para esta investigação.")
                            else:
                                st.warning("Nenhuma sessão encontrada para arquivar.")
                            st.rerun()
                with act_col3:
                    if st.button("Excluir", key=f"delete_{s['filename']}", use_container_width=True):
                        deleted = delete_session(path=s["path"], user_email=_USER_EMAIL)
                        if deleted:
                            st.success("Sessão excluída.")
                        else:
                            st.warning("Não foi possível excluir esta sessão.")
                        st.rerun()
    else:
        st.caption("Nenhuma sessão salva ainda.")

    if step != "prompt":
        st.divider()
        if st.button("Recomeçar", use_container_width=True):
            for k, v in DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()


# ====================================================================
# Render helpers
# ====================================================================

def render_trends(ctx: dict) -> None:
    """Render Phase 0 trends with metrics dashboard."""
    trends = ctx.get("trends", [])
    if not trends:
        st.warning("Nenhuma tendência encontrada.")
        return

    source = ctx.get("_source", "live")
    if source == "builtin":
        st.info("ℹ️ Tendências geradas a partir do conhecimento interno do Claude (busca web indisponível para este domínio ou plano da API).")

    # Use the new metrics-focused render function
    trends_output = {
        "trends": trends,
        "market_sentiment": ctx.get("market_sentiment", "cautious"),
        "key_takeaway": ctx.get("key_takeaway", ""),
        "domain": ctx.get("user_prompt", "Unknown Domain"),
        "search_queries_used": ctx.get("search_queries_used", []),
    }
    render_trend_metrics(trends_output)


def render_opportunities(ctx: dict) -> None:
    conf_labels = {"high": "alta", "medium": "média", "low": "baixa"}
    for opp in ctx.get("opportunities", []):
        conf = opp.get("confidence", "?")
        cc = {"high": "green", "medium": "orange", "low": "red"}.get(conf, "gray")
        conf_pt = conf_labels.get(conf, conf)
        with st.expander(f"**{opp.get('title', '?')}** — :{cc}[confiança {conf_pt}]"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Domínio:** {opp.get('domain', '?')}")
                st.markdown(f"**Público-alvo:** {opp.get('target_audience', '?')}")
                st.markdown(f"**Receita:** {opp.get('revenue_potential', '?')}")
            with c2:
                st.markdown(f"**Timing:** {opp.get('timing_rationale', '?')}")
                st.markdown(f"**Competição:** {opp.get('competition_landscape', '?')}")
            st.markdown(f"**Ponto de dor:** {opp.get('pain_point', '?')}")
            for s in opp.get("market_signals", []):
                st.markdown(f"- {s}")


def render_concepts(ctx: dict) -> None:
    for c in ctx.get("concepts", []):
        with st.expander(f"**{c.get('name', '?')}** — {c.get('one_liner', '')}"):
            st.markdown(f"**Endereça:** {c.get('opportunity_ref', '?')}")
            st.markdown(f"**Como funciona:** {c.get('how_it_works', '?')}")
            st.markdown(f"**Diferencial:** {c.get('key_differentiator', '?')}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Monetização:** {c.get('monetization_model', '?')}")
                st.markdown(f"**Escopo do MVP:** {c.get('mvp_scope', '?')}")
            with c2:
                st.markdown(f"**Usuário-alvo:** {c.get('target_user_persona', '?')}")
                for a in c.get("assumptions", []):
                    st.markdown(f"- {a}")


def render_validation(ctx: dict) -> None:
    rec_labels = {"proceed": "PROSSEGUIR", "pivot": "PIVOTAR", "kill": "DESCARTAR"}
    for v in ctx.get("validations", []):
        ref = v.get("concept_ref", "?")
        overall = v.get("overall_score", 0)
        rec = v.get("recommendation", "?")
        rc = {"proceed": "green", "pivot": "orange", "kill": "red"}
        rec_pt = rec_labels.get(rec, rec.upper())
        with st.expander(f"**{ref}** — {overall:.1f}/10 :{rc.get(rec, 'gray')}[{rec_pt}]"):
            c1, c2, c3 = st.columns(3)
            with c1:
                mf = v.get("market_fit_score", 0)
                st.metric("Fit de Mercado", f"{mf}/10")
                st.progress(mf / 10)
            with c2:
                fs = v.get("feasibility_score", 0)
                st.metric("Viabilidade", f"{fs}/10")
                st.progress(fs / 10)
            with c3:
                rv = v.get("revenue_viability_score", 0)
                st.metric("Viab. de Receita", f"{rv}/10")
                st.progress(rv / 10)
            st.markdown(f"**Raciocínio:** {v.get('reasoning', '')}")
            c_s, c_w = st.columns(2)
            with c_s:
                for s in v.get("strengths", []):
                    st.markdown(f"- :green[{s}]")
            with c_w:
                for w in v.get("weaknesses", []):
                    st.markdown(f"- :orange[{w}]")
            for r in v.get("killer_risks", []):
                st.error(r)


def render_architecture(ctx: dict) -> None:
    arch = ctx.get("architecture", {})
    st.markdown(f"**Conceito selecionado:** {ctx.get('selected_concept', '?')}")
    st.markdown(f"**Complexidade:** {arch.get('estimated_complexity', '?')}")
    st.markdown(arch.get("system_overview", ""))
    roles = arch.get("roles", [])
    if roles:
        st.markdown("### Papéis & Agentes")
        ai = [r for r in roles if r.get("type") == "ai_agent"]
        hu = [r for r in roles if r.get("type") == "human"]
        hy = [r for r in roles if r.get("type") == "hybrid"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Agentes IA", len(ai))
        c2.metric("Papéis Humanos", len(hu))
        c3.metric("Híbrido", len(hy))
        for r in roles:
            rt = r.get("type", "?")
            icon = {"ai_agent": "🤖", "human": "👤", "hybrid": "🔄"}.get(rt, "?")
            with st.expander(f"{icon} **{r.get('title', '?')}** ({rt})"):
                for resp in r.get("responsibilities", []):
                    st.markdown(f"- {resp}")
                st.markdown(f"**Ferramentas:** {', '.join(r.get('tools_needed', []))}")
    stack = arch.get("tech_stack", [])
    if stack:
        st.markdown("### Stack Tecnológico")
        for comp in stack:
            with st.expander(f"**{comp.get('name', '?')}** — {comp.get('technology', '?')}"):
                st.markdown(f"**Propósito:** {comp.get('purpose', '?')}")
                st.markdown(f"**Justificativa:** {comp.get('rationale', '?')}")
    df = arch.get("data_flow", "")
    if df:
        st.markdown(f"### Fluxo de Dados\n{df}")
    cost = arch.get("cost_structure", "")
    if cost:
        st.markdown(f"### Estrutura de Custos\n{cost}")


def render_execution_plan(ctx: dict) -> None:
    plan = ctx.get("execution_plan", {})
    qw = plan.get("quick_wins", [])
    if qw:
        st.markdown("### Quick Wins (Primeiras 48h)")
        for q in qw:
            st.markdown(f"- {q}")
    for i, m in enumerate(plan.get("phases", [])):
        with st.expander(f"**{i+1}. {m.get('name','?')}** — {m.get('estimated_duration','?')}"):
            st.markdown(m.get("description", ""))
            for d in m.get("deliverables", []):
                st.markdown(f"- {d}")
            deps = m.get("dependencies", [])
            if deps:
                st.markdown(f"**Depende de:** {', '.join(deps)}")
            for c in m.get("success_criteria", []):
                st.markdown(f"- {c}")
    crit = plan.get("critical_path", [])
    if crit:
        st.markdown(f"### Caminho Crítico\n{' → '.join(crit)}")
    mits = plan.get("risk_mitigations", {})
    if mits:
        st.markdown("### Mitigação de Riscos")
        for risk, mit in mits.items():
            st.markdown(f"- **{risk}:** {mit}")


def render_critical_review(ctx: dict) -> None:
    review = ctx.get("critical_review", {})
    score = review.get("score", 0)
    verdict = review.get("go_no_go", "?")
    viability = review.get("overall_viability", "?")
    vc = {"go": ("success", "VAI"), "conditional_go": ("warning", "VAI COM CONDIÇÕES"), "no_go": ("error", "NÃO VAI")}
    mt, vt = vc.get(verdict, ("info", verdict.upper()))
    getattr(st, mt)(f"**{vt}** — Nota: {score}/10 | Viabilidade: {viability}")
    final = review.get("final_verdict", "")
    if final:
        st.markdown(final)
    c1, c2 = st.columns(2)
    with c1:
        for s in review.get("strongest_elements", []):
            st.markdown(f"- :green[{s}]")
    with c2:
        for b in review.get("blind_spots", []):
            st.markdown(f"- :orange[{b}]")
    for f in review.get("fatal_flaws", []):
        st.error(f)
    for c in review.get("conditions", []):
        st.warning(c)


RENDERERS = {
    "trend_research": render_trends,
    "opportunity_discovery": render_opportunities,
    "ideation": render_concepts,
    "validation": render_validation,
    "architecture": render_architecture,
    "execution_planning": render_execution_plan,
    "critical_review": render_critical_review,
}


# ====================================================================
# Phase summaries
# ====================================================================

def summarize_trend_research(ctx: dict) -> str:
    trends = ctx.get("trends", [])
    sentiment = ctx.get("market_sentiment", "unknown")
    takeaway = ctx.get("key_takeaway", "")
    source = ctx.get("_source", "live")
    if not trends:
        return "Nenhuma tendência encontrada. Continuando com conhecimento interno."
    source_label = "conhecimento interno" if source == "builtin" else "busca web ao vivo"
    titles = ", ".join(t.get("title", "?") for t in trends[:3])
    return (
        f"Encontradas **{len(trends)} tendências** via {source_label} — sentimento: **{sentiment}**.\n\n"
        f"Principais tendências: {titles}\n\n"
        f"Conclusão-chave: *{takeaway}*"
    )

def summarize_opportunities(ctx: dict) -> str:
    opps = ctx.get("opportunities", [])
    if not opps:
        return "Nenhuma oportunidade identificada."
    lines = [f"- **{o.get('title','?')}** ({o.get('confidence','?')}) — {o.get('pain_point','')[:100]}" for o in opps]
    return f"Identificadas **{len(opps)} oportunidades:**\n\n" + "\n".join(lines)

def summarize_ideation(ctx: dict) -> str:
    concepts = ctx.get("concepts", [])
    if not concepts:
        return "Nenhum conceito gerado."
    lines = [f"- **{c.get('name','?')}** — {c.get('one_liner','')}" for c in concepts]
    return f"Gerados **{len(concepts)} conceitos:**\n\n" + "\n".join(lines)

def summarize_validation(ctx: dict) -> str:
    vals = ctx.get("validations", [])
    if not vals:
        return "Nenhum resultado de validação."
    best = max(vals, key=lambda v: v.get("overall_score", 0))
    lines = [f"- **{v.get('concept_ref','?')}** — {v.get('overall_score',0):.1f}/10 ({v.get('recommendation','?')})" for v in vals]
    return "\n".join(lines) + f"\n\nMelhor: **{best.get('concept_ref','?')}** com {best.get('overall_score',0):.1f}/10"

def summarize_architecture(ctx: dict) -> str:
    arch = ctx.get("architecture", {})
    roles = arch.get("roles", [])
    ai_n = sum(1 for r in roles if r.get("type") == "ai_agent")
    hu_n = sum(1 for r in roles if r.get("type") == "human")
    return (
        f"Arquitetura para **{ctx.get('selected_concept','?')}** — "
        f"{len(roles)} papéis ({ai_n} IA, {hu_n} humano), "
        f"complexidade: {arch.get('estimated_complexity','?')}"
    )

def summarize_execution_plan(ctx: dict) -> str:
    plan = ctx.get("execution_plan", {})
    phases = plan.get("phases", [])
    crit = plan.get("critical_path", [])
    return f"**{len(phases)} marcos** — Caminho crítico: {' → '.join(crit[:4])}"

def summarize_critical_review(ctx: dict) -> str:
    review = ctx.get("critical_review", {})
    go_labels = {"go": "VAI", "conditional_go": "VAI COM CONDIÇÕES", "no_go": "NÃO VAI"}
    verdict = review.get('go_no_go', '?')
    return f"**{go_labels.get(verdict, verdict.upper())}** — Nota: {review.get('score',0)}/10"

SUMMARIZERS = {
    "trend_research": summarize_trend_research,
    "opportunity_discovery": summarize_opportunities,
    "ideation": summarize_ideation,
    "validation": summarize_validation,
    "architecture": summarize_architecture,
    "execution_planning": summarize_execution_plan,
    "critical_review": summarize_critical_review,
}


# ====================================================================
# Next-step options per phase
# ====================================================================

def get_next_options(phase_key: str, ctx: dict) -> list[dict]:
    next_idx = next((i for i, p in enumerate(PHASES) if p["key"] == phase_key), -1) + 1
    next_label = PHASES[next_idx]["label"] if next_idx < TOTAL_PHASES else None
    options = []

    if phase_key == "trend_research":
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": "Alimentar tendências na Inteligência de Mercado para análise fundamentada."})
        options.append({"label": "Pular tendências e continuar", "action": "skip_trends", "type": "secondary",
                        "help": "Limpar tendências, usar apenas conhecimento interno."})
        options.append({"label": "Re-executar pesquisa de tendências", "action": "rerun", "type": "secondary",
                        "help": "Buscar novamente com foco diferente."})

    elif phase_key == "opportunity_discovery":
        n = len(ctx.get("opportunities", []))
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": f"Gerar conceitos para {n} oportunidades."})
        options.append({"label": "Re-executar com orientação", "action": "rerun", "type": "secondary",
                        "help": "Direcionar a análise de forma diferente."})

    elif phase_key == "ideation":
        n = len(ctx.get("concepts", []))
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": f"Testar {n} conceitos sob pressão."})
        options.append({"label": "Gerar mais conceitos", "action": "rerun", "type": "secondary",
                        "help": "Explorar ângulos diferentes."})

    elif phase_key == "validation":
        vals = ctx.get("validations", [])
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": "Arquitetar o conceito selecionado abaixo."})
        if any(v.get("recommendation") == "kill" for v in vals):
            options.append({"label": "Voltar para Ideação", "action": "back_to_ideation", "type": "secondary",
                            "help": "Gerar novos conceitos usando feedback do validador."})
        options.append({"label": "Re-validar", "action": "rerun", "type": "secondary",
                        "help": "Adicionar contexto que o validador não considerou."})

    elif phase_key == "architecture":
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": "Criar marcos e cronograma."})
        options.append({"label": "Re-arquitetar", "action": "rerun", "type": "secondary",
                        "help": "Adicionar restrições de orçamento/equipe/tecnologia."})

    elif phase_key == "execution_planning":
        options.append({"label": f"Continuar para {next_label}", "action": "next", "type": "primary",
                        "help": "Revisão final e veredito."})
        options.append({"label": "Ajustar plano", "action": "rerun", "type": "secondary",
                        "help": "Adicionar restrições."})

    elif phase_key == "critical_review":
        review = ctx.get("critical_review", {})
        verdict = review.get("go_no_go", "?")
        if verdict == "no_go":
            options.append({"label": "Re-executar com feedback", "action": "restart_with_feedback", "type": "primary",
                            "help": "Alimentar problemas do crítico de volta para uma segunda iteração."})
        if verdict in ("go", "conditional_go"):
            options.append({"label": "Gerar prompt para Claude Code", "action": "generate_prompt",
                            "type": "primary",
                            "help": "Criar um prompt completo para começar a desenvolver o projeto no Claude Code."})
        options.append({"label": "Exportar resultados", "action": "export",
                        "type": "secondary",
                        "help": "Salvar saída completa como JSON."})
        options.append({"label": "Nova ideia", "action": "reset", "type": "secondary",
                        "help": "Começar do zero."})

    return options


# ====================================================================
# Run a single phase
# ====================================================================

def run_single_phase(phase_idx: int, ctx: dict, user_notes: str = "") -> dict:
    phase = PHASES[phase_idx]
    agent = phase["agent_cls"]()

    if user_notes.strip():
        ctx["user_guidance"] = user_notes.strip()

    with st.status(f"Fase {phase['num']}: {phase['label']} — executando...", expanded=True) as status:
        st.caption(f"Agente: **{agent.name}** | Modelo: `{agent.model}`")
        start = time.time()
        try:
            result = agent.run(ctx)
            ctx.update(result)
            elapsed = time.time() - start
            status.update(label=f"Fase {phase['num']}: {phase['label']} — {elapsed:.1f}s",
                          state="complete", expanded=False)
        except Exception as e:
            elapsed = time.time() - start
            if phase["key"] == "trend_research" and _is_credit_balance_error(e):
                status.update(
                    label=f"Fase {phase['num']}: {phase['label']} — pulada (créditos da API indisponíveis, {elapsed:.1f}s)",
                    state="complete",
                    expanded=False,
                )
                st.warning(
                    "⚠️ Fase 0 pulada: saldo de créditos da API Anthropic muito baixo para busca web. "
                    "Pipeline continua com conhecimento interno."
                )
                ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
            elif phase["key"] == "trend_research" and not phase["critical"]:
                status.update(
                    label=f"Fase {phase['num']}: {phase['label']} — indisponível ({elapsed:.1f}s)",
                    state="complete",
                    expanded=False,
                )
                st.info(
                    f"ℹ️ Pesquisa de tendências ao vivo indisponível ({type(e).__name__}: {e}). "
                    "Pipeline continua com conhecimento interno."
                )
                ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
            else:
                status.update(label=f"Fase {phase['num']}: {phase['label']} — FALHOU ({elapsed:.1f}s)",
                              state="error")
                st.error(f"**{agent.name}** falhou: {e}")
                st.code(traceback.format_exc(), language="text")
                if not phase["critical"]:
                    pass
                else:
                    ctx["_phase_failed"] = True
        else:
            # Successful run — warn if Phase 0 came back empty (web search silently returned nothing)
            if phase["key"] == "trend_research" and not ctx.get("trends"):
                st.info(
                    "ℹ️ A busca web não retornou resultados para este domínio. "
                    "Pipeline continua com conhecimento interno."
                )
    return ctx


def score_exploration_path(path: dict) -> dict:
    """Compute a compact why-this-path score for fast selection decisions."""
    momentum = str(path.get("momentum", "warm")).lower()
    momentum_score = {"hot": 3, "warm": 2, "cool": 1}.get(momentum, 1)

    combined_text = " ".join([
        str(path.get("opportunity_hypothesis", "")),
        str(path.get("why_now", "")),
        " ".join(path.get("source_signals", []) or []),
    ]).lower()

    pain_keywords = {
        "pain", "problem", "complaint", "cost", "wait", "shortage", "burnout",
        "dropout", "churn", "risk", "compliance", "inefficiency", "friction",
    }
    pain_hits = sum(1 for kw in pain_keywords if kw in combined_text)
    buyer_pain_score = 3 if pain_hits >= 3 else 2 if pain_hits >= 1 else 1

    feasibility_text = (
        f"{path.get('mid_area', '')} {path.get('narrow_area', '')} "
        f"{path.get('opportunity_hypothesis', '')}"
    ).lower()
    low_feasibility_terms = {
        "drug", "biotech", "clinical trial", "implant", "hardware", "medical device"
    }
    high_feasibility_terms = {
        "saas", "workflow", "platform", "automation", "assistant", "analytics", "copilot"
    }
    if any(term in feasibility_text for term in low_feasibility_terms):
        feasibility_score = 1
    elif any(term in feasibility_text for term in high_feasibility_terms):
        feasibility_score = 3
    else:
        feasibility_score = 2

    total = momentum_score + buyer_pain_score + feasibility_score
    return {
        "momentum": momentum_score,
        "buyer_pain": buyer_pain_score,
        "feasibility": feasibility_score,
        "total": total,
    }


# ====================================================================
# Trending helper
# ====================================================================

@st.cache_data(ttl=3600)
def get_trending_topics() -> list[dict]:
    """Fetch what's trending across domains (cached for 1 hour).
    
    Returns list of dicts with keys: title, why_trending, signal.
    """
    trending = [
        {
            "title": "Otimização de Supply Chain com IA",
            "why_trending": "Consolidação logística pós-pandemia + pressão por eficiência.",
            "signal": "📦 Tech + Operações",
        },
        {
            "title": "Saúde Mental Corporativa",
            "why_trending": "Burnout + pressão regulatória + exigências de seguradoras.",
            "signal": "💼 Saúde + Trabalho",
        },
        {
            "title": "Infraestrutura de Dados Biotech",
            "why_trending": "Descoberta de fármacos com IA exige pipelines massivos de biomarcadores.",
            "signal": "🧬 IA + Biologia",
        },
        {
            "title": "Fintech para Mercados Emergentes",
            "why_trending": "Pagamentos mobile-first + stablecoins para populações desbancarizadas.",
            "signal": "💰 Mobile + Finanças",
        },
        {
            "title": "Redes de Entrega Autônoma",
            "why_trending": "Robótica last-mile resolve escassez de mão de obra + crise de custos.",
            "signal": "🤖 Robótica + Logística",
        },
    ]
    return trending


# ====================================================================
# Main UI
# ====================================================================

st.markdown("# Fábrica de Soluções")

step = st.session_state.step

# ------------------------------------------------------------------
# STEP 1: Prompt input
# ------------------------------------------------------------------
if step == "prompt":
    st.markdown("## Descobrir & Explorar")
    st.markdown("Digite um domínio, ideia ou problema. Ou escolha o que está em alta agora.")

    # Trending Now section
    st.markdown("### 🔥 Em Alta Agora")
    st.caption("Clique em qualquer tema para preencher o formulário")

    trending_topics = get_trending_topics()
    trending_cols = st.columns(len(trending_topics))

    for col, trend in zip(trending_cols, trending_topics):
        with col:
            if st.button(
                f"{trend['title']}",
                key=f"trending_{trend['title']}",
                use_container_width=True,
                help=trend["why_trending"],
            ):
                st.session_state.context = {
                    "user_prompt": trend["title"].strip(),
                    "production_stage": "Backlog",
                    "exploration_mode": "online_trends",
                    "search_country": "worldwide",
                    "owner_email": _USER_EMAIL,
                }
                st.session_state.exploration_mode = "online_trends"
                st.session_state.step = "exploring"
                st.rerun()
            st.caption(f"{trend['signal']}")

    st.divider()
    st.markdown("### Ou Explore o Seu Próprio")

    with st.form("prompt_form"):
        exploration_mode = st.radio(
            "Modo de exploração",
            options=["brainstorm", "online_trends"],
            format_func=lambda v: (
                "Brainstorming rápido (ideação com LLM)"
                if v == "brainstorm"
                else "Varredura de tendências ao vivo (amplo para estreito)"
            ),
            help="Varredura de tendências usa busca web ao vivo para propor caminhos de exploração de áreas amplas a nichos estreitos.",
            horizontal=True,
            key="exploration_mode_input",
        )
        user_prompt = st.text_area(
            "Qual domínio você quer explorar?",
            placeholder="ex: saúde e bem-estar, IA em logística, fintech para freelancers...",
            height=100,
            max_chars=5000,
        )
        search_country = st.selectbox(
            "País/região para a pesquisa",
            options=list(COUNTRY_OPTIONS.keys()),
            format_func=lambda k: COUNTRY_OPTIONS[k],
            index=0,
            help="Direciona as buscas web e análises de mercado para o país/região selecionado.",
            key="search_country_input",
        )
        submitted = st.form_submit_button("Explorar Temas", type="primary", use_container_width=True)

    if submitted and user_prompt.strip():
        st.session_state.context = {
            "user_prompt": user_prompt.strip(),
            "production_stage": "Backlog",
            "exploration_mode": exploration_mode,
            "search_country": search_country,
            "owner_email": _USER_EMAIL,
        }
        st.session_state.exploration_mode = exploration_mode
        st.session_state.step = "exploring"
        st.rerun()
    elif submitted:
        st.warning("Digite um domínio ou ideia primeiro.")
    st.stop()

# ------------------------------------------------------------------
# STEP 2: Topic Exploration (runs agent, then shows results)
# ------------------------------------------------------------------
if step == "exploring":
    ctx = st.session_state.context
    exploration_mode = ctx.get("exploration_mode", st.session_state.exploration_mode)
    _country_code = ctx.get("search_country", "worldwide")
    _country_label = COUNTRY_OPTIONS.get(_country_code, _country_code)
    st.markdown(f"> **Domínio:** {ctx['user_prompt']}  |  **Região:** {_country_label}")
    st.divider()

    status_text = (
        "Varrendo tendências ao vivo e gerando caminhos amplo-para-estreito..."
        if exploration_mode == "online_trends"
        else "Explorando ângulos de temas..."
    )

    with st.status(status_text, expanded=True) as status:
        if exploration_mode == "online_trends":
            agent = OnlineTrendExplorerAgent()
            st.caption(f"Agente: **{agent.name}** | Modelo: `{agent.model}` (varredura de tendências ao vivo)")
        else:
            agent = TopicExplorerAgent()
            st.caption(f"Agente: **{agent.name}** | Modelo: `{agent.model}` (brainstorming rápido)")
        start = time.time()
        try:
            result = agent.run(ctx)
            ctx.update(result)
            st.session_state.context = ctx
            st.session_state.exploration_angles = result.get("exploration_angles", [])
            st.session_state.exploration_paths = result.get("exploration_paths", [])
            st.session_state.exploration_domain = result.get("exploration_domain", ctx["user_prompt"])
            # Store full exploration output for metrics rendering
            st.session_state.exploration_output = {
                "exploration_domain": result.get("exploration_domain", ""),
                "broad_areas": result.get("broad_areas", []),
                "exploration_paths": result.get("exploration_paths", []),
            }
            elapsed = time.time() - start
            status.update(label=f"Exploração de temas — {elapsed:.1f}s", state="complete", expanded=False)
            st.session_state.step = "explored"
            st.rerun()
        except Exception as e:
            elapsed = time.time() - start
            if _is_credit_balance_error(e):
                fallback = _offline_exploration_fallback(ctx["user_prompt"], exploration_mode)
                ctx.update(fallback)
                st.session_state.context = ctx
                st.session_state.exploration_angles = fallback.get("exploration_angles", [])
                st.session_state.exploration_paths = fallback.get("exploration_paths", [])
                st.session_state.exploration_domain = fallback.get("exploration_domain", ctx["user_prompt"])
                st.session_state.exploration_output = {
                    "exploration_domain": fallback.get("exploration_domain", ""),
                    "broad_areas": fallback.get("broad_areas", []),
                    "exploration_paths": fallback.get("exploration_paths", []),
                }
                status.update(
                    label=f"Exploração de temas — créditos da API indisponíveis, usado fallback offline ({elapsed:.1f}s)",
                    state="complete",
                    expanded=False,
                )
                st.warning(
                    "Créditos Anthropic atualmente insuficientes. Usando exploração inicial offline para você poder continuar.",
                    icon="⚠️",
                )
                st.session_state.step = "explored"
                st.rerun()

            status.update(label=f"Exploração de temas — FALHOU ({elapsed:.1f}s)", state="error")
            st.error(f"**Explorador de Temas** falhou: {e}")
            st.code(traceback.format_exc(), language="text")
            # Allow skipping exploration on failure
            if st.button("Pular exploração, ir direto para pesquisa de tendências"):
                st.session_state.step = "pipeline"
                st.session_state.current_phase = -1
                st.rerun()
    st.stop()

# ------------------------------------------------------------------
# STEP 3: Show exploration results, let user pick angles
# ------------------------------------------------------------------
if step == "explored":
    ctx = st.session_state.context
    exploration_mode = ctx.get("exploration_mode", st.session_state.exploration_mode)
    angles = st.session_state.exploration_angles
    paths = st.session_state.exploration_paths
    domain = st.session_state.exploration_domain

    _country_code = ctx.get("search_country", "worldwide")
    _country_label = COUNTRY_OPTIONS.get(_country_code, _country_code)
    st.markdown(f"> **Domínio:** {ctx['user_prompt']}  |  **Região:** {_country_label}")
    st.divider()

    st.subheader("Exploração de Temas")

    _no_results = False
    _is_builtin = ctx.get("_source") == "builtin"
    if exploration_mode == "online_trends":
        if not paths:
            _no_results = True
            st.warning(
                f"A varredura de tendências online não retornou caminhos para **{domain}**. "
                "Isso pode acontecer quando a busca web não encontra sinais relevantes para esse domínio. "
                "Tente reformular o tema, trocar a região, ou use o modo brainstorming rápido.",
                icon="⚠️",
            )
        else:
            if _is_builtin:
                st.info(
                    "ℹ️ Caminhos gerados a partir do conhecimento interno do Claude "
                    "(busca web indisponível ou sem resultados para este domínio)."
                )
            st.markdown(
                f"Encontrei **{len(paths)} caminhos amplo-para-estreito** "
                f"{'baseados no conhecimento interno' if _is_builtin else 'baseados em sinais online ao vivo'} "
                f"em **{domain}**. "
                "Escolha os caminhos que quer investigar primeiro."
            )
            # Render metrics dashboard for exploration paths
            exploration_output = st.session_state.get("exploration_output", {})
            if exploration_output:
                render_exploration_metrics(exploration_output)
    else:
        if not angles:
            _no_results = True
            st.warning(
                f"O brainstorming não retornou ângulos para **{domain}**. "
                "Tente reformular o tema ou trocar o modo de exploração.",
                icon="⚠️",
            )
        else:
            st.markdown(
                f"Encontrei **{len(angles)} ângulos** para explorar em **{domain}**. "
                f"Selecione os que te interessam — eles vão direcionar a pesquisa de tendências."
            )

    selected_labels = []

    if exploration_mode == "online_trends":
        grouped_paths: dict[str, list[tuple[int, dict]]] = {}
        for idx, path in enumerate(paths):
            broad = path.get("broad_area", "Other")
            grouped_paths.setdefault(broad, []).append((idx, path))

        MOMENTUM_COLORS = {"hot": "red", "warm": "orange", "cool": "blue"}

        for broad, broad_paths in grouped_paths.items():
            st.markdown(f"### 🌐 {broad}")
            for idx, path in broad_paths:
                mid = path.get("mid_area", "?")
                narrow = path.get("narrow_area", "?")
                momentum = path.get("momentum", "warm")
                momentum_color = MOMENTUM_COLORS.get(momentum, "gray")

                label = f"{broad} -> {mid} -> {narrow}"
                score = score_exploration_path(path)
                col_check, col_content, col_score = st.columns([0.05, 0.75, 0.20])
                with col_check:
                    checked = st.checkbox(
                        label,
                        key=f"path_{idx}",
                        label_visibility="collapsed",
                    )
                with col_content:
                    st.markdown(f"**{mid} -> {narrow}** :{momentum_color}[{momentum}]")
                    hypothesis = path.get("opportunity_hypothesis", "")
                    why_now = path.get("why_now", "")
                    if hypothesis:
                        st.markdown(f"**Hipótese de oportunidade:** {hypothesis}")
                    if why_now:
                        st.markdown(f"**Por que agora:** {why_now}")

                    signals = path.get("source_signals", [])
                    queries = path.get("starter_queries", [])
                    if signals or queries:
                        with st.expander("Sinais e consultas iniciais"):
                            for s in signals:
                                st.markdown(f"- {s}")
                            if queries:
                                st.markdown("**Consultas iniciais**")
                                for q in queries:
                                    st.markdown(f"- {q}")
                with col_score:
                    st.markdown("**Por que este caminho**")
                    st.caption(
                        " | ".join(
                            [
                                f"M {score['momentum']}/3",
                                f"Pain {score['buyer_pain']}/3",
                                f"Build {score['feasibility']}/3",
                            ]
                        )
                    )
                    st.metric("Total", f"{score['total']}/9")

                if checked:
                    selected_labels.append(label)
    else:
        # Group angles by category
        categories: dict[str, list] = {}
        for angle in angles:
            cat = angle.get("category", "other")
            categories.setdefault(cat, []).append(angle)

        CATEGORY_ICONS = {
            "technology": "💡", "audience": "👥", "pain_point": "🎯",
            "business_model": "💰", "regulation": "📋", "emerging_niche": "🌱",
        }
        HEAT_COLORS = {"hot": "red", "warm": "orange", "cool": "blue"}

        for cat, cat_angles in categories.items():
            icon = CATEGORY_ICONS.get(cat, "📌")
            st.markdown(f"### {icon} {cat.replace('_', ' ').title()}")

            for angle in cat_angles:
                title = angle.get("title", "?")
                desc = angle.get("description", "")
                heat = angle.get("heat_level", "warm")
                heat_color = HEAT_COLORS.get(heat, "gray")
                questions = angle.get("example_questions", [])

                col_check, col_content = st.columns([0.05, 0.95])
                with col_check:
                    checked = st.checkbox(
                        title,
                        key=f"angle_{title}",
                        label_visibility="collapsed",
                    )
                with col_content:
                    st.markdown(f"**{title}** :{heat_color}[{heat}]")
                    st.markdown(desc)
                    if questions:
                        with st.expander("Perguntas de pesquisa"):
                            for q in questions:
                                st.markdown(f"- {q}")

                if checked:
                    selected_labels.append(title)

    if not _no_results:
        st.divider()

        # Custom angle input
        custom_angle = st.text_input(
            "Adicione seu próprio ângulo (opcional)",
            placeholder="ex: dispositivos vestíveis para detecção de quedas em idosos",
            key="custom_angle",
        )

        # Summary of selection
        if selected_labels or custom_angle.strip():
            n_selected = len(selected_labels) + (1 if custom_angle.strip() else 0)
            st.info(f"**{n_selected} ângulo(s) selecionado(s).** Eles vão direcionar a pesquisa de tendências.")
    else:
        custom_angle = ""

    st.divider()
    if _no_results:
        st.subheader("O que fazer?")
    else:
        st.subheader("Pronto para prosseguir?")
    st.markdown("Escolha como continuar:")

    col1, col2, col3 = st.columns(3)

    if not _no_results:
        with col1:
            if st.button("Pesquisar áreas selecionadas", type="primary", use_container_width=True,
                          help="Executar pesquisa de tendências ao vivo focada nos seus ângulos selecionados."):
                # Build focused prompt from selections
                focus_parts = list(selected_labels)
                if custom_angle.strip():
                    focus_parts.append(custom_angle.strip())

                if focus_parts:
                    focused_prompt = (
                        f"{ctx['user_prompt']} — focando especificamente em: {'; '.join(focus_parts)}"
                    )
                else:
                    focused_prompt = ctx["user_prompt"]

                ctx["user_prompt"] = focused_prompt
                ctx["selected_exploration_angles"] = list(selected_labels)
                if custom_angle.strip():
                    ctx["selected_exploration_angles"].append(custom_angle.strip())
                st.session_state.context = ctx
                st.session_state.step = "pipeline"
                st.session_state.current_phase = -1
                st.rerun()

    with col2 if not _no_results else col1:
        if st.button(
            "Tentar novamente" if _no_results else "Explorar mais",
            type="primary" if _no_results else "secondary",
            use_container_width=True,
            help="Re-executar o explorador de temas para sugestões diferentes.",
        ):
            st.session_state.step = "exploring"
            st.rerun()

    with col3 if not _no_results else col2:
        if st.button("Pular para o pipeline", use_container_width=True,
                      help="Pular pesquisa de tendências e ir direto para descoberta de oportunidades."):
            ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
            st.session_state.context = ctx
            st.session_state.step = "pipeline"
            st.session_state.current_phase = 0  # skip phase 0, start at phase 1
            st.rerun()

    st.stop()


# ------------------------------------------------------------------
# STEP 4: Pipeline execution (phase-by-phase)
# ------------------------------------------------------------------
assert step == "pipeline"
ctx = st.session_state.context

_country_code = ctx.get("search_country", "worldwide")
_country_label = COUNTRY_OPTIONS.get(_country_code, _country_code)
st.markdown(f"> **Prompt:** {ctx.get('user_prompt', '')}  |  **Região:** {_country_label}")

# Show selected exploration angles if any
sel_angles = ctx.get("selected_exploration_angles", [])
if sel_angles:
    st.caption(f"Áreas de foco: {', '.join(sel_angles)}")
st.divider()

next_phase_idx = st.session_state.current_phase + 1

# Auto-run phase 0 when entering pipeline mode
if next_phase_idx == 0:
    ctx = run_single_phase(0, ctx)
    st.session_state.context = ctx
    if not ctx.pop("_phase_failed", False):
        st.session_state.current_phase = 0
        try:
            _checkpoint_session(ctx, 0)
        except Exception:
            pass
    st.rerun()

# -- Show completed phases as collapsed sections --
for i in range(next_phase_idx):
    phase = PHASES[i]
    renderer = RENDERERS.get(phase["key"])
    summarizer = SUMMARIZERS.get(phase["key"])
    summary = summarizer(ctx) if summarizer else ""

    with st.expander(f"Fase {phase['num']}: {phase['label']} — {summary[:80]}", expanded=False):
        if renderer:
            renderer(ctx)
        rerun_notes = st.text_input(
            "Orientação (opcional)",
            placeholder="ex: Focar em outro ângulo...",
            key=f"rerun_notes_phase_{i}",
        )
        if st.button(
            f"Re-executar Fase {phase['num']}: {phase['label']}",
            key=f"rerun_prev_phase_{i}",
            type="secondary",
            use_container_width=True,
        ):
            ctx = run_single_phase(i, ctx, rerun_notes)
            st.session_state.context = ctx
            if not ctx.pop("_phase_failed", False):
                st.session_state.current_phase = i
                try:
                    _checkpoint_session(ctx, i)
                except Exception:
                    pass
            st.rerun()

# -- Current phase results + next steps --
if 0 <= st.session_state.current_phase < TOTAL_PHASES:
    current_phase = PHASES[st.session_state.current_phase]
    summarizer = SUMMARIZERS.get(current_phase["key"])

    st.divider()
    st.subheader(f"Fase {current_phase['num']} Concluída: {current_phase['label']}")

    if summarizer:
        st.markdown(summarizer(ctx))

    renderer = RENDERERS.get(current_phase["key"])
    if renderer:
        with st.expander("Ver detalhes completos", expanded=True):
            renderer(ctx)

    # Next steps
    st.divider()
    st.subheader("Próximos passos?")

    options = get_next_options(current_phase["key"], ctx)

    if next_phase_idx < TOTAL_PHASES:
        next_p = PHASES[next_phase_idx]
        st.markdown(
            f"Próxima fase: **Fase {next_p['num']}: {next_p['label']}**. "
            f"Prossiga, re-execute ou adicione orientação."
        )

    # -- Concept selection for validation → architecture transition --
    selected_concept_from_ui = None
    if current_phase["key"] == "validation":
        vals = ctx.get("validations", [])
        eligible = [v for v in vals if v.get("recommendation") != "kill"]
        if eligible:
            rec_labels = {"proceed": "PROSSEGUIR", "pivot": "PIVOTAR"}
            rc = {"proceed": "🟢", "pivot": "🟡"}
            sorted_eligible = sorted(eligible, key=lambda x: x.get("overall_score", 0), reverse=True)
            concept_options = []
            for v in sorted_eligible:
                ref = v.get("concept_ref", "?")
                score = v.get("overall_score", 0)
                rec = v.get("recommendation", "?")
                icon = rc.get(rec, "⚪")
                rec_pt = rec_labels.get(rec, rec.upper())
                concept_options.append(f"{icon} {ref} — {score:.1f}/10 ({rec_pt})")

            st.markdown("**Selecione o conceito para arquitetar:**")
            chosen_label = st.radio(
                "Conceito",
                concept_options,
                index=0,
                key="concept_select",
                label_visibility="collapsed",
            )
            chosen_idx = concept_options.index(chosen_label)
            selected_concept_from_ui = sorted_eligible[chosen_idx].get("concept_ref")

    user_notes = st.text_area(
        "Adicionar orientação para a próxima fase (opcional)",
        placeholder="ex: Focar em B2B, orçamento de R$25k, preferir stack Python...",
        height=80,
        key=f"notes_{current_phase['key']}",
    )

    cols = st.columns(len(options))
    for col, opt in zip(cols, options):
        with col:
            clicked = st.button(
                opt["label"], help=opt.get("help", ""),
                type=opt.get("type", "secondary"),
                use_container_width=True,
                key=f"btn_{current_phase['key']}_{opt['action']}",
            )
            if clicked:
                action = opt["action"]

                if action == "next" and next_phase_idx < TOTAL_PHASES:
                    if selected_concept_from_ui:
                        ctx["selected_concept"] = selected_concept_from_ui
                    ctx = run_single_phase(next_phase_idx, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = next_phase_idx
                        try:
                            _checkpoint_session(ctx, next_phase_idx)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "rerun":
                    ctx = run_single_phase(st.session_state.current_phase, ctx, user_notes)
                    st.session_state.context = ctx
                    failed = ctx.pop("_phase_failed", None)
                    if not failed and st.session_state.current_phase >= 0:
                        try:
                            _checkpoint_session(ctx, st.session_state.current_phase)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "skip_trends":
                    ctx.update({"trends": [], "market_sentiment": "unknown", "key_takeaway": ""})
                    st.session_state.context = ctx
                    ctx = run_single_phase(next_phase_idx, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = next_phase_idx
                        try:
                            _checkpoint_session(ctx, next_phase_idx)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "back_to_ideation":
                    vals = ctx.get("validations", [])
                    feedback = []
                    for v in vals:
                        rec = v.get("recommendation", "")
                        if rec in ("kill", "pivot"):
                            feedback.append(f"{rec.upper()}: {v.get('concept_ref','?')}: {v.get('reasoning','')}")
                    ctx["validation_feedback"] = feedback
                    ctx = run_single_phase(2, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = 2
                        try:
                            _checkpoint_session(ctx, 2)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "restart_with_feedback":
                    review = ctx.get("critical_review", {})
                    ctx["critic_feedback"] = review.get("recommended_changes", [])
                    ctx["fatal_flaws"] = review.get("fatal_flaws", [])
                    ctx = run_single_phase(1, ctx, user_notes)
                    st.session_state.context = ctx
                    if not ctx.pop("_phase_failed", False):
                        st.session_state.current_phase = 1
                        try:
                            _checkpoint_session(ctx, 1)
                        except Exception:
                            pass
                    st.rerun()

                elif action == "generate_prompt":
                    prompt_text = build_claude_code_prompt(ctx)
                    st.divider()
                    st.subheader("Prompt para Claude Code")
                    st.info(
                        "Copie o prompt abaixo e cole no Claude Code para começar a desenvolver o projeto. "
                        "O prompt contém toda a análise do pipeline — contexto de negócio, arquitetura, "
                        "stack tecnológico, plano de execução e recomendações.",
                        icon="🚀",
                    )
                    st.code(prompt_text, language="markdown")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "Baixar prompt (.md)",
                            data=prompt_text,
                            file_name="fabrica_solucoes_prompt_claude_code.md",
                            mime="text/markdown",
                            key="download_prompt_md",
                        )
                    with dl_col2:
                        st.download_button(
                            "Baixar prompt (.txt)",
                            data=prompt_text,
                            file_name="fabrica_solucoes_prompt_claude_code.txt",
                            mime="text/plain",
                            key="download_prompt_txt",
                        )

                elif action == "export":
                    filepath = export_results(ctx)
                    session_path = save_session(ctx, st.session_state.current_phase, user_email=_USER_EMAIL)
                    st.success(f"Exportado para `{filepath}` — sessão salva no histórico.")
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "Baixar JSON",
                            data=json.dumps(ctx, indent=2, ensure_ascii=False, default=str),
                            file_name="fabrica_solucoes_resultado.json",
                            mime="application/json",
                            key="download_final_json",
                        )
                    with dl_col2:
                        try:
                            pdf_bytes = build_pdf_bytes(ctx)
                            st.download_button(
                                "Baixar PDF",
                                data=pdf_bytes,
                                file_name="fabrica_solucoes_relatorio.pdf",
                                mime="application/pdf",
                                key="download_final_pdf",
                            )
                        except Exception as pdf_err:
                            st.warning(f"Geração de PDF falhou: {pdf_err}")

                elif action == "reset":
                    for k, v in DEFAULTS.items():
                        st.session_state[k] = v
                    st.rerun()
