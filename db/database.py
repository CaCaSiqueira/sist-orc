import os
from sqlalchemy import create_engine, text

_engine = None

DEFAULT_CATEGORIES = [
    ("Alimentação",     "despesa", "#FF6B6B", "variavel"),
    ("Transporte",      "despesa", "#4ECDC4", "variavel"),
    ("Moradia",         "despesa", "#45B7D1", "fixo"),
    ("Saúde",           "despesa", "#96CEB4", "fixo"),
    ("Lazer",           "despesa", "#FFEAA7", "variavel"),
    ("Educação",        "despesa", "#DDA0DD", "fixo"),
    ("Compras",         "despesa", "#F0A500", "variavel"),
    ("Serviços",        "despesa", "#A29BFE", "fixo"),
    ("Outros (despesa)","despesa", "#B2BEC3", "nao_classificado"),
    ("Salário",         "receita", "#00B894", "nao_classificado"),
    ("Freelance",       "receita", "#00CEC9", "nao_classificado"),
    ("Investimentos",   "receita", "#6C5CE7", "nao_classificado"),
    ("Outros (receita)","receita", "#55EFC4", "nao_classificado"),
]

_PLACEHOLDER_HOSTS = {"SEU-HOST", "[SEU-HOST]", "localhost_placeholder"}


def _get_url() -> str:
    """Retorna a URL do banco. Usa SQLite como fallback quando Supabase não está configurado."""
    raw = ""
    try:
        import streamlit as st
        raw = st.secrets.get("DATABASE_URL", "")
    except Exception:
        pass
    if not raw:
        raw = os.environ.get("DATABASE_URL", "")

    # Verifica se é um placeholder ou URL inválida
    if raw and raw.startswith("postgresql://"):
        host = raw.split("@")[-1].split(":")[0].split("/")[0]
        if host not in _PLACEHOLDER_HOSTS and "[" not in host:
            return raw  # URL real do Supabase

    # Fallback: SQLite local
    local_db = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "orcamento.db")
    )
    os.makedirs(os.path.dirname(local_db), exist_ok=True)
    return f"sqlite:///{local_db}"


def get_engine():
    global _engine
    if _engine is None:
        url = _get_url()
        if url.startswith("postgresql"):
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args={"sslmode": "require"},
            )
        else:
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def dialect() -> str:
    return get_engine().dialect.name  # 'sqlite' ou 'postgresql'


def _pk() -> str:
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect() == "sqlite" else "BIGSERIAL PRIMARY KEY"


def _ts() -> str:
    return "TIMESTAMP" if dialect() == "sqlite" else "TIMESTAMPTZ"


def init_db():
    pk, ts = _pk(), _ts()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS categorias (
                id {pk},
                nome TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL CHECK(tipo IN ('despesa', 'receita')),
                cor TEXT DEFAULT '#888888',
                parent_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                natureza TEXT DEFAULT 'nao_classificado'
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS contas (
                id {pk},
                nome TEXT NOT NULL,
                banco TEXT NOT NULL,
                tipo TEXT NOT NULL
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS transacoes (
                id {pk},
                data TEXT NOT NULL,
                descricao TEXT NOT NULL,
                valor NUMERIC NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('despesa', 'receita')),
                categoria_id INTEGER REFERENCES categorias(id),
                conta_id INTEGER REFERENCES contas(id),
                observacao TEXT,
                importacao_id INTEGER,
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS importacoes (
                id {pk},
                arquivo TEXT NOT NULL,
                banco TEXT NOT NULL,
                total_transacoes INTEGER,
                importado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS parcelamentos (
                id {pk},
                descricao TEXT NOT NULL,
                valor_total NUMERIC NOT NULL,
                valor_parcela NUMERIC NOT NULL,
                total_parcelas INTEGER NOT NULL,
                parcelas_pagas INTEGER DEFAULT 0,
                data_primeira_parcela TEXT NOT NULL,
                categoria_id INTEGER REFERENCES categorias(id),
                conta_id INTEGER REFERENCES contas(id),
                observacao TEXT,
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS investimentos (
                id {pk},
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                instituicao TEXT,
                valor_investido NUMERIC NOT NULL,
                valor_atual NUMERIC NOT NULL,
                data_aplicacao TEXT NOT NULL,
                data_vencimento TEXT,
                rentabilidade_esperada NUMERIC,
                ativo INTEGER DEFAULT 1,
                observacao TEXT,
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS investimento_historico (
                id {pk},
                investimento_id INTEGER REFERENCES investimentos(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                valor NUMERIC NOT NULL,
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS orcamentos (
                id {pk},
                categoria_id INTEGER NOT NULL REFERENCES categorias(id),
                mes TEXT NOT NULL,
                valor_limite NUMERIC NOT NULL,
                UNIQUE(categoria_id, mes)
            )
        """))

        for col_ddl in [
            "ALTER TABLE categorias ADD COLUMN parent_id INTEGER REFERENCES categorias(id)",
            "ALTER TABLE categorias ADD COLUMN natureza TEXT DEFAULT 'nao_classificado'",
        ]:
            try:
                conn.execute(text(col_ddl))
            except Exception:
                pass  # coluna já existe

        for nome, tipo, cor, natureza in DEFAULT_CATEGORIES:
            conn.execute(text(
                "INSERT INTO categorias (nome, tipo, cor, natureza) VALUES (:nome, :tipo, :cor, :natureza) "
                "ON CONFLICT (nome) DO NOTHING"
            ), {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza})
