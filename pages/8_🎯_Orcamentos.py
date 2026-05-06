import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
from auth import require_login, sidebar_user
from db.queries import listar_orcamentos, salvar_orcamento, excluir_orcamento, listar_categorias

st.set_page_config(page_title="Orçamentos", page_icon="🎯", layout="wide")
uid = require_login()
sidebar_user()

st.title("🎯 Orçamentos por Categoria")

fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

hoje = datetime.date.today()
col_mes, col_copy = st.columns([2, 4])
with col_mes:
    mes_sel = st.text_input("Mês (AAAA-MM)", value=hoje.strftime("%Y-%m"), max_chars=7)

if len(mes_sel) != 7 or mes_sel[4] != "-":
    st.error("Informe o mês no formato AAAA-MM")
    st.stop()

df       = listar_orcamentos(mes_sel, user_id=uid)
cats_df  = listar_categorias(tipo="despesa", user_id=uid)

# ── Copiar orçamento de outro mês ─────────────────────────────────────────────
with col_copy:
    with st.expander("📋 Copiar orçamento de outro mês"):
        mes_origem = st.text_input("Mês de origem (AAAA-MM)", value="", max_chars=7, key="copy_from")
        if st.button("Copiar") and mes_origem and mes_origem != mes_sel:
            df_orig = listar_orcamentos(mes_origem, user_id=uid)
            copiados = 0
            for _, row in df_orig[df_orig["limite"] > 0].iterrows():
                salvar_orcamento(int(row["categoria_id"]), mes_sel, float(row["limite"]))
                copiados += 1
            if copiados:
                st.success(f"{copiados} categorias copiadas de {mes_origem}.")
                st.rerun()
            else:
                st.warning("Nenhum orçamento definido no mês de origem.")

# ── KPIs ──────────────────────────────────────────────────────────────────────
df_com_limite = df[df["limite"] > 0]
total_orcado  = df_com_limite["limite"].sum()
total_gasto   = df_com_limite["gasto"].sum()
total_livre   = total_orcado - total_gasto
estouradas    = (df_com_limite["gasto"] > df_com_limite["limite"]).sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total orçado",         fmt(total_orcado))
k2.metric("Total gasto",          fmt(total_gasto))
k3.metric("Saldo livre",          fmt(total_livre))
k4.metric("Categorias estouradas", int(estouradas))

st.markdown("---")

# ── Gráfico geral ─────────────────────────────────────────────────────────────
if not df_com_limite.empty:
    fig = go.Figure()
    cores_barra = ["#FF6B6B" if row["gasto"] > row["limite"] else "#00B894"
                   for _, row in df_com_limite.iterrows()]
    fig.add_trace(go.Bar(
        name="Gasto",
        x=df_com_limite["categoria"], y=df_com_limite["gasto"],
        marker_color=cores_barra,
        text=df_com_limite["gasto"].apply(fmt), textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="Limite",
        x=df_com_limite["categoria"], y=df_com_limite["limite"],
        mode="markers",
        marker=dict(symbol="line-ew", size=16, color="#FFEAA7",
                    line=dict(color="#FFEAA7", width=3)),
    ))
    fig.update_layout(
        title=f"Gastos vs Limite — {mes_sel}",
        xaxis_tickangle=-30, yaxis_title="R$",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=380,
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── Edição categoria a categoria ──────────────────────────────────────────────
st.subheader(f"Definir limites — {mes_sel}")

for _, row in df.iterrows():
    cat_id      = int(row["categoria_id"])
    limite_atual = float(row["limite"])
    gasto        = float(row["gasto"])
    pct          = float(row["pct"])

    with st.container():
        c1, c2, c3 = st.columns([3, 3, 2])
        with c1:
            st.markdown(f"**{row['categoria']}**")
            if limite_atual > 0:
                status = "🔴 Estourado" if gasto > limite_atual else f"🟢 {pct:.0f}% usado"
                st.caption(f"Gasto: {fmt(gasto)} / {fmt(limite_atual)}  ·  {status}")
                st.progress(pct / 100)
            else:
                st.caption(f"Gasto: {fmt(gasto)}  ·  _(sem limite definido)_")
        with c2:
            novo_limite = st.number_input(
                "Limite (R$)", min_value=0.0, step=50.0, format="%.2f",
                value=limite_atual, key=f"lim_{cat_id}",
                label_visibility="collapsed",
            )
        with c3:
            col_s, col_d = st.columns(2)
            if col_s.button("Salvar", key=f"sv_{cat_id}", type="primary"):
                if novo_limite > 0:
                    salvar_orcamento(cat_id, mes_sel, novo_limite)
                else:
                    excluir_orcamento(cat_id, mes_sel)
                st.rerun()
            if limite_atual > 0 and col_d.button("Remover", key=f"rm_{cat_id}"):
                excluir_orcamento(cat_id, mes_sel)
                st.rerun()
    st.divider()
