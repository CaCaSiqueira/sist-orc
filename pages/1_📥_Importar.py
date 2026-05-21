import streamlit as st
import pandas as pd
from auth import require_login, sidebar_user
import hashlib
from db.queries import (
    listar_categorias, listar_subcategorias, listar_categorias_arvore,
    get_ou_criar_conta, registrar_importacao, inserir_transacoes,
    atualizar_natureza_categoria, criar_categoria,
    verificar_importacao_duplicada, verificar_periodo_ja_importado,
    buscar_transacoes_existentes_por_periodo,
)
from parsers import nubank, mercado_pago, banco_brasil

st.set_page_config(page_title="Importar Extrato", page_icon="📥", layout="wide")
uid = require_login()
sidebar_user()

st.title("📥 Importar Extrato")

BANCOS = {
    "Nubank": {
        "banco_key": "nubank",
        "parser":    nubank,
        "tipos": {
            "💳 Fatura (Cartão de Crédito)": "cartao_credito",
            "🏦 Conta Corrente":             "conta_corrente",
        },
    },
    "Mercado Pago": {
        "banco_key": "mercado_pago",
        "parser":    mercado_pago,
        "tipos": {
            "📱 Carteira Digital": "carteira_digital",
        },
    },
    "Banco do Brasil": {
        "banco_key": "bb",
        "parser":    banco_brasil,
        "tipos": {
            "🏦 Conta Corrente": "conta_corrente",
            "💰 Poupança":       "poupanca",
        },
    },
}
NATUREZA_OPTS   = ["nao_classificado", "fixo", "variavel"]
NATUREZA_LABELS = {"nao_classificado": "Não classificado", "fixo": "Fixo", "variavel": "Variável"}
SUB_NONE        = "(nenhuma)"

# ── Seleção de banco e tipo de conta em campos separados ──────────────────────
col_banco, col_tipo = st.columns(2)
banco_nome = col_banco.selectbox("Banco", list(BANCOS.keys()))
banco_info = BANCOS[banco_nome]
tipos_disponiveis = banco_info["tipos"]

if len(tipos_disponiveis) > 1:
    tipo_label = col_tipo.selectbox("Tipo de conta", list(tipos_disponiveis.keys()))
else:
    tipo_label = list(tipos_disponiveis.keys())[0]
    col_tipo.info(f"Tipo: **{tipo_label}**")

banco_key           = banco_info["banco_key"]
parser_mod          = banco_info["parser"]
conta_tipo_importacao = tipos_disponiveis[tipo_label]

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
            file_bytes = uploaded.read()
            file_hash  = hashlib.md5(file_bytes).hexdigest()
            df_parsed  = parser_mod.parse(file_bytes, uploaded.name)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            st.stop()

    # ── Verifica duplicata por hash (arquivo idêntico) ───────────────────────
    duplicata = verificar_importacao_duplicada(file_hash, user_id=uid)
    if duplicata:
        st.warning(
            f"⚠️ **Este arquivo já foi importado antes!**\n\n"
            f"- 📄 Arquivo: `{duplicata['arquivo']}`\n"
            f"- 🏦 Banco: `{duplicata['banco']}`\n"
            f"- 📊 Transações na época: `{duplicata['total']}`\n"
            f"- 📅 Importado em: `{duplicata['importado_em']}`\n\n"
            f"Importar novamente vai **duplicar as transações**."
        )
        if not st.checkbox("⚠️ Entendi, quero importar mesmo assim", key="dup_hash"):
            st.stop()
    else:
        # ── Verifica duplicata por período (mesmo banco, mesmo intervalo de datas)
        if not df_parsed.empty:
            datas      = pd.to_datetime(df_parsed["data"])
            dt_inicio  = datas.min().strftime("%Y-%m-%d")
            dt_fim     = datas.max().strftime("%Y-%m-%d")
            mes_label  = datas.min().strftime("%m/%Y")
            qtd_exist  = verificar_periodo_ja_importado(banco_key, dt_inicio, dt_fim, user_id=uid)
            if qtd_exist > 0:
                st.warning(
                    f"⚠️ **Já existem {qtd_exist} transações do {banco_key.upper()} "
                    f"no período {mes_label}!**\n\n"
                    f"Importar novamente pode **duplicar as transações**."
                )
                if not st.checkbox("⚠️ Entendi, quero importar mesmo assim", key="dup_periodo"):
                    st.stop()

    st.session_state["_imp_file_key"]   = file_key
    st.session_state["_imp_df_parsed"]  = df_parsed
    st.session_state["_imp_file_hash"]  = file_hash
    st.session_state["_imp_rows"]       = None
else:
    df_parsed  = st.session_state["_imp_df_parsed"]
    file_hash  = st.session_state.get("_imp_file_hash", "")

st.success(f"{len(df_parsed)} transações encontradas.")


# ── Helpers de categorias ─────────────────────────────────────────────────────
def _build_cat_maps():
    # pais: list[dict] com {id, nome, tipo, cor, natureza}
    # filhos_map: {categoria_id: [{id, nome, cor, natureza, categoria_id, tipo}, ...]}
    pais, filhos_map = listar_categorias_arvore(user_id=uid)
    cats = listar_categorias(user_id=uid)  # DataFrame para uso no form de nova cat

    pai_nome = {int(p["id"]): p["nome"] for p in pais}

    def _labels_pais(tipo):
        filtrado = sorted([p for p in pais if p["tipo"] == tipo], key=lambda x: x["nome"])
        labels = [p["nome"] for p in filtrado]
        id_map = {p["nome"]: int(p["id"]) for p in filtrado}
        return labels, id_map

    labels_cat_desp, id_cat_desp = _labels_pais("despesa")
    labels_cat_rec,  id_cat_rec  = _labels_pais("receita")
    labels_cat_all = sorted(set(labels_cat_desp + labels_cat_rec))
    id_cat_all     = {**id_cat_desp, **id_cat_rec}

    def _labels_subs(tipo):
        labels = [SUB_NONE]
        id_map = {SUB_NONE: None}
        for cid, subs in filhos_map.items():
            nome_pai = pai_nome.get(cid, "?")
            for s in sorted(subs, key=lambda x: x["nome"]):
                if s.get("tipo") == tipo:
                    label = f"{nome_pai} › {s['nome']}"
                    labels.append(label)
                    id_map[label] = int(s["id"])
        return labels, id_map

    labels_sub_desp, id_sub_desp = _labels_subs("despesa")
    labels_sub_rec,  id_sub_rec  = _labels_subs("receita")
    labels_sub_all = sorted(set(labels_sub_desp + labels_sub_rec) - {SUB_NONE})
    labels_sub_all = [SUB_NONE] + labels_sub_all
    id_sub_all     = {**id_sub_desp, **id_sub_rec}

    nat_map = {p["nome"]: p.get("natureza") or "nao_classificado" for p in pais}

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
    # Busca transações já existentes no mesmo período para detectar duplicatas
    if not df_parsed.empty:
        datas_parsed = pd.to_datetime(df_parsed["data"])
        _dt_ini = datas_parsed.min().strftime("%Y-%m-%d")
        _dt_fim = datas_parsed.max().strftime("%Y-%m-%d")
        existentes = buscar_transacoes_existentes_por_periodo(
            banco_key, _dt_ini, _dt_fim, user_id=uid
        )
    else:
        existentes = set()

    linhas = []
    duplicatas_encontradas = 0
    for _, row in df_parsed.iterrows():
        opts  = labels_cat_rec if row["tipo"] == "receita" else labels_cat_desp
        cat   = opts[0] if opts else ""
        data  = pd.to_datetime(row["data"]).date()
        valor = float(row["valor"])
        tipo  = row["tipo"]

        chave = (str(data), valor, tipo)
        ja_existe = chave in existentes
        if ja_existe:
            duplicatas_encontradas += 1

        linhas.append({
            "incluir":      not ja_existe,   # desmarca automático se duplicata
            "⚠️":           "⚠️ já existe" if ja_existe else "",
            "data":         data,
            "descricao":    row["descricao"],
            "valor":        valor,
            "tipo":         tipo,
            "categoria":    cat,
            "subcategoria": SUB_NONE,
            "natureza":     nat_map.get(cat, "nao_classificado"),
            "_banco":       row["banco"],
            "_conta_nome":  row["conta_nome"],
            "_conta_tipo":  row["conta_tipo"],
        })

    if duplicatas_encontradas:
        st.warning(
            f"⚠️ **{duplicatas_encontradas} transação(ões) com mesma data e valor já existem** "
            f"no banco e foram **desmarcadas automaticamente**. "
            f"Revise antes de salvar."
        )

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
        "⚠️":           st.column_config.TextColumn("Aviso", width="small"),
        "data":         st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao":    st.column_config.TextColumn("Descrição", width="large"),
        "valor":        st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
        "tipo":         st.column_config.SelectboxColumn("Tipo", options=["despesa", "receita"]),
        "categoria":    st.column_config.SelectboxColumn("Categoria", options=labels_cat_all),
        "subcategoria": st.column_config.SelectboxColumn("Subcategoria", options=labels_sub_all),
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
    imp_id = registrar_importacao(uploaded.name, banco_key, len(selecionadas), user_id=uid, hash_arquivo=file_hash)

    # sub_cache: chave_lower → {"cat_id": int, "sub_id": int}
    sub_cache: dict = {}
    subs_df = listar_subcategorias(user_id=uid)
    sub_existentes = {
        str(row["nome"]).strip().lower(): {
            "cat_id": int(row["categoria_id"]),
            "sub_id": int(row["id"]),
        }
        for _, row in subs_df.iterrows()
    }

    nat_atualizada: dict = {}
    registros = []
    novas_criadas = 0

    for _, row in selecionadas.iterrows():
        conta_id  = get_ou_criar_conta(row["_conta_nome"], row["_banco"], conta_tipo_importacao, user_id=uid)
        nat       = row.get("natureza") or "nao_classificado"
        sub_texto = str(row.get("subcategoria") or "").strip()
        # ignora a opção "(nenhuma)" do dropdown
        if sub_texto == SUB_NONE:
            sub_texto = ""
        cat_nome  = row.get("categoria") or ""
        cat_id    = id_cat_all.get(cat_nome)
        sub_id    = None

        if sub_texto and cat_id:
            # label do dropdown pode ser "Categoria › Subcategoria" — extrai só o nome
            if " › " in sub_texto:
                sub_texto = sub_texto.split(" › ", 1)[1].strip()
            chave = sub_texto.lower()
            if chave in sub_cache:
                sub_id = sub_cache[chave]["sub_id"]
                cat_id = sub_cache[chave]["cat_id"]
            elif chave in sub_existentes:
                sub_id = sub_existentes[chave]["sub_id"]
                cat_id = sub_existentes[chave]["cat_id"]
            else:
                tipo_pai = cats_df[cats_df["nome"] == cat_nome]["tipo"].values
                tipo_pai = tipo_pai[0] if len(tipo_pai) else "despesa"
                try:
                    criar_categoria(sub_texto, tipo_pai, "#888888",
                                    parent_id=cat_id, natureza=nat, user_id=uid)
                    subs_fresh = listar_subcategorias(user_id=uid)
                    novo = subs_fresh[
                        (subs_fresh["nome"].str.lower() == chave) &
                        (subs_fresh["categoria_id"] == cat_id)
                    ]
                    if not novo.empty:
                        novo_sub_id = int(novo.iloc[0]["id"])
                        sub_cache[chave]    = {"cat_id": cat_id, "sub_id": novo_sub_id}
                        sub_existentes[chave] = {"cat_id": cat_id, "sub_id": novo_sub_id}
                        sub_id = novo_sub_id
                        novas_criadas += 1
                except Exception:
                    pass  # subcategoria duplicada — ignora

        if cat_id and cat_id not in nat_atualizada:
            nat_atualizada[cat_id] = nat
            atualizar_natureza_categoria(cat_id, nat, user_id=uid)

        registros.append({
            "data":            str(row["data"])[:10],
            "descricao":       row["descricao"],
            "valor":           float(row["valor"]),
            "tipo":            row["tipo"],
            "categoria_id":    cat_id,
            "subcategoria_id": sub_id,
            "conta_id":        conta_id,
            "observacao":      None,
            "importacao_id":   imp_id,
        })

    inserir_transacoes(registros, user_id=uid)
    for k in ["_imp_file_key", "_imp_df_parsed", "_imp_rows"]:
        st.session_state.pop(k, None)

    msg = f"✅ {len(registros)} transações salvas!"
    if novas_criadas:
        msg += f" ({novas_criadas} subcategoria(s) nova(s) criada(s))"
    st.success(msg)
    st.balloons()
