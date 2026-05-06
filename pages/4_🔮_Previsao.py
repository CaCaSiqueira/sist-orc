import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from auth import require_login, sidebar_user
from db.queries import evolucao_mensal, listar_transacoes

st.set_page_config(page_title="Previsão", page_icon="🔮", layout="wide")
uid = require_login()
sidebar_user()

st.title("🔮 Previsão de Gastos")

df_evo = evolucao_mensal(user_id=uid)

if df_evo.empty or len(df_evo["mes"].unique()) < 2:
    st.info("Você precisa de pelo menos 2 meses de dados para gerar previsões.")
    st.stop()

pivot = df_evo.pivot_table(index="mes", columns="tipo", values="total", aggfunc="sum").fillna(0).reset_index()
pivot["saldo"] = pivot.get("receita", 0) - pivot.get("despesa", 0)

st.subheader("Histórico e Projeção")
meses_previsao = st.slider("Meses a projetar", 1, 6, 3)


def media_movel(series, janela=3):
    return series.rolling(window=min(janela, len(series)), min_periods=1).mean().iloc[-1]


ult_despesa = media_movel(pivot.get("despesa", pd.Series([0])))
ult_receita = media_movel(pivot.get("receita", pd.Series([0])))

ultimo_mes = pd.Period(pivot["mes"].iloc[-1], freq="M")
meses_fut = [(ultimo_mes + i).strftime("%Y-%m") for i in range(1, meses_previsao + 1)]

df_prev = pd.DataFrame({
    "mes":     meses_fut,
    "despesa": [ult_despesa] * meses_previsao,
    "receita": [ult_receita] * meses_previsao,
})
df_prev["saldo"] = df_prev["receita"] - df_prev["despesa"]
df_prev["tipo"]  = "previsão"
pivot["tipo"]    = "histórico"

fig = go.Figure()
for col, cor, nome in [("despesa", "#FF6B6B", "Despesa"), ("receita", "#00B894", "Receita")]:
    if col in pivot.columns:
        fig.add_trace(go.Bar(x=pivot["mes"], y=pivot[col], name=f"{nome} (histórico)", marker_color=cor, opacity=0.85))
    fig.add_trace(go.Bar(x=df_prev["mes"], y=df_prev[col], name=f"{nome} (previsão)", marker_color=cor, opacity=0.4, marker_pattern_shape="/"))

fig.update_layout(barmode="group", xaxis_title="Mês", yaxis_title="R$",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig, use_container_width=True)

fig2 = go.Figure()
todos_meses = list(pivot["mes"]) + meses_fut
todos_saldo = list(pivot["saldo"]) + list(df_prev["saldo"])
cores = ["#6C5CE7"] * len(pivot) + ["#A29BFE"] * meses_previsao
fig2.add_trace(go.Scatter(x=todos_meses, y=todos_saldo, mode="lines+markers",
                          line=dict(color="#6C5CE7", width=2), marker=dict(color=cores, size=8)))
fig2.add_hline(y=0, line_dash="dash", line_color="gray")
fig2.add_vrect(x0=meses_fut[0], x1=meses_fut[-1], fillcolor="lightblue", opacity=0.15, annotation_text="Previsão")
fig2.update_layout(title="Projeção de Saldo", xaxis_title="Mês", yaxis_title="R$")
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Resumo da Projeção")
fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
df_prev_show = df_prev[["mes", "receita", "despesa", "saldo"]].copy()
for c in ["receita", "despesa", "saldo"]:
    df_prev_show[c] = df_prev_show[c].apply(fmt)
df_prev_show.columns = ["Mês", "Receita Prevista", "Despesa Prevista", "Saldo Previsto"]
st.dataframe(df_prev_show, use_container_width=True, hide_index=True)
st.caption("Previsão baseada na média móvel dos últimos 3 meses. Os valores são estimativas.")
