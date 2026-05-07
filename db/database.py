import os
import socket
from urllib.parse import urlparse
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
    raw = ""
    try:
        import streamlit as st
        raw = st.secrets.get("DATABASE_URL", "")
    except Exception:
        pass
    if not raw:
        raw = os.environ.get("DATABASE_URL", "")

    if raw and raw.startswith("postgresql://"):
        host = raw.split("@")[-1].split(":")[0].split("/")[0]
        if host not in _PLACEHOLDER_HOSTS and "[" not in host:
            return raw

    local_db = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "orcamento.db")
    )
    os.makedirs(os.path.dirname(local_db), exist_ok=True)
    return f"sqlite:///{local_db}"


def _pg_connect_args(url: str) -> dict:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    is_pooler = "pooler.supabase.com" in hostname
    args = {"sslmode": "disable" if is_pooler else "require"}
    try:
        if hostname:
            ipv4 = socket.getaddrinfo(hostname, parsed.port or 5432, socket.AF_INET)
            if ipv4:
                args["hostaddr"] = ipv4[0][4][0]
    except Exception:
        pass
    return args


def get_engine():
    global _engine
    if _engine is None:
        url = _get_url()
        if url.startswith("postgresql"):
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args=_pg_connect_args(url),
            )
        else:
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def dialect() -> str:
    return get_engine().dialect.name


def _pk() -> str:
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect() == "sqlite" else "BIGSERIAL PRIMARY KEY"


def _ts() -> str:
    return "TIMESTAMP" if dialect() == "sqlite" else "TIMESTAMPTZ"


def init_db():
    pk, ts = _pk(), _ts()
    engine = get_engine()

    # ── Cria tabelas ──────────────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS usuarios (
                id {pk},
                email TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL DEFAULT '',
                senha_hash TEXT NOT NULL DEFAULT '',
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS categorias (
                id {pk},
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('despesa', 'receita')),
                cor TEXT DEFAULT '#888888',
                parent_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                natureza TEXT DEFAULT 'nao_classificado',
                user_id TEXT NOT NULL DEFAULT 'default'
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS contas (
                id {pk},
                nome TEXT NOT NULL,
                banco TEXT NOT NULL,
                tipo TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'default'
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
                user_id TEXT NOT NULL DEFAULT 'default',
                criado_em {ts} DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS importacoes (
                id {pk},
                arquivo TEXT NOT NULL,
                banco TEXT NOT NULL,
                total_transacoes INTEGER,
                user_id TEXT NOT NULL DEFAULT 'default',
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
                user_id TEXT NOT NULL DEFAULT 'default',
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
                user_id TEXT NOT NULL DEFAULT 'default',
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

    # ── Migrações de colunas (cada ALTER em transação isolada) ────────────────
    migrations = [
        "ALTER TABLE usuarios ADD COLUMN nome TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE usuarios ADD COLUMN senha_hash TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE categorias ADD COLUMN parent_id INTEGER REFERENCES categorias(id)",
        "ALTER TABLE categorias ADD COLUMN natureza TEXT DEFAULT 'nao_classificado'",
        "ALTER TABLE categorias ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE contas ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE transacoes ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE importacoes ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE parcelamentos ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE investimentos ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'",
    ]
    for ddl in migrations:
        try:
            with engine.begin() as _conn:
                _conn.execute(text(ddl))
        except Exception:
            pass  # coluna já existe

    # ── PostgreSQL: migra UNIQUE(nome) → UNIQUE(nome, user_id) ───────────────
    if dialect() == "postgresql":
        for ddl in [
            "ALTER TABLE categorias DROP CONSTRAINT IF EXISTS categorias_nome_key",
            "ALTER TABLE categorias ADD CONSTRAINT categorias_nome_user_uq UNIQUE(nome, user_id)",
        ]:
            try:
                with engine.begin() as _conn:
                    _conn.execute(text(ddl))
            except Exception:
                pass  # constraint já migrada

    # ── Categorias padrão para o usuário 'default' (banco local/legado) ───────
    with engine.begin() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM categorias WHERE user_id = 'default'"
        ))
        if result.scalar() == 0:
            for nome, tipo, cor, natureza in DEFAULT_CATEGORIES:
                conn.execute(text(
                    "INSERT INTO categorias (nome, tipo, cor, natureza, user_id) "
                    "VALUES (:nome, :tipo, :cor, :natureza, 'default')"
                ), {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza})


def init_user(user_id: str):
    """Cria categorias padrão para um novo usuário (idempotente)."""
    if not user_id or user_id == "default":
        return
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM categorias WHERE user_id = :uid"),
            {"uid": user_id},
        )
        if result.scalar() == 0:
            for nome, tipo, cor, natureza in DEFAULT_CATEGORIES:
                conn.execute(text(
                    "INSERT INTO categorias (nome, tipo, cor, natureza, user_id) "
                    "VALUES (:nome, :tipo, :cor, :natureza, :uid)"
                ), {"nome": nome, "tipo": tipo, "cor": cor, "natureza": natureza, "uid": user_id})
