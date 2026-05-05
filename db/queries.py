import pandas as pd
from sqlalchemy import text
from .database import get_engine, dialect


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
    """INSERT ... RETURNING id — funciona em SQLite 3.35+ e PostgreSQL."""
    with get_engine().begin() as conn:
        result = conn.execute(text(sql_returning), params or {})
        row = result.fetchone()
        return int(row[0]) if row else None


def _month_sql(col: str) -> str:
    """Formata coluna de data como 'YYYY-MM' para SQLite e PostgreSQL."""
    if dialect() == "sqlite":
        return f"strftime('%Y-%m', {col})"
    return f"to_char({col}::date, 'YYYY-MM')"


# ── Categorias ────────────────────────────────────────────────────────────────

def listar_categorias(tipo=None):
    """Retorna todas as categorias com coluna parent_nome para exibição."""
    sql = """
        SELECT c.id, c.nome, c.tipo, c.cor, c.parent_id, c.natureza,
               p.nome AS parent_nome
        FROM categorias c
        LEFT JOIN categorias p ON c.parent_id = p.id
        {where}
        ORDER BY COALESCE(p.nome, c.nome), c.parent_id NULLS FIRST, c.nome
    """
    if tipo:
        return _read(sql.format(where="WHERE c.tipo = :tipo"), {"tipo": tipo})
    return _read(sql.format(where=""))


def listar_categorias_arvore(tipo=None):
    """
    Retorna dict com estrutura {parent_id: {"info": row, "filhos": [row, ...]}}
    para renderização hierárquica.
    """
    df = listar_categorias(tipo)
    pais = df[df["parent_id"].isna()].to_dict("records")
    filhos_map = {}
    for _, row in df[df["parent_id"].notna()].iterrows():
        pid = int(row["parent_id"])
        filhos_map.setdefault(pid, []).append(row.to_dict())
    return pais, filhos_map


def opcoes_categoria(tipo=None):
    """
    Retorna lista e dict para uso em selectbox:
      - lista de labels formatados (com indentação para subcategorias)
      - dict label → id
    """
    df = listar_categorias(tipo)
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


def criar_categoria(nome, tipo, cor="#888888", parent_id=None, natureza="nao_classificado"):
    _write(
        "INSERT INTO categorias (nome, tipo, cor, parent_id, natureza) VALUES (:nome, :tipo, :cor, :parent_id, :natureza)",
        {"nome": nome, "tipo": tipo, "cor": cor, "parent_id": parent_id, "natureza": natureza},
    )


def editar_categoria(id_, nome, tipo, cor, natureza="nao_classificado"):
    _write(
        "UPDATE categorias SET nome = :nome, tipo = :tipo, cor = :cor, natureza = :natureza WHERE id = :id",
        {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza, "id": id_},
    )


def atualizar_natureza_categoria(id_: int, natureza: str):
    _write(
        "UPDATE categorias SET natureza = :natureza WHERE id = :id",
        {"natureza": natureza, "id": id_},
    )


def excluir_categoria(id_):
    # promove filhos para sem-pai antes de excluir
    _write("UPDATE categorias SET parent_id = NULL WHERE parent_id = :id", {"id": id_})
    _write("UPDATE transacoes SET categoria_id = NULL WHERE categoria_id = :id", {"id": id_})
    _write("DELETE FROM categorias WHERE id = :id", {"id": id_})


# ── Contas ────────────────────────────────────────────────────────────────────

def listar_contas():
    return _read("SELECT * FROM contas ORDER BY banco, nome")


def criar_conta(nome, banco, tipo):
    return _insert_returning_id(
        "INSERT INTO contas (nome, banco, tipo) VALUES (:nome, :banco, :tipo) RETURNING id",
        {"nome": nome, "banco": banco, "tipo": tipo},
    )


def get_ou_criar_conta(nome, banco, tipo):
    existing = _read(
        "SELECT id FROM contas WHERE nome = :nome AND banco = :banco",
        {"nome": nome, "banco": banco},
    )
    if not existing.empty:
        return int(existing.iloc[0]["id"])
    return _insert_returning_id(
        "INSERT INTO contas (nome, banco, tipo) VALUES (:nome, :banco, :tipo) RETURNING id",
        {"nome": nome, "banco": banco, "tipo": tipo},
    )


# ── Importações ───────────────────────────────────────────────────────────────

def registrar_importacao(arquivo, banco, total):
    return _insert_returning_id(
        "INSERT INTO importacoes (arquivo, banco, total_transacoes) VALUES (:arquivo, :banco, :total) RETURNING id",
        {"arquivo": arquivo, "banco": banco, "total": total},
    )


def listar_importacoes():
    return _read("SELECT * FROM importacoes ORDER BY importado_em DESC")


# ── Transações ────────────────────────────────────────────────────────────────

def inserir_transacoes(transacoes: list[dict]):
    _write_many(
        """INSERT INTO transacoes (data, descricao, valor, tipo, categoria_id, conta_id, observacao, importacao_id)
           VALUES (:data, :descricao, :valor, :tipo, :categoria_id, :conta_id, :observacao, :importacao_id)""",
        transacoes,
    )


def listar_transacoes(filtros: dict = None):
    filtros = filtros or {}
    where, params = [], {}

    if filtros.get("data_inicio"):
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = filtros["data_inicio"]
    if filtros.get("data_fim"):
        where.append("t.data <= :data_fim")
        params["data_fim"] = filtros["data_fim"]
    if filtros.get("tipo"):
        where.append("t.tipo = :tipo")
        params["tipo"] = filtros["tipo"]
    if filtros.get("categoria_id"):
        where.append("t.categoria_id = :categoria_id")
        params["categoria_id"] = filtros["categoria_id"]
    if filtros.get("conta_id"):
        where.append("t.conta_id = :conta_id")
        params["conta_id"] = filtros["conta_id"]

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

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


def resumo_por_categoria(data_inicio=None, data_fim=None):
    where, params = [], {}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

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


def resumo_por_natureza(data_inicio=None, data_fim=None):
    where, params = [], {}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

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


def evolucao_fixo_variavel(data_inicio=None, data_fim=None):
    where, params = [], {}
    if data_inicio:
        where.append("t.data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("t.data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = ("WHERE t.tipo = 'despesa'" + (" AND " + " AND ".join(where) if where else ""))

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


def evolucao_mensal(data_inicio=None, data_fim=None):
    where, params = [], {}
    if data_inicio:
        where.append("data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        where.append("data <= :data_fim")
        params["data_fim"] = data_fim
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

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

def criar_parcelamento(dados: dict) -> int:
    return _insert_returning_id(
        """INSERT INTO parcelamentos
           (descricao, valor_total, valor_parcela, total_parcelas, parcelas_pagas,
            data_primeira_parcela, categoria_id, conta_id, observacao)
           VALUES (:descricao, :valor_total, :valor_parcela, :total_parcelas, :parcelas_pagas,
                   :data_primeira_parcela, :categoria_id, :conta_id, :observacao)
           RETURNING id""",
        dados,
    )


def listar_parcelamentos(apenas_ativos=False):
    where = "WHERE p.parcelas_pagas < p.total_parcelas" if apenas_ativos else ""
    return _read(f"""
        SELECT p.*, c.nome AS categoria, ct.nome AS conta, ct.banco
        FROM parcelamentos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN contas ct ON p.conta_id = ct.id
        {where}
        ORDER BY p.data_primeira_parcela DESC
    """)


def registrar_pagamento(id_: int, parcelas_pagas: int):
    _write(
        "UPDATE parcelamentos SET parcelas_pagas = :pagas WHERE id = :id",
        {"pagas": parcelas_pagas, "id": id_},
    )


def excluir_parcelamento(id_: int):
    _write("DELETE FROM parcelamentos WHERE id = :id", {"id": id_})


def parcelas_a_vencer_por_mes(meses=6):
    import datetime
    hoje = datetime.date.today()
    df = _read("SELECT * FROM parcelamentos WHERE parcelas_pagas < total_parcelas")
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

def criar_investimento(dados: dict) -> int:
    inv_id = _insert_returning_id(
        """INSERT INTO investimentos
           (nome, tipo, instituicao, valor_investido, valor_atual,
            data_aplicacao, data_vencimento, rentabilidade_esperada, observacao)
           VALUES (:nome, :tipo, :instituicao, :valor_investido, :valor_atual,
                   :data_aplicacao, :data_vencimento, :rentabilidade_esperada, :observacao)
           RETURNING id""",
        dados,
    )
    _write(
        "INSERT INTO investimento_historico (investimento_id, data, valor) VALUES (:id, :data, :valor)",
        {"id": inv_id, "data": dados["data_aplicacao"], "valor": dados["valor_atual"]},
    )
    return inv_id


def listar_investimentos(apenas_ativos=True):
    where = "WHERE i.ativo = 1" if apenas_ativos else ""
    return _read(f"""
        SELECT i.*,
               ROUND(CAST(i.valor_atual - i.valor_investido AS NUMERIC), 2) AS rendimento,
               ROUND(CAST((i.valor_atual - i.valor_investido) / NULLIF(i.valor_investido, 0) * 100 AS NUMERIC), 2) AS rentabilidade_real
        FROM investimentos i
        {where}
        ORDER BY i.valor_atual DESC
    """)


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


def resumo_investimentos():
    return _read("""
        SELECT tipo, COUNT(*) AS qtd,
               SUM(valor_investido) AS total_investido,
               SUM(valor_atual) AS total_atual
        FROM investimentos WHERE ativo = 1
        GROUP BY tipo ORDER BY total_atual DESC
    """)


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


def listar_orcamentos(mes: str):
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
        WHERE c.tipo = 'despesa'
        GROUP BY c.id, c.nome, c.cor, o.valor_limite
        ORDER BY c.nome
    """, {"mes": mes})
    df["saldo"] = df["limite"] - df["gasto"]
    df["pct"] = df.apply(
        lambda r: min(r["gasto"] / r["limite"] * 100, 100) if r["limite"] > 0 else 0, axis=1
    )
    return df
