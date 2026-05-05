import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
from db.queries import (
    listar_parcelamentos, criar_parcelamento, registrar_pagamento,
    excluir_parcelamento, parcelas_a_vencer_por_mes,
    listar_categorias, listar_contas, get_ou_criar_conta,
)

st.set_page_config(page_title="Parcelamentos", page_icon="💳", layout="wide")
st.title("💳 Controle de Parcelamentos")

fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

cats_df = listar_categorias()
contas_df = listar_contas()

# ── KPIs ──────────────────────────────────────────────────────────────────────
df_ativos = listar_parcelamentos(apenas_ativos=True)
df_todos = listar_parcelamentos(apenas_ativos=False)

if not df_ativos.empty:
    total_restante = (df_ativos["total_parcelas"] - df_ativos["parcelas_pagas"]) * df_ativos["valor_parcela"]
    compromisso_mes = df_ativos["valor_parcela"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Parcelamentos ativos", len(df_ativos))
    k2.metric("Comprometido este mês", fmt(compromisso_mes))
    k3.metric("Total restante a pagar", fmt(total_restante.sum()))
    k4.metric("Total já quitado", len(df_todos) - len(df_ativos))
else:
    st.info("Nenhum parcelamento ativo no momento. Cadastre um abaixo.")

st.markdown("---")

# ── Gráfico: parcelas a vencer ────────────────────────────────────────────────
df_vencer = parcelas_a_vencer_por_mes(meses=12)
if not df_vencer.empty:
    st.subheader("Parcelas a Vencer (próximos 12 meses)")
    fig = px.bar(
        df_vencer, x="mes", y="total",
        labels={"mes": "Mês", "total": "R$"},
        color_discrete_sequence=["#A29BFE"],
        text_auto=".2s",
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

# ── Lista de parcelamentos ativos ─────────────────────────────────────────────
st.subheader("Parcelamentos Ativos")

if not df_ativos.empty:
    for _, p in df_ativos.iterrows():
        pagas = int(p["parcelas_pagas"])
        total = int(p["total_parcelas"])
        restantes = total - pagas
        progresso = pagas / total

        with st.container(border=True):
            col_info, col_prog, col_acoes = st.columns([3, 3, 2])

            with col_info:
                st.markdown(f"**{p['descricao']}**")
                st.caption(f"📂 {p['categoria'] or 'Sem categoria'}  •  🏦 {p.get('banco', '') or ''} {p.get('conta', '') or ''}")
                st.caption(f"Início: {pd.to_datetime(p['data_primeira_parcela']).strftime('%d/%m/%Y')}")

            with col_prog:
                st.progress(progresso, text=f"{pagas}/{total} parcelas pagas")
                st.markdown(
                    f"Parcela: **{fmt(p['valor_parcela'])}** · "
                    f"Restante: **{fmt(restantes * p['valor_parcela'])}** · "
                    f"Total: **{fmt(p['valor_total'])}**"
                )

            with col_acoes:
                novo_pagas = st.number_input(
                    "Parcelas pagas",
                    min_value=0, max_value=total,
                    value=pagas,
                    key=f"pagas_{p['id']}",
                    step=1,
                )
                c1, c2 = st.columns(2)
                if c1.button("Atualizar", key=f"upd_{p['id']}", type="primary"):
                    registrar_pagamento(int(p["id"]), novo_pagas)
                    st.rerun()
                if c2.button("Excluir", key=f"del_{p['id']}", type="secondary"):
                    excluir_parcelamento(int(p["id"]))
                    st.rerun()
else:
    st.caption("Nenhum parcelamento ativo.")

# ── Parcelamentos quitados ────────────────────────────────────────────────────
df_quitados = df_todos[df_todos["parcelas_pagas"] >= df_todos["total_parcelas"]] if not df_todos.empty else pd.DataFrame()
if not df_quitados.empty:
    with st.expander(f"✅ Quitados ({len(df_quitados)})"):
        for _, p in df_quitados.iterrows():
            col_i, col_b = st.columns([5, 1])
            col_i.markdown(f"~~{p['descricao']}~~ — {fmt(p['valor_total'])} em {p['total_parcelas']}x")
            if col_b.button("Excluir", key=f"del_q_{p['id']}"):
                excluir_parcelamento(int(p["id"]))
                st.rerun()

st.markdown("---")

# ── Cadastrar novo parcelamento ───────────────────────────────────────────────
st.subheader("Cadastrar Novo Parcelamento")

with st.form("novo_parcelamento", clear_on_submit=True):
    col1, col2 = st.columns(2)
    descricao = col1.text_input("Descrição *", placeholder="Ex: Geladeira, Notebook...")
    data_ini = col2.date_input("Data da 1ª parcela *", value=datetime.date.today())

    col3, col4, col5 = st.columns(3)
    valor_total = col3.number_input("Valor total (R$) *", min_value=0.01, step=10.0, format="%.2f")
    total_parcelas = col4.number_input("Nº de parcelas *", min_value=1, max_value=120, value=12, step=1)
    parcelas_pagas = col5.number_input("Parcelas já pagas", min_value=0, max_value=120, value=0, step=1)

    valor_parcela = valor_total / total_parcelas if total_parcelas else 0
    st.caption(f"Valor por parcela calculado: **{fmt(valor_parcela)}**")

    col6, col7 = st.columns(2)
    cat_opts = ["(nenhuma)"] + cats_df[cats_df["tipo"] == "despesa"]["nome"].tolist()
    cat_sel = col6.selectbox("Categoria", cat_opts)

    conta_opts = ["(nenhuma)"] + (
        (contas_df["banco"] + " — " + contas_df["nome"]).tolist() if not contas_df.empty else []
    )
    conta_sel = col7.selectbox("Conta", conta_opts)

    observacao = st.text_input("Observação (opcional)")

    if st.form_submit_button("💾 Cadastrar", type="primary"):
        if not descricao.strip():
            st.error("Informe a descrição.")
        elif valor_total <= 0:
            st.error("Informe o valor total.")
        else:
            cat_id = None
            if cat_sel != "(nenhuma)":
                cat_id = int(cats_df[cats_df["nome"] == cat_sel]["id"].iloc[0])

            conta_id = None
            if conta_sel != "(nenhuma)" and not contas_df.empty:
                idx = conta_opts.index(conta_sel) - 1
                conta_id = int(contas_df.iloc[idx]["id"])

            criar_parcelamento({
                "descricao": descricao.strip(),
                "valor_total": valor_total,
                "valor_parcela": round(valor_parcela, 2),
                "total_parcelas": int(total_parcelas),
                "parcelas_pagas": int(parcelas_pagas),
                "data_primeira_parcela": str(data_ini),
                "categoria_id": cat_id,
                "conta_id": conta_id,
                "observacao": observacao.strip() or None,
            })
            st.success(f"Parcelamento '{descricao}' cadastrado!")
            st.rerun()
