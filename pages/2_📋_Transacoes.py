import streamlit as st
import pandas as pd
from auth import require_login, sidebar_user, is_admin
from db.queries import (
    listar_transacoes, listar_categorias, opcoes_categoria,
    listar_contas, atualizar_transacao, excluir_transacao,
    remover_transacoes_duplicadas,
)


st.set_page_config(page_title="Transações", page_icon="📋", layout="wide")
uid = require_login()
sidebar_user()

st.title("📋 Transações")

# ── Limpeza de duplicatas (admin) ─────────────────────────────────────────────
if is_admin(uid):
    with st.expander("🛠️ Ferramentas de manutenção", expanded=False):
        st.caption("Use apenas se houver transações duplicadas na listagem.")
        if st.button("🗑️ Remover transações duplicadas", type="secondary"):
            removidos = remover_transacoes_duplicadas(user_id=uid)
            if removidos:
                st.success(f"✅ {removidos} transação(ões) duplicada(s) removida(s)!")
                st.rerun()
            else:
                st.info("Nenhuma duplicata encontrada.")

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
    sel = cat_label_to_id.get(fa["cat"])
    if sel:
        if sel["type"] == "subcategoria":
            filtros["subcategoria_id"] = sel["id"]
        else:
            filtros["categoria_id"] = sel["id"]
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
display["data"] = pd.to_datetime(display["data"], errors="coerce").dt.date
display["valor_fmt"] = display.apply(
    lambda r: f"+{fmt(r['valor'])}" if r["tipo"] == "receita" else f"-{fmt(r['valor'])}", axis=1
)
display["excluir"] = False   # coluna de seleção para exclusão

edited = st.data_editor(
    display[["excluir", "id", "data", "descricao", "valor_fmt", "tipo", "categoria", "conta", "banco", "observacao"]],
    column_config={
        "excluir":    st.column_config.CheckboxColumn("🗑️", width="small", help="Marque para excluir"),
        "id":         None,
        "data":       st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao":  st.column_config.TextColumn("Descrição", width="large"),
        "valor_fmt":  st.column_config.TextColumn("Valor", disabled=True),
        "tipo":       st.column_config.SelectboxColumn("Tipo", options=["despesa", "receita"]),
        "categoria":  st.column_config.SelectboxColumn("Categoria", options=todas_labels, help="↳ = subcategoria"),
        "conta":      st.column_config.TextColumn("Conta", disabled=True),
        "banco":      st.column_config.TextColumn("Banco", disabled=True),
        "observacao": st.column_config.TextColumn("Obs."),
    },
    hide_index=True,
    use_container_width=True,
)

# ── Barra de ações ────────────────────────────────────────────────────────────
selecionadas_excluir = edited[edited["excluir"] == True]
col_salvar, col_excluir, col_info = st.columns([2, 2, 4])

with col_salvar:
    if st.button("💾 Salvar alterações", use_container_width=True):
        for i, row in edited.iterrows():
            orig = display.iloc[i]
            tid = int(orig["id"])
            if row["descricao"] != orig["descricao"]:
                atualizar_transacao(tid, "descricao", row["descricao"])
            if row["tipo"] != orig["tipo"]:
                atualizar_transacao(tid, "tipo", row["tipo"])
            if row.get("categoria") != orig.get("categoria"):
                nova_sel = cat_label_to_id.get(row.get("categoria"))
                if nova_sel:
                    if nova_sel["type"] == "subcategoria":
                        atualizar_transacao(tid, "categoria_id", nova_sel["cat_id"])
                        atualizar_transacao(tid, "subcategoria_id", nova_sel["id"])
                    else:
                        atualizar_transacao(tid, "categoria_id", nova_sel["id"])
                        atualizar_transacao(tid, "subcategoria_id", None)
            if str(row.get("observacao", "")) != str(orig.get("observacao", "")):
                atualizar_transacao(tid, "observacao", row.get("observacao"))
        st.success("Alterações salvas!")
        st.rerun()

with col_excluir:
    qtd = len(selecionadas_excluir)
    btn_label = f"🗑️ Excluir {qtd} selecionada(s)" if qtd else "🗑️ Excluir selecionadas"
    if st.button(btn_label, disabled=qtd == 0, type="secondary", use_container_width=True):
        st.session_state["_confirmar_exclusao"] = True

with col_info:
    if qtd:
        st.caption(f"⚠️ {qtd} transação(ões) marcada(s) para exclusão. Clique no botão para confirmar.")

# ── Confirmação de exclusão ───────────────────────────────────────────────────
if st.session_state.get("_confirmar_exclusao") and len(selecionadas_excluir) > 0:
    ids_excluir = [int(display.iloc[i]["id"]) for i in selecionadas_excluir.index]
    st.warning(f"⚠️ Tem certeza que deseja excluir **{len(ids_excluir)} transação(ões)**? Esta ação não pode ser desfeita.")
    c1, c2, _ = st.columns([1, 1, 4])
    if c1.button("✅ Sim, excluir", type="primary"):
        for tid in ids_excluir:
            excluir_transacao(tid)
        st.session_state.pop("_confirmar_exclusao", None)
        st.success(f"{len(ids_excluir)} transação(ões) excluída(s)!")
        st.rerun()
    if c2.button("❌ Cancelar"):
        st.session_state.pop("_confirmar_exclusao", None)
        st.rerun()
