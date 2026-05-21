import hashlib
import os
import base64
import pandas as pd
from sqlalchemy import text
from .database import get_engine, dialect


# ── Usuários ──────────────────────────────────────────────────────────────────

_UID = "default"  # fallback quando não há login


def _hash_senha(senha: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 100_000)
    return base64.b64encode(salt + key).decode()


def _verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        raw = base64.b64decode(armazenado)
        salt, key = raw[:16], raw[16:]
        return key == hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 100_000)
    except Exception:
        return False


def get_usuario(email: str) -> dict | None:
    row = _read(
        "SELECT id, nome, senha_hash FROM usuarios WHERE email = :e",
        {"e": email.lower().strip()},
    )
    if row.empty:
        return None
    r = row.iloc[0]
    return {"id": str(int(r["id"])), "nome": str(r["nome"]), "senha_hash": str(r["senha_hash"])}


def criar_usuario(email: str, nome: str, senha: str) -> str:
    """Cria usuário com senha criptografada. Retorna user_id como string."""
    uid = _insert_returning_id(
        "INSERT INTO usuarios (email, nome, senha_hash) VALUES (:e, :n, :h) RETURNING id",
        {"e": email.lower().strip(), "n": nome.strip(), "h": _hash_senha(senha)},
    )
    return str(uid)


def autenticar(email: str, senha: str) -> tuple[str, str] | None:
    """Retorna (user_id, nome) se credenciais válidas, senão None."""
    u = get_usuario(email)
    if u and _verificar_senha(senha, u["senha_hash"]):
        return u["id"], u["nome"]
    return None


def atualizar_senha(user_id: str, nova_senha: str):
    _write(
        "UPDATE usuarios SET senha_hash = :h WHERE id = :id",
        {"h": _hash_senha(nova_senha), "id": int(user_id)},
    )


def listar_usuarios():
    return _read("SELECT id, email, nome, criado_em FROM usuarios ORDER BY nome")


def excluir_usuario(id_: int):
    _write("DELETE FROM usuarios WHERE id = :id", {"id": id_})


def email_cadastrado(email: str) -> bool:
    df = _read("SELECT id FROM usuarios WHERE email = :email", {"email": email.lower().strip()})
    return not df.empty


def _read(sql: str, params: dict = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def _write(sql: str, params=None):
    with get_engine().begin() as conn:
        conn.execute(text(sql), params or {})


def _write_many(sql: str, params_list: list):
    with get_engine().begin() as conn:
        conn.execute(text(sql), params_list)


def _insert_returning_id(sql_returning: str, params: dict = None) -> int:
    with get_engine().begin() as conn:
        result = conn.execute(text(sql_returning), params or {})
        row = result.fetchone()
        return int(row[0]) if row else None


def _month_sql(col: str) -> str:
    if dialect() == "sqlite":
        return f"strftime('%Y-%m', {col})"
    return f"to_char({col}::date, 'YYYY-MM')"


# ── Categorias ────────────────────────────────────────────────────────────────

def listar_categorias(tipo=None, user_id=_UID):
    extra = "AND tipo = :tipo" if tipo else ""
    params = {"uid": user_id}
    if tipo:
        params["tipo"] = tipo
    return _read(
        f"SELECT id, nome, tipo, cor, natureza FROM categorias WHERE user_id = :uid {extra} ORDER BY nome",
        params,
    )


def _listar_subcategorias_df(tipo=None, user_id=_UID):
    # user_id agora filtrado via JOIN com categorias (3FN: user_id removido de subcategorias)
    sql = """
        SELECT s.id, s.nome, s.cor, s.natureza, s.categoria_id, c.tipo
        FROM subcategorias s
        JOIN categorias c ON s.categoria_id = c.id
        WHERE c.user_id = :uid
    """
    params = {"uid": user_id}
    if tipo:
        sql += " AND c.tipo = :tipo"
        params["tipo"] = tipo
    return _read(sql, params)


def listar_subcategorias(tipo=None, user_id=_UID):
    """Retorna DataFrame com subcategorias do usuário (tabela subcategorias)."""
    return _listar_subcategorias_df(tipo, user_id)


def listar_categorias_arvore(tipo=None, user_id=_UID):
    pais = listar_categorias(tipo, user_id).to_dict("records")
    subs_df = _listar_subcategorias_df(tipo, user_id)
    filhos_map = {}
    for _, row in subs_df.iterrows():
        cid = int(row["categoria_id"])
        filhos_map.setdefault(cid, []).append(row.to_dict())
    return pais, filhos_map


def opcoes_categoria(tipo=None, user_id=_UID):
    pais_df = listar_categorias(tipo, user_id)
    subs_df = _listar_subcategorias_df(tipo, user_id)

    labels, id_map = [], {}
    for _, p in pais_df.iterrows():
        labels.append(p["nome"])
        id_map[p["nome"]] = {"type": "categoria", "id": int(p["id"])}
        subs = subs_df[subs_df["categoria_id"] == p["id"]].sort_values("nome")
        for _, s in subs.iterrows():
            label = f"  ↳ {s['nome']}"
            labels.append(label)
            id_map[label] = {"type": "subcategoria", "id": int(s["id"]), "cat_id": int(p["id"])}
    return labels, id_map


def criar_categoria(nome, tipo, cor="#888888", parent_id=None, natureza="nao_classificado", user_id=_UID):
    from sqlalchemy.exc import IntegrityError
    try:
        if parent_id is None:
            _write(
                "INSERT INTO categorias (nome, tipo, cor, natureza, user_id) "
                "VALUES (:nome, :tipo, :cor, :natureza, :uid)",
                {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza, "uid": user_id},
            )
        else:
            # user_id não é armazenado em subcategorias (3FN: derivável via categoria_id)
            _write(
                "INSERT INTO subcategorias (nome, cor, natureza, categoria_id) "
                "VALUES (:nome, :cor, :natureza, :cid)",
                {"nome": nome, "cor": cor, "natureza": natureza, "cid": parent_id},
            )
    except IntegrityError:
        if parent_id is None:
            raise ValueError(f"Já existe uma categoria com o nome '{nome}'.")
        else:
            raise ValueError(f"Já existe uma subcategoria com o nome '{nome}' nesta categoria.")



def editar_categoria(id_, nome, tipo, cor, natureza="nao_classificado", user_id=_UID):
    _write(
        "UPDATE categorias SET nome = :nome, tipo = :tipo, cor = :cor, natureza = :natureza "
        "WHERE id = :id AND user_id = :uid",
        {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza, "id": id_, "uid": user_id},
    )


def editar_subcategoria(id_, nome, cor, natureza="nao_classificado", user_id=_UID):
    from sqlalchemy.exc import IntegrityError
    try:
        # Verifica propriedade via JOIN com categorias (3FN: user_id removido de subcategorias)
        _write(
            "UPDATE subcategorias SET nome = :nome, cor = :cor, natureza = :natureza "
            "WHERE id = :id "
            "AND categoria_id IN (SELECT id FROM categorias WHERE user_id = :uid)",
            {"nome": nome, "cor": cor, "natureza": natureza, "id": id_, "uid": user_id},
        )
    except IntegrityError:
        raise ValueError(f"Já existe uma subcategoria com o nome '{nome}' nesta categoria.")


def atualizar_natureza_categoria(id_: int, natureza: str, user_id=_UID):
    _write(
        "UPDATE categorias SET natureza = :natureza WHERE id = :id AND user_id = :uid",
        {"natureza": natureza, "id": id_, "uid": user_id},
    )


def excluir_categoria(id_, user_id=_UID):
    _write("UPDATE transacoes SET categoria_id = NULL, subcategoria_id = NULL "
           "WHERE categoria_id = :id AND user_id = :uid",
           {"id": id_, "uid": user_id})
    # subcategorias não tem user_id (3FN); a segurança é garantida pela FK de categoria_id
    _write("DELETE FROM subcategorias WHERE categoria_id = :id",
           {"id": id_})
    _write("DELETE FROM categorias WHERE id = :id AND user_id = :uid",
           {"id": id_, "uid": user_id})


def excluir_subcategoria(id_, user_id=_UID):
    _write("UPDATE transacoes SET subcategoria_id = NULL "
           "WHERE subcategoria_id = :id AND user_id = :uid",
           {"id": id_, "uid": user_id})
    # Verifica propriedade via JOIN (3FN: user_id removido de subcategorias)
    _write("DELETE FROM subcategorias WHERE id = :id "
           "AND categoria_id IN (SELECT id FROM categorias WHERE user_id = :uid)",
           {"id": id_, "uid": user_id})


# ── Contas ────────────────────────────────────────────────────────────────────

def listar_contas(user_id=_UID):
    return _read(
        "SELECT * FROM contas WHERE user_id = :uid ORDER BY banco, nome",
        {"uid": user_id},
    )


def criar_conta(nome, banco, tipo, user_id=_UID):
    return _insert_returning_id(
        "INSERT INTO contas (nome, banco, tipo, user_id) "
        "VALUES (:nome, :banco, :tipo, :uid) RETURNING id",
        {"nome": nome, "banco": banco, "tipo": tipo, "uid": user_id},
    )


def get_ou_criar_conta(nome, banco, tipo, user_id=_UID):
    existing = _read(
        "SELECT id FROM contas WHERE nome = :nome AND banco = :banco AND user_id = :uid",
        {"nome": nome, "banco": banco, "uid": user_id},
    )
    if not existing.empty:
        return int(existing.iloc[0]["id"])
    return _insert_returning_id(
        "INSERT INTO contas (nome, banco, tipo, user_id) "
        "VALUES (:nome, :banco, :tipo, :uid) RETURNING id",
        {"nome": nome, "banco": banco, "tipo": tipo, "uid": user_id},
    )


# ── Importações ───────────────────────────────────────────────────────────────

def verificar_periodo_ja_importado(banco: str, data_inicio: str, data_fim: str, user_id=_UID) -> int:
    """Retorna qtd de transacoes ja existentes do banco nesse periodo."""
    df = _read("""
        SELECT COUNT(*) AS total
        FROM transacoes t
        JOIN contas c ON t.conta_id = c.id
        WHERE c.banco = :banco
          AND t.data >= :inicio
          AND t.data <= :fim
          AND t.user_id = :uid
    """, {"banco": banco, "inicio": data_inicio, "fim": data_fim, "uid": user_id})
    return int(df.iloc[0]["total"]) if not df.empty else 0


def remover_transacoes_duplicadas(user_id=_UID) -> int:
    """Remove transacoes com mesmos (data, descricao, valor, tipo, conta_id).
    Mantém a de menor id (primeira importada). Retorna quantidade removida."""
    df = _read("""
        SELECT MIN(id) AS keep_id, data, descricao, valor, tipo, conta_id
        FROM transacoes
        WHERE user_id = :uid
        GROUP BY data, descricao, valor, tipo, conta_id
        HAVING COUNT(*) > 1
    """, {"uid": user_id})

    removidos = 0
    for _, row in df.iterrows():
        ids = _read("""
            SELECT id FROM transacoes
            WHERE data = :data AND descricao = :desc AND valor = :valor
              AND tipo = :tipo AND conta_id = :conta AND user_id = :uid
              AND id != :keep
        """, {
            "data": row["data"], "desc": row["descricao"], "valor": row["valor"],
            "tipo": row["tipo"], "conta": row["conta_id"], "uid": user_id,
            "keep": int(row["keep_id"]),
        })
        for _, id_row in ids.iterrows():
            _write("DELETE FROM transacoes WHERE id = :id", {"id": int(id_row["id"])})
            removidos += 1
    return removidos


def buscar_transacoes_existentes_por_periodo(banco: str, data_inicio: str, data_fim: str, user_id=_UID) -> set:
    """Retorna set de tuplas (data, valor, tipo) já existentes no banco nesse período."""
    df = _read("""
        SELECT t.data, t.valor, t.tipo
        FROM transacoes t
        JOIN contas c ON t.conta_id = c.id
        WHERE c.banco = :banco
          AND t.data >= :inicio
          AND t.data <= :fim
          AND t.user_id = :uid
    """, {"banco": banco, "inicio": data_inicio, "fim": data_fim, "uid": user_id})
    if df.empty:
        return set()
    return {
        (str(row["data"])[:10], float(row["valor"]), str(row["tipo"]))
        for _, row in df.iterrows()
    }


def verificar_importacao_duplicada(hash_arquivo: str, user_id=_UID):
    """Retorna dict com info da importacao anterior se o arquivo ja foi importado, senão None."""
    df = _read(
        "SELECT id, arquivo, banco, total_transacoes, importado_em "
        "FROM importacoes WHERE hash_arquivo = :hash AND user_id = :uid",
        {"hash": hash_arquivo, "uid": user_id},
    )
    if df.empty:
        return None
    row = df.iloc[0]
    return {
        "id":          int(row["id"]),
        "arquivo":     str(row["arquivo"]),
        "banco":       str(row["banco"]),
        "total":       int(row["total_transacoes"]) if row["total_transacoes"] else 0,
        "importado_em": str(row["importado_em"]),
    }


def registrar_importacao(arquivo, banco, total, user_id=_UID, hash_arquivo=None):
    return _insert_returning_id(
        "INSERT INTO importacoes (arquivo, banco, total_transacoes, user_id, hash_arquivo) "
        "VALUES (:arquivo, :banco, :total, :uid, :hash) RETURNING id",
        {"arquivo": arquivo, "banco": banco, "total": total, "uid": user_id, "hash": hash_arquivo},
    )


def listar_importacoes(user_id=_UID):
    return _read(
        "SELECT * FROM importacoes WHERE user_id = :uid ORDER BY importado_em DESC",
        {"uid": user_id},
    )


# ── Transações ────────────────────────────────────────────────────────────────

def inserir_transacoes(transacoes: list[dict], user_id=_UID):
    for t in transacoes:
        t["user_id"] = user_id
        if "subcategoria_id" not in t:
            t["subcategoria_id"] = None
    _write_many(
        """INSERT INTO transacoes
           (data, descricao, valor, tipo, categoria_id, subcategoria_id, conta_id,
            observacao, importacao_id, user_id)
           VALUES (:data, :descricao, :valor, :tipo, :categoria_id, :subcategoria_id, :conta_id,
                   :observacao, :importacao_id, :user_id)""",
        transacoes,
    )


def listar_transacoes(filtros: dict = None, user_id=_UID):
    filtros = filtros or {}
    where, params = ["t.user_id = :user_id"], {"user_id": user_id}

    if filtros.get("data_inicio"):
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = filtros["data_inicio"]
    if filtros.get("data_fim"):
        where.append("t.data <= :data_fim")
        params["data_fim"] = filtros["data_fim"]
    if filtros.get("tipo"):
        where.append("t.tipo = :tipo")
        params["tipo"] = filtros["tipo"]
    if filtros.get("subcategoria_id") is not None:
        where.append("t.subcategoria_id = :subcategoria_id")
        params["subcategoria_id"] = filtros["subcategoria_id"]
    elif filtros.get("categoria_id") is not None:
        where.append("t.categoria_id = :categoria_id")
        params["categoria_id"] = filtros["categoria_id"]
    if filtros.get("conta_id"):
        where.append("t.conta_id = :conta_id")
        params["conta_id"] = filtros["conta_id"]
    if filtros.get("busca"):
        if dialect() == "postgresql":
            where.append("t.descricao ILIKE :busca")
        else:
            where.append("LOWER(t.descricao) LIKE LOWER(:busca)")
        params["busca"] = f"%{filtros['busca']}%"

    where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT t.id, t.data, t.descricao, t.valor, t.tipo,
               COALESCE(s.nome, c.nome) AS categoria,
               COALESCE(s.cor, c.cor) AS cor,
               ct.nome AS conta, ct.banco,
               t.observacao
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
        LEFT JOIN subcategorias s ON t.subcategoria_id = s.id
        LEFT JOIN contas ct ON t.conta_id = ct.id
        {where_sql}
        ORDER BY t.data DESC, t.id DESC
    """
    return _read(sql, params)


def atualizar_transacao(id_, campo, valor):
    _write(f"UPDATE transacoes SET {campo} = :valor WHERE id = :id", {"valor": valor, "id": id_})


def excluir_transacao(id_):
    _write("DELETE FROM transacoes WHERE id = :id", {"id": id_})


def resumo_por_categoria(data_inicio=None, data_fim=None, user_id=_UID):
    where, params = ["t.user_id = :user_id"], {"user_id": user_id}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT COALESCE(s.nome, c.nome) AS categoria,
               COALESCE(s.cor, c.cor) AS cor, t.tipo,
               SUM(t.valor) AS total, COUNT(*) AS qtd
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
        LEFT JOIN subcategorias s ON t.subcategoria_id = s.id
        {where_sql}
        GROUP BY COALESCE(s.nome, c.nome), COALESCE(s.cor, c.cor), t.tipo
        ORDER BY total DESC
    """
    return _read(sql, params)


def resumo_por_natureza(data_inicio=None, data_fim=None, user_id=_UID):
    where, params = ["t.user_id = :user_id"], {"user_id": user_id}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT COALESCE(c.natureza, 'nao_classificado') AS natureza,
               t.tipo, SUM(t.valor) AS total, COUNT(*) AS qtd
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
        {where_sql}
        GROUP BY natureza, t.tipo
        ORDER BY natureza, t.tipo
    """
    return _read(sql, params)


def evolucao_fixo_variavel(data_inicio=None, data_fim=None, user_id=_UID):
    where, params = ["t.tipo = 'despesa'", "t.user_id = :user_id"], {"user_id": user_id}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = "WHERE " + " AND ".join(where)

    mes_col = _month_sql("t.data")
    sql = f"""
        SELECT {mes_col} AS mes,
               COALESCE(c.natureza, 'nao_classificado') AS natureza,
               SUM(t.valor) AS total
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
        {where_sql}
        GROUP BY mes, natureza
        ORDER BY mes, natureza
    """
    return _read(sql, params)


def evolucao_mensal(data_inicio=None, data_fim=None, user_id=_UID):
    where, params = ["user_id = :user_id"], {"user_id": user_id}
    if data_inicio:
        where.append("data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = "WHERE " + " AND ".join(where)

    mes_col = _month_sql("data")
    sql = f"""
        SELECT {mes_col} AS mes, tipo, SUM(valor) AS total
        FROM transacoes
        {where_sql}
        GROUP BY mes, tipo
        ORDER BY mes
    """
    return _read(sql, params)


# ── Parcelamentos ─────────────────────────────────────────────────────────────

def criar_parcelamento(dados: dict, user_id=_UID) -> int:
    # valor_parcela removido (3FN: derivável = valor_total / total_parcelas)
    dados = {k: v for k, v in dados.items() if k != "valor_parcela"}
    dados = {**dados, "uid": user_id}
    return _insert_returning_id(
        """INSERT INTO parcelamentos
           (descricao, valor_total, total_parcelas, parcelas_pagas,
            data_primeira_parcela, categoria_id, conta_id, observacao, user_id)
           VALUES (:descricao, :valor_total, :total_parcelas, :parcelas_pagas,
                   :data_primeira_parcela, :categoria_id, :conta_id, :observacao, :uid)
           RETURNING id""",
        dados,
    )


def listar_parcelamentos(apenas_ativos=False, user_id=_UID):
    cond = "p.parcelas_pagas < p.total_parcelas AND " if apenas_ativos else ""
    return _read(f"""
        SELECT p.*, c.nome AS categoria, ct.nome AS conta, ct.banco
        FROM parcelamentos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN contas ct ON p.conta_id = ct.id
        WHERE {cond}p.user_id = :uid
        ORDER BY p.data_primeira_parcela DESC
    """, {"uid": user_id})


def registrar_pagamento(id_: int, parcelas_pagas: int):
    _write(
        "UPDATE parcelamentos SET parcelas_pagas = :pagas WHERE id = :id",
        {"pagas": parcelas_pagas, "id": id_},
    )


def excluir_parcelamento(id_: int):
    _write("DELETE FROM parcelamentos WHERE id = :id", {"id": id_})


def parcelas_a_vencer_por_mes(meses=6, user_id=_UID):
    import datetime
    hoje = datetime.date.today()
    df = _read(
        "SELECT * FROM parcelamentos WHERE parcelas_pagas < total_parcelas AND user_id = :uid",
        {"uid": user_id},
    )
    if df.empty:
        return pd.DataFrame(columns=["mes", "total"])

    rows = []
    for _, p in df.iterrows():
        inicio = pd.to_datetime(p["data_primeira_parcela"])
        for i in range(int(p["parcelas_pagas"]), int(p["total_parcelas"])):
            data_parc = inicio + pd.DateOffset(months=i)
            if data_parc.date() >= hoje:
                # valor_parcela = valor_total / total_parcelas (3FN: coluna removida)
                vp = float(p["valor_total"]) / int(p["total_parcelas"])
                rows.append({"mes": data_parc.strftime("%Y-%m"), "total": vp})

    if not rows:
        return pd.DataFrame(columns=["mes", "total"])

    df_rows = pd.DataFrame(rows)
    cutoff = (hoje + pd.DateOffset(months=meses)).strftime("%Y-%m")
    df_rows = df_rows[df_rows["mes"] <= cutoff]
    return df_rows.groupby("mes")["total"].sum().reset_index()


# ── Investimentos ─────────────────────────────────────────────────────────────

def criar_investimento(dados: dict, user_id=_UID) -> int:
    dados = {**dados, "uid": user_id}
    inv_id = _insert_returning_id(
        """INSERT INTO investimentos
           (nome, tipo, instituicao, valor_investido, valor_atual,
            data_aplicacao, data_vencimento, rentabilidade_esperada, observacao, user_id)
           VALUES (:nome, :tipo, :instituicao, :valor_investido, :valor_atual,
                   :data_aplicacao, :data_vencimento, :rentabilidade_esperada, :observacao, :uid)
           RETURNING id""",
        dados,
    )
    _write(
        "INSERT INTO investimento_historico (investimento_id, data, valor) VALUES (:id, :data, :valor)",
        {"id": inv_id, "data": dados["data_aplicacao"], "valor": dados["valor_atual"]},
    )
    return inv_id


def listar_investimentos(apenas_ativos=True, user_id=_UID):
    cond = "i.ativo = 1 AND " if apenas_ativos else ""
    return _read(f"""
        SELECT i.*,
               ROUND(CAST(i.valor_atual - i.valor_investido AS NUMERIC), 2) AS rendimento,
               ROUND(CAST((i.valor_atual - i.valor_investido) / NULLIF(i.valor_investido, 0) * 100 AS NUMERIC), 2) AS rentabilidade_real
        FROM investimentos i
        WHERE {cond}i.user_id = :uid
        ORDER BY i.valor_atual DESC
    """, {"uid": user_id})


def atualizar_valor_investimento(id_: int, valor_atual: float, data: str):
    _write("UPDATE investimentos SET valor_atual = :valor WHERE id = :id", {"valor": valor_atual, "id": id_})
    _write(
        "INSERT INTO investimento_historico (investimento_id, data, valor) VALUES (:id, :data, :valor)",
        {"id": id_, "data": data, "valor": valor_atual},
    )


def resgatar_investimento(id_: int, valor_resgate: float, data: str):
    _write(
        "UPDATE investimentos SET ativo = 0, valor_atual = :valor WHERE id = :id",
        {"valor": valor_resgate, "id": id_},
    )
    _write(
        "INSERT INTO investimento_historico (investimento_id, data, valor) VALUES (:id, :data, :valor)",
        {"id": id_, "data": data, "valor": valor_resgate},
    )


def excluir_investimento(id_: int):
    _write("DELETE FROM investimento_historico WHERE investimento_id = :id", {"id": id_})
    _write("DELETE FROM investimentos WHERE id = :id", {"id": id_})


def historico_investimento(id_: int):
    return _read(
        "SELECT data, valor FROM investimento_historico WHERE investimento_id = :id ORDER BY data",
        {"id": id_},
    )


def resumo_investimentos(user_id=_UID):
    return _read("""
        SELECT tipo, COUNT(*) AS qtd,
               SUM(valor_investido) AS total_investido,
               SUM(valor_atual) AS total_atual
        FROM investimentos WHERE ativo = 1 AND user_id = :uid
        GROUP BY tipo ORDER BY total_atual DESC
    """, {"uid": user_id})


# ── Orçamentos ────────────────────────────────────────────────────────────────

def salvar_orcamento(categoria_id: int, mes: str, valor_limite: float, user_id=_UID):
    _write(
        """INSERT INTO orcamentos (categoria_id, mes, valor_limite, user_id)
           VALUES (:categoria_id, :mes, :valor_limite, :uid)
           ON CONFLICT (categoria_id, mes) DO UPDATE SET valor_limite = EXCLUDED.valor_limite""",
        {"categoria_id": categoria_id, "mes": mes, "valor_limite": valor_limite, "uid": user_id},
    )


def excluir_orcamento(categoria_id: int, mes: str, user_id=_UID):
    _write(
        "DELETE FROM orcamentos WHERE categoria_id = :cat AND mes = :mes AND user_id = :uid",
        {"cat": categoria_id, "mes": mes, "uid": user_id},
    )


def listar_orcamentos(mes: str, user_id=_UID):
    mes_col = _month_sql("t.data")
    df = _read(f"""
        SELECT c.id AS categoria_id, c.nome AS categoria, c.cor,
               COALESCE(o.valor_limite, 0) AS limite,
               COALESCE(SUM(t.valor), 0) AS gasto
        FROM categorias c
        LEFT JOIN orcamentos o ON o.categoria_id = c.id AND o.mes = :mes
        LEFT JOIN transacoes t ON t.categoria_id = c.id
            AND {mes_col} = :mes
            AND t.tipo = 'despesa'
        WHERE c.tipo = 'despesa' AND c.user_id = :uid
        GROUP BY c.id, c.nome, c.cor, o.valor_limite
        ORDER BY c.nome
    """, {"mes": mes, "uid": user_id})
    df["saldo"] = df["limite"] - df["gasto"]
    df["pct"] = df.apply(
        lambda r: min(r["gasto"] / r["limite"] * 100, 100) if r["limite"] > 0 else 0, axis=1
    )
    return df
