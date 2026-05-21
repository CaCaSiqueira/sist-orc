import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import datetime
from auth import require_login, sidebar_user
from db.queries import (
    listar_transacoes, resumo_por_categoria, evolucao_mensal,
    resumo_por_natureza, evolucao_fixo_variavel,
    listar_parcelamentos, parcelas_a_vencer_por_mes,
    listar_investimentos, resumo_investimentos,
    listar_orcamentos,
)

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
uid = require_login()
sidebar_user()

st.title("📊 Dashboard")

hoje = datetime.date.today()

# ── Filtro de período ─────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    data_ini = st.date_input("De", value=None, key="dash_ini")
with col2:
    data_fim = st.date_input("Até", value=None, key="dash_fim")

ini_str = str(data_ini) if data_ini else None
fim_str = str(data_fim) if data_fim else None

df_transacoes = listar_transacoes({"data_inicio": ini_str, "data_fim": fim_str} if ini_str or fim_str else {}, user_id=uid)
df_cat = resumo_por_categoria(ini_str, fim_str, user_id=uid)
df_evolucao = evolucao_mensal(ini_str, fim_str, user_id=uid)

if df_transacoes.empty:
    st.info("Sem dados para o período selecionado.")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
receitas = df_transacoes[df_transacoes["tipo"] == "receita"]["valor"].sum()
despesas = df_transacoes[df_transacoes["tipo"] == "despesa"]["valor"].sum()
saldo = receitas - despesas
fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Receitas", fmt(receitas))
k2.metric("Despesas", fmt(despesas))
k3.metric("Saldo", fmt(saldo))
k4.metric("Transações", len(df_transacoes))

st.markdown("---")

# ── Evolução mensal ───────────────────────────────────────────────────────────
if not df_evolucao.empty:
    st.subheader("Evolução Mensal")
    fig_evo = px.bar(
        df_evolucao, x="mes", y="total", color="tipo",
        barmode="group",
        color_discrete_map={"receita": "#00B894", "despesa": "#FF6B6B"},
        labels={"mes": "Mês", "total": "R$", "tipo": "Tipo"},
        text_auto=".2s",
    )
    fig_evo.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_evo, use_container_width=True)

    pivot = df_evolucao.pivot_table(index="mes", columns="tipo", values="total", aggfunc="sum").fillna(0)
    pivot["saldo"] = pivot.get("receita", 0) - pivot.get("despesa", 0)
    pivot = pivot.reset_index()
    fig_saldo = px.line(
        pivot, x="mes", y="saldo", markers=True,
        labels={"mes": "Mês", "saldo": "Saldo (R$)"},
        title="Saldo Mensal",
        color_discrete_sequence=["#6C5CE7"],
    )
    fig_saldo.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_saldo, use_container_width=True)

st.markdown("---")

# ── Tortas: despesas e receitas por categoria ─────────────────────────────────
col_a, col_b = st.columns(2)
df_desp_cat = df_cat[df_cat["tipo"] == "despesa"].copy()
df_rec_cat  = df_cat[df_cat["tipo"] == "receita"].copy()

with col_a:
    st.subheader("Despesas por Categoria")
    if not df_desp_cat.empty:
        fig_pie = px.pie(
            df_desp_cat, values="total", names="categoria",
            color_discrete_sequence=px.colors.qualitative.Pastel, hole=0.4,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Sem despesas no período.")

with col_b:
    st.subheader("Receitas por Categoria")
    if not df_rec_cat.empty:
        fig_pie2 = px.pie(
            df_rec_cat, values="total", names="categoria",
            color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4,
        )
        fig_pie2.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_pie2, use_container_width=True)
    else:
        st.info("Sem receitas no período.")

st.markdown("---")

# ── Ranking de categorias ─────────────────────────────────────────────────────
st.subheader("Ranking de Categorias — Despesas")
if not df_desp_cat.empty:
    fig_bar = px.bar(
        df_desp_cat.sort_values("total", ascending=True),
        x="total", y="categoria", orientation="h",
        color="total", color_continuous_scale="Reds",
        labels={"total": "R$", "categoria": ""},
        text_auto=".2s",
    )
    fig_bar.update_coloraxes(showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Fixo vs Variável ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📌 Fixo vs Variável")

df_nat = resumo_por_natureza(ini_str, fim_str, user_id=uid)
df_nat_desp = df_nat[df_nat["tipo"] == "despesa"].copy() if not df_nat.empty else pd.DataFrame()

NAT_LABELS = {"fixo": "Fixo", "variavel": "Variável", "nao_classificado": "Não classificado"}
NAT_CORES  = {"fixo": "#45B7D1", "variavel": "#FDCB6E", "nao_classificado": "#B2BEC3"}

if not df_nat_desp.empty:
    df_nat_desp["label"] = df_nat_desp["natureza"].map(NAT_LABELS).fillna("Não classificado")
    total_fixo  = df_nat_desp[df_nat_desp["natureza"] == "fixo"]["total"].sum()
    total_var   = df_nat_desp[df_nat_desp["natureza"] == "variavel"]["total"].sum()
    total_nc    = df_nat_desp[df_nat_desp["natureza"] == "nao_classificado"]["total"].sum()
    total_desp_nat = total_fixo + total_var + total_nc

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Gastos Fixos", fmt(total_fixo),
              delta=f"{total_fixo/total_desp_nat*100:.1f}%" if total_desp_nat else "")
    n2.metric("Gastos Variáveis", fmt(total_var),
              delta=f"{total_var/total_desp_nat*100:.1f}%" if total_desp_nat else "")
    n3.metric("Não classificado", fmt(total_nc))
    n4.metric("Total despesas", fmt(total_desp_nat))

    col_nat1, col_nat2 = st.columns(2)
    with col_nat1:
        fig_nat_pie = px.pie(
            df_nat_desp, values="total", names="label",
            color="natureza",
            color_discrete_map={NAT_LABELS[k]: v for k, v in NAT_CORES.items()},
            hole=0.45, title="Proporção Fixo / Variável",
        )
        fig_nat_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_nat_pie, use_container_width=True)

    with col_nat2:
        df_evo_nat = evolucao_fixo_variavel(ini_str, fim_str, user_id=uid)
        if not df_evo_nat.empty:
            df_evo_nat["label"] = df_evo_nat["natureza"].map(NAT_LABELS).fillna("Não classificado")
            fig_nat_bar = px.bar(
                df_evo_nat, x="mes", y="total", color="label",
                barmode="stack",
                color_discrete_map={v: NAT_CORES[k] for k, v in NAT_LABELS.items()},
                labels={"mes": "Mês", "total": "R$", "label": "Natureza"},
                title="Evolução Fixo vs Variável por mês",
                text_auto=".2s",
            )
            fig_nat_bar.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_nat_bar, use_container_width=True)
else:
    st.info("Sem dados de despesas para o período.")

# ── Maiores despesas ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Maiores Despesas")
top_desp = df_transacoes[df_transacoes["tipo"] == "despesa"].nlargest(10, "valor")[
    ["data", "descricao", "valor", "categoria", "conta"]
].copy()
top_desp["valor"] = top_desp["valor"].apply(fmt)
st.dataframe(top_desp, use_container_width=True, hide_index=True)

# ── Parcelamentos ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("💳 Compras Parceladas")

df_parc = listar_parcelamentos(apenas_ativos=False, user_id=uid)

if df_parc.empty:
    st.info("Nenhum parcelamento cadastrado.")
else:
    df_ativos  = df_parc[df_parc["parcelas_pagas"] < df_parc["total_parcelas"]].copy()

    p1, p2, p3, p4 = st.columns(4)
    vp_ativos        = df_ativos["valor_total"] / df_ativos["total_parcelas"] if not df_ativos.empty else 0
    comprometido_mes = vp_ativos.sum() if not df_ativos.empty else 0
    total_restante   = ((df_ativos["total_parcelas"] - df_ativos["parcelas_pagas"]) * vp_ativos).sum() if not df_ativos.empty else 0
    total_pago       = (df_parc["parcelas_pagas"] * df_parc["valor_total"] / df_parc["total_parcelas"]).sum()
    p1.metric("Ativos", len(df_ativos))
    p2.metric("Comprometido/mês", fmt(comprometido_mes))
    p3.metric("Restante a pagar", fmt(total_restante))
    p4.metric("Total já pago", fmt(total_pago))

    col_esq, col_dir = st.columns([3, 2])
    with col_esq:
        df_vencer = parcelas_a_vencer_por_mes(meses=6, user_id=uid)
        if not df_vencer.empty:
            fig_v = px.bar(
                df_vencer, x="mes", y="total",
                labels={"mes": "Mês", "total": "R$"},
                title="Parcelas a Vencer — próximos 6 meses",
                color_discrete_sequence=["#A29BFE"], text_auto=".2s",
            )
            fig_v.update_layout(xaxis_tickangle=-45, showlegend=False)
            st.plotly_chart(fig_v, use_container_width=True)

    with col_dir:
        if not df_ativos.empty:
            _vp = df_ativos["valor_total"] / df_ativos["total_parcelas"]
            df_ativos["pago"]     = df_ativos["parcelas_pagas"] * _vp
            df_ativos["restante"] = (df_ativos["total_parcelas"] - df_ativos["parcelas_pagas"]) * _vp
            fig_prog = go.Figure()
            fig_prog.add_trace(go.Bar(
                name="Pago", y=df_ativos["descricao"], x=df_ativos["pago"],
                orientation="h", marker_color="#00B894",
                text=df_ativos["pago"].apply(fmt), textposition="inside",
            ))
            fig_prog.add_trace(go.Bar(
                name="Restante", y=df_ativos["descricao"], x=df_ativos["restante"],
                orientation="h", marker_color="#FF6B6B",
                text=df_ativos["restante"].apply(fmt), textposition="inside",
            ))
            fig_prog.update_layout(
                barmode="stack", title="Progresso dos Parcelamentos",
                xaxis_title="R$", yaxis_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                height=max(250, len(df_ativos) * 55),
            )
            st.plotly_chart(fig_prog, use_container_width=True)

# ── Investimentos ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📈 Investimentos")

df_inv = listar_investimentos(apenas_ativos=True, user_id=uid)

if df_inv.empty:
    st.info("Nenhum investimento cadastrado.")
else:
    total_inv   = df_inv["valor_investido"].sum()
    total_atual = df_inv["valor_atual"].sum()
    rendimento  = total_atual - total_inv
    rent_pct    = (rendimento / total_inv * 100) if total_inv else 0

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Total investido", fmt(total_inv))
    i2.metric("Valor atual", fmt(total_atual))
    i3.metric("Rendimento", fmt(rendimento), delta=f"{rent_pct:+.2f}%")
    i4.metric("Ativos", len(df_inv))

    CORES_TIPO = {
        "Renda Fixa": "#00B894", "CDB": "#00CEC9", "LCI/LCA": "#55EFC4",
        "Tesouro Direto": "#6C5CE7", "Ações": "#FDCB6E", "FII": "#E17055",
        "Crypto": "#A29BFE", "Poupança": "#74B9FF", "Outros": "#B2BEC3",
    }
    col_inv1, col_inv2 = st.columns(2)
    with col_inv1:
        df_resumo_inv = resumo_investimentos(user_id=uid)
        fig_inv_pie = px.pie(
            df_resumo_inv, values="total_atual", names="tipo",
            title="Distribuição por tipo", hole=0.45,
            color="tipo", color_discrete_map=CORES_TIPO,
        )
        fig_inv_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_inv_pie, use_container_width=True)

    with col_inv2:
        df_inv["rendimento"] = df_inv["valor_atual"] - df_inv["valor_investido"]
        fig_inv_bar = go.Figure()
        fig_inv_bar.add_trace(go.Bar(name="Investido", x=df_inv["nome"], y=df_inv["valor_investido"], marker_color="#74B9FF"))
        fig_inv_bar.add_trace(go.Bar(name="Atual",     x=df_inv["nome"], y=df_inv["valor_atual"],     marker_color="#00B894"))
        fig_inv_bar.update_layout(barmode="group", title="Investido vs Atual", xaxis_title="", yaxis_title="R$", xaxis_tickangle=-30)
        st.plotly_chart(fig_inv_bar, use_container_width=True)

# ── Orçamentos ────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🎯 Orçamento do Mês")

mes_orc = hoje.strftime("%Y-%m")
df_orc = listar_orcamentos(mes_orc, user_id=uid)
df_orc_com_limite = df_orc[df_orc["limite"] > 0]

if df_orc_com_limite.empty:
    st.info(f"Nenhum limite definido para {mes_orc}. Acesse 🎯 Orçamentos para configurar.")
else:
    orcado    = df_orc_com_limite["limite"].sum()
    gasto_orc = df_orc_com_limite["gasto"].sum()
    livre     = orcado - gasto_orc
    estouradas = (df_orc_com_limite["gasto"] > df_orc_com_limite["limite"]).sum()

    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Total orçado", fmt(orcado))
    o2.metric("Total gasto", fmt(gasto_orc))
    o3.metric("Saldo livre", fmt(livre))
    o4.metric("Categorias estouradas", int(estouradas))

    cores = ["#FF6B6B" if row["gasto"] > row["limite"] else "#00B894"
             for _, row in df_orc_com_limite.iterrows()]
    fig_orc = go.Figure()
    fig_orc.add_trace(go.Bar(
        name="Gasto", x=df_orc_com_limite["categoria"], y=df_orc_com_limite["gasto"],
        marker_color=cores,
        text=df_orc_com_limite["gasto"].apply(fmt), textposition="outside",
    ))
    fig_orc.add_trace(go.Scatter(
        name="Limite", x=df_orc_com_limite["categoria"], y=df_orc_com_limite["limite"],
        mode="markers",
        marker=dict(symbol="line-ew", size=18, color="#FFEAA7", line=dict(color="#FFEAA7", width=3)),
    ))
    fig_orc.update_layout(
        xaxis_tickangle=-30, yaxis_title="R$",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=360, margin=dict(t=10),
    )
    st.plotly_chart(fig_orc, use_container_width=True)

    col_a, col_b = st.columns(2)
    metade = len(df_orc_com_limite) // 2
    for idx, (_, row) in enumerate(df_orc_com_limite.iterrows()):
        pct = float(row["pct"]) / 100
        estourou = row["gasto"] > row["limite"]
        col = col_a if idx < metade else col_b
        with col:
            label = f"{'🔴' if estourou else '🟢'} **{row['categoria']}** — {fmt(row['gasto'])} / {fmt(row['limite'])}"
            st.markdown(label)
            st.progress(min(pct, 1.0))
