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

cats_df    = listar_categorias(user_id=uid)
contas_df  = listar_contas(user_id=uid)
todas_labels, cat_label_to_id = opcoes_categoria(user_id=uid)

fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ── Filtros ───────────────────────────────────────────────────────────────────
def _limpar_filtros():
    for k in ("f_data_ini", "f_data_fim"):
        st.session_state.pop(k, None)
    st.session_state.update(f_tipo="Todos", f_cat="Todas", f_busca="")
    st.session_state.pop("filtros_aplicados", None)

with st.expander("🔍 Filtros", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    data_ini = col1.date_input("De",    value=None, key="f_data_ini")
    data_fim = col2.date_input("Até",   value=None, key="f_data_fim")
    tipo_f   = col3.selectbox("Tipo",   ["Todos", "despesa", "receita"], key="f_tipo")
    cat_f    = col4.selectbox("Categoria", ["Todas"] + todas_labels,
                              help="↳ = subcategoria", key="f_cat")
    c_busca, c_aplicar, c_limpar = st.columns([4, 1, 1])
    busca = c_busca.text_input("Buscar descrição", placeholder="Ex: mercado, salário...", key="f_busca")
    c_aplicar.write("")
    aplicar = c_aplicar.button("🔍 Filtrar", type="primary", use_container_width=True)
    c_limpar.write("")
    c_limpar.button("✖ Limpar", on_click=_limpar_filtros, use_container_width=True)

if aplicar:
    st.session_state["filtros_aplicados"] = {
        "data_ini": data_ini, "data_fim": data_fim,
        "tipo": tipo_f, "cat": cat_f,
        "busca": busca.strip() if busca else "",
    }
    st.session_state.pop("_selecionadas", None)

fa = st.session_state.get("filtros_aplicados", {})
filtros = {}
if fa.get("data_ini"):   filtros["data_inicio"]  = str(fa["data_ini"])
if fa.get("data_fim"):   filtros["data_fim"]      = str(fa["data_fim"])
if fa.get("tipo", "Todos") != "Todos": filtros["tipo"] = fa["tipo"]
if fa.get("cat",  "Todas") != "Todas":
    sel = cat_label_to_id.get(fa["cat"])
    if sel:
        if sel["type"] == "subcategoria": filtros["subcategoria_id"] = sel["id"]
        else:                             filtros["categoria_id"]    = sel["id"]
if fa.get("busca"): filtros["busca"] = fa["busca"]

df = listar_transacoes(filtros, user_id=uid)

if df.empty:
    st.info("Nenhuma transação encontrada com os filtros aplicados.")
    st.stop()

# ── Resumo ────────────────────────────────────────────────────────────────────
r = df[df["tipo"] == "receita"]["valor"].sum()
d = df[df["tipo"] == "despesa"]["valor"].sum()
c1, c2, c3 = st.columns(3)
c1.metric("Receitas",  fmt(r))
c2.metric("Despesas",  fmt(d))
c3.metric("Saldo",     fmt(r - d))

st.markdown("---")

# ── Prepara display ───────────────────────────────────────────────────────────
display = df.copy()
display["data"]      = pd.to_datetime(display["data"], errors="coerce").dt.date
display["valor_fmt"] = display.apply(
    lambda r: f"+{fmt(r['valor'])}" if r["tipo"] == "receita" else f"-{fmt(r['valor'])}", axis=1
)

# Mantém seleção entre reruns via session_state
if "tx_sel" not in st.session_state:
    st.session_state["tx_sel"] = set()

n = len(display)
st.subheader(f"{n} transações")

# ── Barra superior: Selecionar todas / Excluir ────────────────────────────────
col_sel_all, col_desmarcar, col_spacer, col_excluir_btn = st.columns([2, 2, 3, 3])

if col_sel_all.button("☑️ Selecionar todas", use_container_width=True):
    st.session_state["tx_sel"] = set(display["id"].astype(int).tolist())
    st.rerun()

if col_desmarcar.button("⬜ Desmarcar todas", use_container_width=True):
    st.session_state["tx_sel"] = set()
    st.rerun()

qtd_sel = len(st.session_state["tx_sel"])
with col_excluir_btn:
    lbl = f"🗑️ Excluir {qtd_sel} selecionada(s)" if qtd_sel else "🗑️ Excluir selecionadas"
    excluir_btn = st.button(lbl, disabled=(qtd_sel == 0),
                            type="secondary", use_container_width=True)

# ── Confirmação de exclusão ───────────────────────────────────────────────────
if excluir_btn and qtd_sel > 0:
    st.session_state["_confirmar_exclusao"] = True

if st.session_state.get("_confirmar_exclusao"):
    ids_del = list(st.session_state["tx_sel"])
    st.warning(
        f"⚠️ Tem certeza que deseja excluir **{len(ids_del)} transação(ões)**? "
        f"Esta ação **não pode ser desfeita**."
    )
    c_sim, c_nao, _ = st.columns([1, 1, 4])
    if c_sim.button("✅ Sim, excluir", type="primary"):
        for tid in ids_del:
            excluir_transacao(int(tid))
        st.session_state["tx_sel"] = set()
        st.session_state.pop("_confirmar_exclusao", None)
        st.success(f"{len(ids_del)} transação(ões) excluída(s)!")
        st.rerun()
    if c_nao.button("❌ Cancelar"):
        st.session_state.pop("_confirmar_exclusao", None)
        st.rerun()

# ── Tabela com checkboxes ─────────────────────────────────────────────────────
display["✓"] = display["id"].apply(lambda i: int(i) in st.session_state["tx_sel"])

edited = st.data_editor(
    display[["✓", "id", "data", "descricao", "valor_fmt", "tipo", "categoria", "conta", "banco", "observacao"]],
    column_config={
        "✓":          st.column_config.CheckboxColumn("✓", width="small"),
        "id":         None,
        "data":       st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao":  st.column_config.TextColumn("Descrição", width="large"),
        "valor_fmt":  st.column_config.TextColumn("Valor", disabled=True),
        "tipo":       st.column_config.SelectboxColumn("Tipo", options=["despesa", "receita"]),
        "categoria":  st.column_config.SelectboxColumn("Categoria", options=todas_labels),
        "conta":      st.column_config.TextColumn("Conta", disabled=True),
        "banco":      st.column_config.TextColumn("Banco", disabled=True),
        "observacao": st.column_config.TextColumn("Obs."),
    },
    hide_index=True,
    use_container_width=True,
    key="tx_editor",
)

# Atualiza seleção a partir dos checkboxes marcados na tabela
nova_sel = set()
for i, row in edited.iterrows():
    if row["✓"]:
        nova_sel.add(int(display.iloc[i]["id"]))
if nova_sel != st.session_state["tx_sel"]:
    st.session_state["tx_sel"] = nova_sel
    st.rerun()

# ── Salvar edições de categoria / observação ──────────────────────────────────
if st.button("💾 Salvar alterações", use_container_width=False):
    for i, row in edited.iterrows():
        orig = display.iloc[i]
        tid  = int(orig["id"])
        if row["descricao"] != orig["descricao"]:
            atualizar_transacao(tid, "descricao", row["descricao"])
        if row["tipo"] != orig["tipo"]:
            atualizar_transacao(tid, "tipo", row["tipo"])
        if row.get("categoria") != orig.get("categoria"):
            nova_sel_cat = cat_label_to_id.get(row.get("categoria"))
            if nova_sel_cat:
                if nova_sel_cat["type"] == "subcategoria":
                    atualizar_transacao(tid, "categoria_id",    nova_sel_cat["cat_id"])
                    atualizar_transacao(tid, "subcategoria_id", nova_sel_cat["id"])
                else:
                    atualizar_transacao(tid, "categoria_id",    nova_sel_cat["id"])
                    atualizar_transacao(tid, "subcategoria_id", None)
        if str(row.get("observacao", "")) != str(orig.get("observacao", "")):
            atualizar_transacao(tid, "observacao", row.get("observacao"))
    st.success("Alterações salvas!")
    st.rerun()
