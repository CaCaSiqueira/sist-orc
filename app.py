import streamlit as st
from db.database import init_db

st.set_page_config(
    page_title="Orçamento Pessoal",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.title("💰 Orçamento Pessoal")
st.markdown("""
Bem-vindo ao seu sistema de controle financeiro.

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
from db.queries import listar_transacoes, evolucao_mensal
import pandas as pd

df = listar_transacoes()
if not df.empty:
    receitas = df[df["tipo"] == "receita"]["valor"].sum()
    despesas = df[df["tipo"] == "despesa"]["valor"].sum()
    saldo = receitas - despesas

    with col1:
        st.metric("Total Receitas", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col2:
        st.metric("Total Despesas", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col3:
        st.metric("Saldo", f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                  delta_color="normal")
else:
    st.info("Nenhuma transação cadastrada ainda. Comece importando um extrato!")
