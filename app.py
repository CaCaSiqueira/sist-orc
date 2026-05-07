import streamlit as st
from pathlib import Path
from db.database import init_db
from auth import require_login, sidebar_user

st.set_page_config(
    page_title="Finanças Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Logo no topo da página
_logo = Path(__file__).parent / "assets" / "logo.svg"
if _logo.exists():
    st.image(str(_logo), width=380)

init_db()
uid = require_login()
sidebar_user()

st.title("💰 Orçamento Pessoal")
st.markdown("""
Use o menu lateral para navegar entre as seções:

| Seção | Descrição |
|---|---|
| 📥 **Importar Extrato** | Faça upload de extratos e categorize as transações |
| 📋 **Transações** | Visualize, edite e filtre todas as transações |
| 📊 **Dashboard** | Gráficos e resumos do seu orçamento |
| 🔮 **Previsão** | Estimativas de gastos futuros |
| ⚙️ **Configurações** | Gerencie categorias e contas |
""")

col1, col2, col3 = st.columns(3)
from db.queries import listar_transacoes
import pandas as pd

df = listar_transacoes(user_id=uid)
if not df.empty:
    receitas = df[df["tipo"] == "receita"]["valor"].sum()
    despesas = df[df["tipo"] == "despesa"]["valor"].sum()
    saldo = receitas - despesas
    fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    with col1:
        st.metric("Total Receitas", fmt(receitas))
    with col2:
        st.metric("Total Despesas", fmt(despesas))
    with col3:
        st.metric("Saldo", fmt(saldo))
else:
    st.info("Nenhuma transação cadastrada ainda. Comece importando um extrato!")
