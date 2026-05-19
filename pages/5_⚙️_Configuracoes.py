import streamlit as st
import pandas as pd
from auth import require_login, sidebar_user, is_admin
from db.queries import (
    listar_categorias, listar_categorias_arvore, criar_categoria,
    editar_categoria, excluir_categoria,
    editar_subcategoria, excluir_subcategoria,
    listar_contas, criar_conta,
    listar_importacoes,
    criar_usuario, listar_usuarios, excluir_usuario, email_cadastrado,
)

st.set_page_config(page_title="Configurações", page_icon="⚙️", layout="wide")
uid = require_login()
sidebar_user()

st.title("⚙️ Configurações")

_tabs = ["🏷️ Categorias", "🏦 Contas", "📁 Importações"]
if is_admin(uid):
    _tabs.append("👥 Usuários")

_tab_results = st.tabs(_tabs)
tab_cats   = _tab_results[0]
tab_contas = _tab_results[1]
tab_imports = _tab_results[2]
tab_users  = _tab_results[3] if is_admin(uid) else None

_NAT_OPTS   = ["nao_classificado", "fixo", "variavel"]
_NAT_LABELS = {"nao_classificado": "Não classificado", "fixo": "Fixo", "variavel": "Variável"}


def _cor_badge(cor, nome, pequeno=False):
    size = "10px" if pequeno else "13px"
    pad  = "2px 8px" if pequeno else "3px 10px"
    return (
        f"<span style='background:{cor};color:#fff;border-radius:12px;"
        f"padding:{pad};font-size:{size};font-weight:600'>{nome}</span>"
    )


def _bloco_categoria(row, filhos_map):
    id_    = int(row["id"])
    cor    = row["cor"] or "#888888"
    filhos = filhos_map.get(id_, [])
    icone  = "🔴" if row["tipo"] == "despesa" else "🟢"
    nat    = _NAT_LABELS.get(row.get("natureza", "nao_classificado"), "")

    n_subs    = len(filhos)
    subs_label = f"{n_subs} subcategoria{'s' if n_subs != 1 else ''}"

    # ── Cabeçalho do card (categoria pai) ────────────────────────────────────
    st.markdown(
        f"""<div style="border:1px solid {cor}55;border-left:4px solid {cor};
            border-radius:10px 10px {'0 0' if filhos else '10px 10px'};
            background:linear-gradient(90deg,{cor}22 0%,#1a1a2e 70%);
            display:flex;align-items:center;gap:10px;padding:10px 14px;
            margin-bottom:0">
            <span style="font-size:17px">{icone}</span>
            <span style="font-size:15px;font-weight:700;color:#fff;flex:1">{row['nome']}</span>
            {_cor_badge(cor, nat, pequeno=True)}
            <span style="font-size:11px;color:#888;white-space:nowrap">{subs_label}</span>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Subcategorias (dentro do mesmo card visualmente) ─────────────────────
    for i, filho in enumerate(sorted(filhos, key=lambda r: r["nome"])):
        is_last  = i == len(filhos) - 1
        conector = "└─" if is_last else "├─"
        cor_f    = filho["cor"] or "#888888"
        nat_f    = _NAT_LABELS.get(filho.get("natureza", "nao_classificado"), "")
        radius   = "0 0 10px 10px" if is_last else "0"
        st.markdown(
            f"""<div style="border-left:4px solid {cor};border-right:1px solid {cor}55;
                border-bottom:1px solid {cor}{'33' if is_last else '22'};
                border-radius:{radius};background:#13131f;
                display:flex;align-items:center;gap:8px;padding:6px 14px 6px 18px;
                margin-bottom:0">
                <span style="color:{cor}99;font-family:monospace;font-size:13px;flex-shrink:0">{conector}</span>
                <span style="width:9px;height:9px;border-radius:50%;background:{cor_f};
                    display:inline-block;flex-shrink:0;box-shadow:0 0 4px {cor_f}88"></span>
                <span style="font-size:13px;color:#e0e0e0;flex:1">{filho['nome']}</span>
                <span style="font-size:10px;color:#aaa;background:#ffffff12;
                    border-radius:8px;padding:1px 7px">{nat_f}</span>
            </div>""",
            unsafe_allow_html=True,
        )

    if not filhos:
        st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

    # ── Editar / adicionar subcategoria ──────────────────────────────────────
    with st.expander(f"✏️ Editar / gerenciar  **{row['nome']}**", expanded=False):
        # ── Editar categoria pai ─────────────────────────────────────────────
        st.markdown("**Categoria pai**")
        with st.form(f"edit_{id_}"):
            c1, c2, c3 = st.columns([3, 2, 2])
            novo_nome = c1.text_input("Nome", value=row["nome"])
            nova_cor  = c2.color_picker("Cor", value=cor)
            nova_nat  = c3.selectbox(
                "Natureza", options=_NAT_OPTS,
                index=_NAT_OPTS.index(row.get("natureza") or "nao_classificado"),
                format_func=lambda x: _NAT_LABELS[x],
            )
            col_s, col_d = st.columns(2)
            salvar  = col_s.form_submit_button("💾 Salvar categoria")
            excluir = col_d.form_submit_button("🗑️ Excluir categoria", type="secondary")

        if salvar:
            editar_categoria(id_, novo_nome, row["tipo"], nova_cor, nova_nat, user_id=uid)
            st.success("Categoria salva!")
            st.rerun()
        if excluir:
            excluir_categoria(id_, user_id=uid)
            st.rerun()

        # ── Nova subcategoria ────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("**➕ Nova subcategoria**")
        with st.form(f"sub_{id_}"):
            sub_nome = st.text_input("Nome da subcategoria", key=f"sub_nome_{id_}")
            sub_cor  = st.color_picker("Cor", "#888888", key=f"sub_cor_{id_}")
            if st.form_submit_button("Criar subcategoria", type="primary"):
                if sub_nome.strip():
                    try:
                        criar_categoria(sub_nome.strip(), row["tipo"], sub_cor,
                                        parent_id=id_, user_id=uid)
                        st.success(f"Subcategoria '{sub_nome}' criada!")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                else:
                    st.error("Informe o nome.")


# ── Aba Categorias ────────────────────────────────────────────────────────────
with tab_cats:
    tipo_filtro = st.radio("Ver", ["Todas", "Despesas", "Receitas"], horizontal=True)
    tipo_map = {"Todas": None, "Despesas": "despesa", "Receitas": "receita"}
    tipo_sel = tipo_map[tipo_filtro]

    cats_df = listar_categorias(tipo_sel, user_id=uid)
    pais, filhos_map = listar_categorias_arvore(tipo_sel, user_id=uid)

    if not pais:
        st.info("Nenhuma categoria encontrada.")
    else:
        col_desp, col_rec = st.columns(2)
        pais_desp = [p for p in pais if p["tipo"] == "despesa"]
        pais_rec  = [p for p in pais if p["tipo"] == "receita"]

        with col_desp:
            if pais_desp:
                st.markdown("### 🔴 Despesas")
                for p in sorted(pais_desp, key=lambda r: r["nome"]):
                    _bloco_categoria(p, filhos_map)

        with col_rec:
            if pais_rec:
                st.markdown("### 🟢 Receitas")
                for p in sorted(pais_rec, key=lambda r: r["nome"]):
                    _bloco_categoria(p, filhos_map)

    st.markdown("---")
    st.subheader("Nova Categoria")
    with st.form("nova_cat"):
        c1, c2, c3, c4 = st.columns(4)
        nome_novo = c1.text_input("Nome *")
        tipo_novo = c2.selectbox("Tipo", ["despesa", "receita"])
        nat_novo  = c3.selectbox("Natureza", _NAT_OPTS, format_func=lambda x: _NAT_LABELS[x])
        cor_nova  = c4.color_picker("Cor", "#888888")

        cats_todos = listar_categorias(user_id=uid)
        opts_pai = ["(nenhum — categoria raiz)"] + cats_todos["nome"].tolist()
        pai_sel = st.selectbox("Subcategoria de", opts_pai)

        if st.form_submit_button("Criar Categoria", type="primary"):
            if not nome_novo.strip():
                st.error("Informe um nome.")
            else:
                parent_id = None
                if pai_sel != "(nenhum — categoria raiz)":
                    match = cats_todos[cats_todos["nome"] == pai_sel]
                    if not match.empty:
                        parent_id = int(match.iloc[0]["id"])
                        tipo_novo = match.iloc[0]["tipo"]
                try:
                    criar_categoria(nome_novo.strip(), tipo_novo, cor_nova,
                                    parent_id=parent_id, natureza=nat_novo, user_id=uid)
                    st.success(f"Categoria '{nome_novo}' criada!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ── Aba Contas ────────────────────────────────────────────────────────────────
with tab_contas:
    st.subheader("Contas Cadastradas")
    contas = listar_contas(user_id=uid)
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
                criar_conta(nome_c.strip(), banco_c, tipo_c, user_id=uid)
                st.success("Conta adicionada!")
                st.rerun()


# ── Aba Importações ───────────────────────────────────────────────────────────
with tab_imports:
    st.subheader("Histórico de Importações")
    imports = listar_importacoes(user_id=uid)
    if not imports.empty:
        st.dataframe(imports, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma importação realizada ainda.")


# ── Aba Usuários (somente admin) ──────────────────────────────────────────────
if tab_users is not None:
    with tab_users:
        st.subheader("Gerenciar Usuários")

        # Lista de usuários existentes
        usuarios_df = listar_usuarios()
        if not usuarios_df.empty:
            st.markdown("**Usuários cadastrados**")
            for _, row in usuarios_df.iterrows():
                col_info, col_del = st.columns([5, 1])
                with col_info:
                    st.markdown(f"👤 **{row['nome']}** — `{row['email']}`")
                with col_del:
                    is_self = str(row["id"]) == str(uid)
                    if not is_self:
                        if st.button("🗑️", key=f"del_user_{row['id']}", help="Excluir usuário"):
                            excluir_usuario(int(row["id"]))
                            st.success(f"Usuário {row['email']} removido.")
                            st.rerun()
                    else:
                        st.caption("(você)")
        else:
            st.info("Nenhum usuário cadastrado no banco ainda.")

        st.markdown("---")
        st.subheader("Adicionar Novo Usuário")
        with st.form("novo_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            novo_nome  = c1.text_input("Nome completo *")
            novo_email = c2.text_input("E-mail *", placeholder="usuario@email.com")
            c3, c4 = st.columns(2)
            nova_senha  = c3.text_input("Senha *", type="password")
            conf_senha  = c4.text_input("Confirmar senha *", type="password")

            submitted = st.form_submit_button("➕ Cadastrar Usuário", type="primary")
            if submitted:
                erros = []
                if not novo_nome.strip():
                    erros.append("Informe o nome.")
                if not novo_email.strip():
                    erros.append("Informe o e-mail.")
                if not nova_senha:
                    erros.append("Informe a senha.")
                elif nova_senha != conf_senha:
                    erros.append("As senhas não conferem.")
                elif len(nova_senha) < 6:
                    erros.append("A senha deve ter pelo menos 6 caracteres.")
                if not erros and email_cadastrado(novo_email):
                    erros.append("Este e-mail já está cadastrado.")

                if erros:
                    for e in erros:
                        st.error(e)
                else:
                    criar_usuario(novo_email.strip(), novo_nome.strip(), nova_senha)
                    st.success(f"✅ Usuário **{novo_nome.strip()}** cadastrado com sucesso!")
                    st.rerun()

        st.markdown("---")
        st.info(
            "💡 **Dica de bootstrap:** Enquanto o bloco `[users]` existir no secrets.toml, "
            "você pode entrar com as credenciais de lá mesmo sem estar no banco. "
            "Após criar sua conta acima, remova o bloco `[users]` dos secrets para maior segurança.",
            icon="🔐",
        )
