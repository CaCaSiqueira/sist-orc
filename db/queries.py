import hashlib
import os
import base64

import pandas as pd
from sqlalchemy import text
from .database import get_engine, dialect

_UID = "default"  # fallback quando não há login


# ── Usuários ──────────────────────────────────────────────────────────────────

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
        {"e": email},
    )
    if row.empty:
        return None
    r = row.iloc[0]
    return {"id": str(int(r["id"])), "nome": str(r["nome"]), "senha_hash": str(r["senha_hash"])}


def criar_usuario(email: str, nome: str, senha: str) -> str:
    """Cria usuário com senha criptografada. Retorna user_id como string."""
    uid = _insert_returning_id(
        "INSERT INTO usuarios (email, nome, senha_hash) VALUES (:e, :n, :h) RETURNING id",
        {"e": email, "n": nome, "h": _hash_senha(senha)},
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
    sql = """
        SELECT c.id, c.nome, c.tipo, c.cor, c.parent_id, c.natureza,
               p.nome AS parent_nome
        FROM categorias c
        LEFT JOIN categorias p ON c.parent_id = p.id
        WHERE c.user_id = :uid {extra}
        ORDER BY COALESCE(p.nome, c.nome), c.parent_id NULLS FIRST, c.nome
    """
    extra = "AND c.tipo = :tipo" if tipo else ""
    params = {"uid": user_id}
    if tipo:
        params["tipo"] = tipo
    return _read(sql.format(extra=extra), params)


def listar_categorias_arvore(tipo=None, user_id=_UID):
    df = listar_categorias(tipo, user_id)
    pais = df[df["parent_id"].isna()].to_dict("records")
    filhos_map = {}
    for _, row in df[df["parent_id"].notna()].iterrows():
        pid = int(row["parent_id"])
        filhos_map.setdefault(pid, []).append(row.to_dict())
    return pais, filhos_map


def opcoes_categoria(tipo=None, user_id=_UID):
    df = listar_categorias(tipo, user_id)
    pais = df[df["parent_id"].isna()].copy()
    filhos = df[df["parent_id"].notna()].copy()

    labels, id_map = [], {}
    for _, p in pais.iterrows():
        labels.append(p["nome"])
        id_map[p["nome"]] = int(p["id"])
        subs = filhos[filhos["parent_id"] == p["id"]].sort_values("nome")
        for _, s in subs.iterrows():
            label = f"  ↳ {s['nome']}"
            labels.append(label)
            id_map[label] = int(s["id"])
    return labels, id_map


def criar_categoria(nome, tipo, cor="#888888", parent_id=None, natureza="nao_classificado", user_id=_UID):
    from sqlalchemy.exc import IntegrityError
    try:
        _write(
            "INSERT INTO categorias (nome, tipo, cor, parent_id, natureza, user_id) "
            "VALUES (:nome, :tipo, :cor, :parent_id, :natureza, :uid)",
            {"nome": nome, "tipo": tipo, "cor": cor, "parent_id": parent_id,
             "natureza": natureza, "uid": user_id},
        )
    except IntegrityError:
        raise ValueError(f"Já existe uma categoria com o nome '{nome}' neste nível.")


def editar_categoria(id_, nome, tipo, cor, natureza="nao_classificado", user_id=_UID):
    _write(
        "UPDATE categorias SET nome = :nome, tipo = :tipo, cor = :cor, natureza = :natureza "
        "WHERE id = :id AND user_id = :uid",
        {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza, "id": id_, "uid": user_id},
    )


def atualizar_natureza_categoria(id_: int, natureza: str, user_id=_UID):
    _write(
        "UPDATE categorias SET natureza = :natureza WHERE id = :id AND user_id = :uid",
        {"natureza": natureza, "id": id_, "uid": user_id},
    )


def excluir_categoria(id_, user_id=_UID):
    _write("UPDATE categorias SET parent_id = NULL WHERE parent_id = :id AND user_id = :uid",
           {"id": id_, "uid": user_id})
    _write("UPDATE transacoes SET categoria_id = NULL WHERE categoria_id = :id AND user_id = :uid",
           {"id": id_, "uid": user_id})
    _write("DELETE FROM categorias WHERE id = :id AND user_id = :uid",
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

def registrar_importacao(arquivo, banco, total, user_id=_UID):
    return _insert_returning_id(
        "INSERT INTO importacoes (arquivo, banco, total_transacoes, user_id) "
        "VALUES (:arquivo, :banco, :total, :uid) RETURNING id",
        {"arquivo": arquivo, "banco": banco, "total": total, "uid": user_id},
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
    _write_many(
        """INSERT INTO transacoes
           (data, descricao, valor, tipo, categoria_id, conta_id, observacao, importacao_id, user_id)
           VALUES (:data, :descricao, :valor, :tipo, :categoria_id, :conta_id,
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
    if filtros.get("categoria_id") is not None:
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
               c.nome AS categoria, c.cor,
               ct.nome AS conta, ct.banco,
               t.observacao
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
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
        SELECT c.nome AS categoria, c.cor, t.tipo,
               SUM(t.valor) AS total, COUNT(*) AS qtd
        FROM transacoes t
        LEFT JOIN categorias c ON t.categoria_id = c.id
        {where_sql}
        GROUP BY c.nome, c.cor, t.tipo
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
    dados = {**dados, "uid": user_id}
    return _insert_returning_id(
        """INSERT INTO parcelamentos
           (descricao, valor_total, valor_parcela, total_parcelas, parcelas_pagas,
            data_primeira_parcela, categoria_id, conta_id, observacao, user_id)
           VALUES (:descricao, :valor_total, :valor_parcela, :total_parcelas, :parcelas_pagas,
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
                rows.append({"mes": data_parc.strftime("%Y-%m"), "total": float(p["valor_parcela"])})

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

def salvar_orcamento(categoria_id: int, mes: str, valor_limite: float):
    _write(
        """INSERT INTO orcamentos (categoria_id, mes, valor_limite)
           VALUES (:categoria_id, :mes, :valor_limite)
           ON CONFLICT (categoria_id, mes) DO UPDATE SET valor_limite = EXCLUDED.valor_limite""",
        {"categoria_id": categoria_id, "mes": mes, "valor_limite": valor_limite},
    )


def excluir_orcamento(categoria_id: int, mes: str):
    _write(
        "DELETE FROM orcamentos WHERE categoria_id = :cat AND mes = :mes",
        {"cat": categoria_id, "mes": mes},
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
