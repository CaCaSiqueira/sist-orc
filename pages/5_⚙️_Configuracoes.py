import streamlit as st
import pandas as pd
from db.queries import (
    listar_categorias, listar_categorias_arvore, criar_categoria,
    editar_categoria, excluir_categoria,
    listar_contas, criar_conta,
    listar_importacoes,
)

st.set_page_config(page_title="Configurações", page_icon="⚙️", layout="wide")
st.title("⚙️ Configurações")

tab_cats, tab_contas, tab_imports = st.tabs(["🏷️ Categorias", "🏦 Contas", "📁 Importações"])


# ── helpers ──────────────────────────────────────────────────────────────────
def _icone(tipo): return "🔴" if tipo == "despesa" else "🟢"


def _bloco_categoria(row, cats_df, filhos_map, nivel=0):
    """Renderiza uma categoria e seus filhos recursivamente."""
    id_ = int(row["id"])
    filhos = filhos_map.get(id_, [])
    prefixo = "↳ " if nivel > 0 else ""

    with st.expander(f"{_icone(row['tipo'])} {prefixo}{row['nome']}"
                     + (f"  _(pai: {row['parent_nome']})_" if row.get("parent_nome") else ""),
                     expanded=False):

        # ── Editar ───────────────────────────────────────────────────────────
        NATUREZA_OPTS = ["nao_classificado", "fixo", "variavel"]
        NATUREZA_LABELS = {"nao_classificado": "Não classificado", "fixo": "Fixo", "variavel": "Variável"}
        nat_atual = row.get("natureza") or "nao_classificado"
        with st.form(f"edit_{id_}"):
            c1, c2, c3 = st.columns([3, 2, 2])
            novo_nome  = c1.text_input("Nome", value=row["nome"])
            nova_cor   = c2.color_picker("Cor", value=row["cor"] or "#888888")
            nova_nat   = c3.selectbox(
                "Natureza",
                options=NATUREZA_OPTS,
                index=NATUREZA_OPTS.index(nat_atual) if nat_atual in NATUREZA_OPTS else 0,
                format_func=lambda x: NATUREZA_LABELS[x],
            )
            st.caption("Tipo não pode ser alterado aqui para não quebrar subcategorias.")
            col_s, col_d = st.columns(2)
            salvar  = col_s.form_submit_button("💾 Salvar")
            excluir = col_d.form_submit_button("🗑️ Excluir", type="secondary")

        if salvar:
            editar_categoria(id_, novo_nome, row["tipo"], nova_cor, nova_nat)
            st.success("Salvo!")
            st.rerun()
        if excluir:
            excluir_categoria(id_)
            st.rerun()

        # ── Nova subcategoria ─────────────────────────────────────────────────
        with st.form(f"sub_{id_}"):
            st.markdown("**➕ Nova subcategoria**")
            sub_nome = st.text_input("Nome da subcategoria", key=f"sub_nome_{id_}")
            sub_cor  = st.color_picker("Cor", "#888888", key=f"sub_cor_{id_}")
            if st.form_submit_button("Criar subcategoria"):
                if sub_nome.strip():
                    criar_categoria(sub_nome.strip(), row["tipo"], sub_cor, parent_id=id_)
                    st.success(f"Subcategoria '{sub_nome}' criada em '{row['nome']}'!")
                    st.rerun()
                else:
                    st.error("Informe o nome.")

    # ── Renderiza filhos ──────────────────────────────────────────────────────
    if filhos:
        with st.container():
            st.markdown(
                f"<div style='margin-left:{(nivel+1)*20}px'>",
                unsafe_allow_html=True,
            )
            for filho in sorted(filhos, key=lambda r: r["nome"]):
                _bloco_categoria(filho, cats_df, filhos_map, nivel + 1)
            st.markdown("</div>", unsafe_allow_html=True)


# ── Aba Categorias ────────────────────────────────────────────────────────────
with tab_cats:
    tipo_filtro = st.radio("Ver", ["Todas", "Despesas", "Receitas"], horizontal=True)
    tipo_map = {"Todas": None, "Despesas": "despesa", "Receitas": "receita"}
    tipo_sel = tipo_map[tipo_filtro]

    cats_df = listar_categorias(tipo_sel)
    pais, filhos_map = listar_categorias_arvore(tipo_sel)

    if not pais:
        st.info("Nenhuma categoria encontrada.")
    else:
        col_desp, col_rec = st.columns(2)
        pais_desp = [p for p in pais if p["tipo"] == "despesa"]
        pais_rec  = [p for p in pais if p["tipo"] == "receita"]

        with col_desp:
            if pais_desp:
                st.markdown("**Despesas**")
                for p in pais_desp:
                    _bloco_categoria(p, cats_df, filhos_map, nivel=0)

        with col_rec:
            if pais_rec:
                st.markdown("**Receitas**")
                for p in pais_rec:
                    _bloco_categoria(p, cats_df, filhos_map, nivel=0)

    st.markdown("---")

    # ── Nova categoria raiz ───────────────────────────────────────────────────
    st.subheader("Nova Categoria")
    _NAT_OPTS   = ["nao_classificado", "fixo", "variavel"]
    _NAT_LABELS = {"nao_classificado": "Não classificado", "fixo": "Fixo", "variavel": "Variável"}
    with st.form("nova_cat"):
        c1, c2, c3, c4 = st.columns(4)
        nome_novo = c1.text_input("Nome *")
        tipo_novo = c2.selectbox("Tipo", ["despesa", "receita"])
        nat_novo  = c3.selectbox("Natureza", _NAT_OPTS, format_func=lambda x: _NAT_LABELS[x])
        cor_nova  = c4.color_picker("Cor", "#888888")

        cats_todos = listar_categorias()
        opts_pai = ["(nenhum — categoria raiz)"] + cats_todos["nome"].tolist()
        pai_sel = st.selectbox("Subcategoria de", opts_pai,
                               help="Deixe em 'nenhum' para criar uma categoria principal.")

        if st.form_submit_button("Criar Categoria", type="primary"):
            if not nome_novo.strip():
                st.error("Informe um nome.")
            else:
                parent_id = None
                if pai_sel != "(nenhum — categoria raiz)":
                    match = cats_todos[cats_todos["nome"] == pai_sel]
                    if not match.empty:
                        parent_id = int(match.iloc[0]["id"])
                        tipo_novo = match.iloc[0]["tipo"]  # herda tipo do pai
                criar_categoria(nome_novo.strip(), tipo_novo, cor_nova, parent_id=parent_id, natureza=nat_novo)
                st.success(f"Categoria '{nome_novo}' criada!")
                st.rerun()


# ── Aba Contas ────────────────────────────────────────────────────────────────
with tab_contas:
    st.subheader("Contas Cadastradas")
    contas = listar_contas()
    if not contas.empty:
        st.dataframe(contas, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma conta cadastrada. As contas são criadas automaticamente ao importar extratos.")

    st.markdown("---")
    st.subheader("Adicionar Conta Manualmente")
    with st.form("nova_conta"):
        c1, c2, c3 = st.columns(3)
        nome_c  = c1.text_input("Nome da conta")
        banco_c = c2.selectbox("Banco", ["nubank", "mercado_pago", "bb", "outro"])
        tipo_c  = c3.selectbox("Tipo", ["conta_corrente", "cartao_credito", "poupanca", "carteira_digital"])
        if st.form_submit_button("Adicionar", type="primary"):
            if nome_c.strip():
                criar_conta(nome_c.strip(), banco_c, tipo_c)
                st.success("Conta adicionada!")
                st.rerun()


# ── Aba Importações ───────────────────────────────────────────────────────────
with tab_imports:
    st.subheader("Histórico de Importações")
    imports = listar_importacoes()
    if not imports.empty:
        st.dataframe(imports, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma importação realizada ainda.")
