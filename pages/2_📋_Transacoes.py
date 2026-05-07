import streamlit as st
import pandas as pd
from auth import require_login, sidebar_user
from db.queries import (
    listar_transacoes, listar_categorias, opcoes_categoria,
    listar_contas, atualizar_transacao, excluir_transacao,
)

st.set_page_config(page_title="Transações", page_icon="📋", layout="wide")
uid = require_login()
sidebar_user()

st.title("📋 Transações")

cats_df = listar_categorias(user_id=uid)
contas_df = listar_contas(user_id=uid)
todas_labels, cat_label_to_id = opcoes_categoria(user_id=uid)

# ── Filtros ──────────────────────────────────────────────────────────────────
def _limpar_filtros():
    for k in ("f_data_ini", "f_data_fim"):
        st.session_state.pop(k, None)
    st.session_state.update(f_tipo="Todos", f_cat="Todas", f_busca="")
    st.session_state.pop("filtros_aplicados", None)

with st.expander("🔍 Filtros", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        data_ini = st.date_input("De", value=None, key="f_data_ini")
    with col2:
        data_fim = st.date_input("Até", value=None, key="f_data_fim")
    with col3:
        tipo_f = st.selectbox("Tipo", ["Todos", "despesa", "receita"], key="f_tipo")
    with col4:
        cat_opts = ["Todas"] + todas_labels
        cat_f = st.selectbox("Categoria", cat_opts, help="↳ = subcategoria", key="f_cat")
    c_busca, c_aplicar, c_limpar = st.columns([4, 1, 1])
    with c_busca:
        busca = st.text_input("Buscar descrição", placeholder="Ex: mercado, salário...", key="f_busca")
    with c_aplicar:
        st.write("")
        aplicar = st.button("🔍 Filtrar", type="primary", use_container_width=True)
    with c_limpar:
        st.write("")
        st.button("✖ Limpar", on_click=_limpar_filtros, use_container_width=True)

if aplicar:
    st.session_state["filtros_aplicados"] = {
        "data_ini": data_ini,
        "data_fim": data_fim,
        "tipo": tipo_f,
        "cat": cat_f,
        "busca": busca.strip() if busca else "",
    }

fa = st.session_state.get("filtros_aplicados", {})
filtros = {}
if fa.get("data_ini"):
    filtros["data_inicio"] = str(fa["data_ini"])
if fa.get("data_fim"):
    filtros["data_fim"] = str(fa["data_fim"])
if fa.get("tipo", "Todos") != "Todos":
    filtros["tipo"] = fa["tipo"]
if fa.get("cat", "Todas") != "Todas":
    cat_id = cat_label_to_id.get(fa["cat"])
    if cat_id is not None:
        filtros["categoria_id"] = cat_id
if fa.get("busca"):
    filtros["busca"] = fa["busca"]

df = listar_transacoes(filtros, user_id=uid)

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
