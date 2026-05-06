import streamlit as st
import pandas as pd
from auth import require_login, sidebar_user
from db.queries import (
    listar_categorias, get_ou_criar_conta,
    registrar_importacao, inserir_transacoes,
    atualizar_natureza_categoria, criar_categoria,
)
from parsers import nubank, mercado_pago, banco_brasil

st.set_page_config(page_title="Importar Extrato", page_icon="📥", layout="wide")
uid = require_login()
sidebar_user()

st.title("📥 Importar Extrato")

BANCOS = {
    "Nubank (CSV fatura ou conta)": ("nubank", nubank),
    "Mercado Pago (CSV ou XLSX)": ("mercado_pago", mercado_pago),
    "Banco do Brasil (OFX, XLS, CSV)": ("bb", banco_brasil),
}
NATUREZA_OPTS   = ["nao_classificado", "fixo", "variavel"]
NATUREZA_LABELS = {"nao_classificado": "Não classificado", "fixo": "Fixo", "variavel": "Variável"}
SUB_NONE        = "(nenhuma)"

banco_label = st.selectbox("Banco / Cartão", list(BANCOS.keys()))
banco_key, parser_mod = BANCOS[banco_label]

uploaded = st.file_uploader(
    "Selecione o arquivo de extrato",
    type=["csv", "xls", "xlsx", "ofx"],
    help="Exporte o extrato diretamente do app ou internet banking do banco.",
)

if not uploaded:
    st.stop()

# ── Parse do arquivo ──────────────────────────────────────────────────────────
file_key = f"{uploaded.name}_{uploaded.size}"
if st.session_state.get("_imp_file_key") != file_key:
    with st.spinner("Lendo arquivo..."):
        try:
            df_parsed = parser_mod.parse(uploaded.read(), uploaded.name)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            st.stop()
    st.session_state["_imp_file_key"]  = file_key
    st.session_state["_imp_df_parsed"] = df_parsed
    st.session_state["_imp_rows"]      = None
else:
    df_parsed = st.session_state["_imp_df_parsed"]

st.success(f"{len(df_parsed)} transações encontradas.")


# ── Helpers de categorias ─────────────────────────────────────────────────────
def _build_cat_maps():
    cats = listar_categorias(user_id=uid)
    pais   = cats[cats["parent_id"].isna()]
    filhos = cats[cats["parent_id"].notna()]
    pai_nome = dict(zip(cats["id"], cats["nome"]))

    def _labels_pais(tipo):
        df = pais[pais["tipo"] == tipo].sort_values("nome")
        labels = df["nome"].tolist()
        id_map = dict(zip(df["nome"], df["id"].astype(int)))
        return labels, id_map

    labels_cat_desp, id_cat_desp = _labels_pais("despesa")
    labels_cat_rec,  id_cat_rec  = _labels_pais("receita")
    labels_cat_all = sorted(set(labels_cat_desp + labels_cat_rec))
    id_cat_all     = {**id_cat_desp, **id_cat_rec}

    def _labels_subs(tipo):
        df = filhos[filhos["tipo"] == tipo].sort_values("nome")
        labels = [SUB_NONE]
        id_map = {SUB_NONE: None}
        for _, s in df.iterrows():
            label = f"{pai_nome.get(int(s['parent_id']), '?')} › {s['nome']}"
            labels.append(label)
            id_map[label] = int(s["id"])
        return labels, id_map

    labels_sub_desp, id_sub_desp = _labels_subs("despesa")
    labels_sub_rec,  id_sub_rec  = _labels_subs("receita")
    labels_sub_all = sorted(set(labels_sub_desp + labels_sub_rec) - {SUB_NONE})
    labels_sub_all = [SUB_NONE] + labels_sub_all
    id_sub_all     = {**id_sub_desp, **id_sub_rec}

    nat_map = dict(zip(cats["nome"], cats["natureza"].fillna("nao_classificado")))

    return (
        labels_cat_desp, labels_cat_rec, labels_cat_all, id_cat_all,
        labels_sub_desp, labels_sub_rec, labels_sub_all, id_sub_all,
        nat_map, cats,
    )

(
    labels_cat_desp, labels_cat_rec, labels_cat_all, id_cat_all,
    labels_sub_desp, labels_sub_rec, labels_sub_all, id_sub_all,
    nat_map, cats_df,
) = _build_cat_maps()


# ── Criar categoria sem sair da importação ────────────────────────────────────
with st.expander("➕ Criar nova categoria", expanded=False):
    st.caption("A nova categoria aparece imediatamente nas colunas abaixo.")
    with st.form("form_nova_cat_import", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        novo_nome = c1.text_input("Nome *")
        novo_tipo = c2.selectbox("Tipo", ["despesa", "receita"])
        nova_nat  = c3.selectbox("Natureza", NATUREZA_OPTS, format_func=lambda x: NATUREZA_LABELS[x])
        nova_cor  = c4.color_picker("Cor", "#888888")

        opts_pai = ["(categoria principal)"] + cats_df["nome"].tolist()
        pai_sel  = st.selectbox("Subcategoria de", opts_pai)

        if st.form_submit_button("✅ Criar", type="primary"):
            if not novo_nome.strip():
                st.error("Informe o nome.")
            else:
                parent_id, tipo_final = None, novo_tipo
                if pai_sel != "(categoria principal)":
                    m = cats_df[cats_df["nome"] == pai_sel]
                    if not m.empty:
                        parent_id  = int(m.iloc[0]["id"])
                        tipo_final = m.iloc[0]["tipo"]
                criar_categoria(novo_nome.strip(), tipo_final, nova_cor,
                                parent_id=parent_id, natureza=nova_nat, user_id=uid)
                st.success(f"Categoria **{novo_nome}** criada!")
                st.rerun()


# ── Monta linhas ──────────────────────────────────────────────────────────────
if st.session_state.get("_imp_rows") is None:
    linhas = []
    for _, row in df_parsed.iterrows():
        opts = labels_cat_rec if row["tipo"] == "receita" else labels_cat_desp
        cat = opts[0] if opts else ""
        linhas.append({
            "incluir":      True,
            "data":         pd.to_datetime(row["data"]).date(),
            "descricao":    row["descricao"],
            "valor":        float(row["valor"]),
            "tipo":         row["tipo"],
            "categoria":    cat,
            "subcategoria": "",
            "natureza":     nat_map.get(cat, "nao_classificado"),
            "_banco":       row["banco"],
            "_conta_nome":  row["conta_nome"],
            "_conta_tipo":  row["conta_tipo"],
        })
    st.session_state["_imp_rows"] = linhas


# ── Cabeçalho ────────────────────────────────────────────────────────────────
col_titulo, col_remover, col_limpar = st.columns([5, 1, 1])
col_titulo.subheader("Revise e categorize as transações")
if col_remover.button("✂️ Remover desmarcadas"):
    rows_atuais = st.session_state.get("_imp_rows") or []
    st.session_state["_imp_rows"] = [r for r in rows_atuais if r.get("incluir", True)]
    st.rerun()
if col_limpar.button("🔄 Restaurar"):
    st.session_state["_imp_rows"] = None
    st.rerun()

st.caption(
    "💡 **Categoria**: selecione a principal. "
    "**Subcategoria**: digite o nome — se já existir é usada, se for novo é criada automaticamente."
)

edited = st.data_editor(
    pd.DataFrame(st.session_state["_imp_rows"]),
    column_config={
        "incluir":      st.column_config.CheckboxColumn("✓", width="small"),
        "data":         st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao":    st.column_config.TextColumn("Descrição", width="large"),
        "valor":        st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
        "tipo":         st.column_config.SelectboxColumn("Tipo", options=["despesa", "receita"]),
        "categoria":    st.column_config.SelectboxColumn("Categoria", options=labels_cat_all),
        "subcategoria": st.column_config.TextColumn("Subcategoria"),
        "natureza":     st.column_config.SelectboxColumn("Natureza", options=NATUREZA_OPTS),
        "_banco":      None,
        "_conta_nome": None,
        "_conta_tipo": None,
    },
    hide_index=True,
    use_container_width=True,
    num_rows="dynamic",
)

st.session_state["_imp_rows"] = edited.to_dict("records")

selecionadas = edited[edited["incluir"] == True]
st.caption(f"{len(selecionadas)} de {len(edited)} transações selecionadas.")


# ── Salvar ────────────────────────────────────────────────────────────────────
if st.button("💾 Salvar transações selecionadas", type="primary", disabled=len(selecionadas) == 0):
    imp_id = registrar_importacao(uploaded.name, banco_key, len(selecionadas), user_id=uid)

    sub_cache: dict = {}
    sub_existentes = {
        s["nome"].strip().lower(): int(s["id"])
        for _, s in listar_categorias(user_id=uid).iterrows()
        if s["parent_id"] is not None and not pd.isna(s["parent_id"])
    }

    nat_atualizada: dict = {}
    registros = []
    novas_criadas = 0

    for _, row in selecionadas.iterrows():
        conta_id = get_ou_criar_conta(row["_conta_nome"], row["_banco"], row["_conta_tipo"], user_id=uid)
        nat      = row.get("natureza") or "nao_classificado"
        sub_texto = str(row.get("subcategoria") or "").strip()
        cat_nome  = row.get("categoria") or ""
        cat_id    = id_cat_all.get(cat_nome)

        if sub_texto:
            chave = sub_texto.lower()
            if chave in sub_cache:
                cat_id = sub_cache[chave]
            elif chave in sub_existentes:
                cat_id = sub_existentes[chave]
            elif cat_id:
                tipo_pai = cats_df[cats_df["nome"] == cat_nome]["tipo"].values
                tipo_pai = tipo_pai[0] if len(tipo_pai) else "despesa"
                criar_categoria(sub_texto, tipo_pai, "#888888",
                                parent_id=cat_id, natureza=nat, user_id=uid)
                cats_fresh = listar_categorias(user_id=uid)
                novo = cats_fresh[cats_fresh["nome"].str.lower() == chave]
                if not novo.empty:
                    novo_id = int(novo.iloc[0]["id"])
                    sub_cache[chave] = novo_id
                    sub_existentes[chave] = novo_id
                    cat_id = novo_id
                    novas_criadas += 1

        if cat_id and cat_id not in nat_atualizada:
            nat_atualizada[cat_id] = nat
            atualizar_natureza_categoria(cat_id, nat, user_id=uid)

        registros.append({
            "data":          str(row["data"])[:10],
            "descricao":     row["descricao"],
            "valor":         float(row["valor"]),
            "tipo":          row["tipo"],
            "categoria_id":  cat_id,
            "conta_id":      conta_id,
            "observacao":    None,
            "importacao_id": imp_id,
        })

    inserir_transacoes(registros, user_id=uid)
    for k in ["_imp_file_key", "_imp_df_parsed", "_imp_rows"]:
        st.session_state.pop(k, None)

    msg = f"✅ {len(registros)} transações salvas!"
    if novas_criadas:
        msg += f" ({novas_criadas} subcategoria(s) nova(s) criada(s))"
    st.success(msg)
    st.balloons()
