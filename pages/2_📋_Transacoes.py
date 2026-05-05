import streamlit as st
import pandas as pd
from db.queries import (
    listar_transacoes, listar_categorias, opcoes_categoria,
    listar_contas, atualizar_transacao, excluir_transacao,
)

st.set_page_config(page_title="Transações", page_icon="📋", layout="wide")
st.title("📋 Transações")

cats_df = listar_categorias()
contas_df = listar_contas()
todas_labels, cat_label_to_id = opcoes_categoria()

# ── Filtros ──────────────────────────────────────────────────────────────────
with st.expander("🔍 Filtros", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        data_ini = st.date_input("De", value=None)
    with col2:
        data_fim = st.date_input("Até", value=None)
    with col3:
        tipo_f = st.selectbox("Tipo", ["Todos", "despesa", "receita"])
    with col4:
        cat_opts = ["Todas"] + todas_labels
        cat_f = st.selectbox("Categoria", cat_opts, help="↳ = subcategoria")

filtros = {}
if data_ini:
    filtros["data_inicio"] = str(data_ini)
if data_fim:
    filtros["data_fim"] = str(data_fim)
if tipo_f != "Todos":
    filtros["tipo"] = tipo_f
if cat_f != "Todas":
    filtros["categoria_id"] = cat_label_to_id.get(cat_f)

df = listar_transacoes(filtros)

if df.empty:
    st.info("Nenhuma transação encontrada com os filtros aplicados.")
    st.stop()

# ── Resumo rápido ─────────────────────────────────────────────────────────────
r, d = df[df["tipo"] == "receita"]["valor"].sum(), df[df["tipo"] == "despesa"]["valor"].sum()
c1, c2, c3 = st.columns(3)
fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
c1.metric("Receitas", fmt(r))
c2.metric("Despesas", fmt(d))
c3.metric("Saldo", fmt(r - d))

st.markdown("---")

# ── Tabela editável ──────────────────────────────────────────────────────────
st.subheader(f"{len(df)} transações")

display = df.copy()
display["valor_fmt"] = display.apply(
    lambda r: f"+{fmt(r['valor'])}" if r["tipo"] == "receita" else f"-{fmt(r['valor'])}", axis=1
)

edited = st.data_editor(
    display[["id", "data", "descricao", "valor_fmt", "tipo", "categoria", "conta", "banco", "observacao"]],
    column_config={
        "id": None,
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "valor_fmt": st.column_config.TextColumn("Valor", disabled=True),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=["despesa", "receita"]),
        "categoria": st.column_config.SelectboxColumn(
            "Categoria",
            options=todas_labels,
            help="↳ = subcategoria",
        ),
        "conta": st.column_config.TextColumn("Conta", disabled=True),
        "banco": st.column_config.TextColumn("Banco", disabled=True),
        "observacao": st.column_config.TextColumn("Obs."),
    },
    hide_index=True,
    use_container_width=True,
)

if st.button("💾 Salvar alterações"):
    for i, row in edited.iterrows():
        orig = display.iloc[i]
        tid = int(orig["id"])
        if row["descricao"] != orig["descricao"]:
            atualizar_transacao(tid, "descricao", row["descricao"])
        if row["tipo"] != orig["tipo"]:
            atualizar_transacao(tid, "tipo", row["tipo"])
        if row.get("categoria") != orig.get("categoria"):
            nova_cat_id = cat_label_to_id.get(row.get("categoria"))
            atualizar_transacao(tid, "categoria_id", nova_cat_id)
        if str(row.get("observacao", "")) != str(orig.get("observacao", "")):
            atualizar_transacao(tid, "observacao", row.get("observacao"))
    st.success("Alterações salvas!")
    st.rerun()

# ── Excluir ───────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("🗑️ Excluir transação"):
    id_excluir = st.number_input("ID da transação", min_value=1, step=1)
    if st.button("Excluir", type="secondary"):
        excluir_transacao(int(id_excluir))
        st.success(f"Transação {id_excluir} excluída.")
        st.rerun()
