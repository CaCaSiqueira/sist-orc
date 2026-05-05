import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
from db.queries import (
    listar_investimentos, criar_investimento, atualizar_valor_investimento,
    resgatar_investimento, excluir_investimento, historico_investimento,
    resumo_investimentos,
)

st.set_page_config(page_title="Investimentos", page_icon="📈", layout="wide")
st.title("📈 Investimentos")

fmt = lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
fmt_pct = lambda v: f"{v:+.2f}%"

TIPOS = ["Renda Fixa", "CDB", "LCI/LCA", "Tesouro Direto", "Ações", "FII", "Crypto", "Poupança", "Outros"]
CORES_TIPO = {
    "Renda Fixa": "#00B894", "CDB": "#00CEC9", "LCI/LCA": "#55EFC4",
    "Tesouro Direto": "#6C5CE7", "Ações": "#FDCB6E", "FII": "#E17055",
    "Crypto": "#A29BFE", "Poupança": "#74B9FF", "Outros": "#B2BEC3",
}

df_ativos = listar_investimentos(apenas_ativos=True)
df_todos = listar_investimentos(apenas_ativos=False)

# ── KPIs ──────────────────────────────────────────────────────────────────────
if not df_ativos.empty:
    total_inv = df_ativos["valor_investido"].sum()
    total_atual = df_ativos["valor_atual"].sum()
    rendimento = total_atual - total_inv
    rent_pct = (rendimento / total_inv * 100) if total_inv else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total investido", fmt(total_inv))
    k2.metric("Valor atual", fmt(total_atual))
    k3.metric("Rendimento", fmt(rendimento), delta=f"{rent_pct:+.2f}%")
    k4.metric("Ativos", len(df_ativos))
else:
    st.info("Nenhum investimento cadastrado. Use o formulário abaixo para começar.")

st.markdown("---")

# ── Tabs principais ───────────────────────────────────────────────────────────
tab_lista, tab_novo, tab_resgatados = st.tabs(["📋 Carteira", "➕ Novo Investimento", "✅ Resgatados"])

# ── Carteira ──────────────────────────────────────────────────────────────────
with tab_lista:
    if df_ativos.empty:
        st.info("Nenhum investimento ativo.")
    else:
        # gráficos de distribuição
        df_resumo = resumo_investimentos()
        col_pizza, col_barras = st.columns(2)

        with col_pizza:
            fig_pie = px.pie(
                df_resumo, values="total_atual", names="tipo",
                title="Distribuição por tipo (valor atual)",
                hole=0.45,
                color="tipo",
                color_discrete_map=CORES_TIPO,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_barras:
            df_bar = df_ativos.groupby("instituicao")[["valor_investido", "valor_atual"]].sum().reset_index()
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name="Investido", x=df_bar["instituicao"], y=df_bar["valor_investido"], marker_color="#74B9FF"))
            fig_bar.add_trace(go.Bar(name="Atual", x=df_bar["instituicao"], y=df_bar["valor_atual"], marker_color="#00B894"))
            fig_bar.update_layout(barmode="group", title="Por instituição", xaxis_title="", yaxis_title="R$")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # Cards por investimento
        for _, inv in df_ativos.iterrows():
            cor = CORES_TIPO.get(inv["tipo"], "#888")
            rendimento = float(inv["rendimento"])
            rent_pct = float(inv["rentabilidade_real"])
            cor_rend = "#00B894" if rendimento >= 0 else "#FF6B6B"

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 3])

                with c1:
                    st.markdown(f"**{inv['nome']}**")
                    st.caption(f"🏷️ {inv['tipo']}  ·  🏦 {inv['instituicao'] or '—'}")
                    st.caption(f"📅 Aplicado em {pd.to_datetime(inv['data_aplicacao']).strftime('%d/%m/%Y')}"
                               + (f"  ·  Vence em {pd.to_datetime(inv['data_vencimento']).strftime('%d/%m/%Y')}"
                                  if inv.get("data_vencimento") else ""))

                with c2:
                    st.metric("Investido", fmt(inv["valor_investido"]))

                with c3:
                    st.metric("Atual", fmt(inv["valor_atual"]),
                              delta=f"{fmt_pct(rent_pct)} ({fmt(rendimento)})")

                with c4:
                    with st.expander("Atualizar / Resgatar"):
                        novo_val = st.number_input(
                            "Novo valor atual (R$)", min_value=0.0,
                            value=float(inv["valor_atual"]),
                            step=10.0, format="%.2f",
                            key=f"val_{inv['id']}",
                        )
                        data_upd = st.date_input("Data", value=datetime.date.today(), key=f"dt_{inv['id']}")
                        col_a, col_b, col_c = st.columns(3)
                        if col_a.button("Atualizar", key=f"upd_{inv['id']}", type="primary"):
                            atualizar_valor_investimento(int(inv["id"]), novo_val, str(data_upd))
                            st.success("Atualizado!")
                            st.rerun()
                        if col_b.button("Resgatar", key=f"res_{inv['id']}"):
                            resgatar_investimento(int(inv["id"]), novo_val, str(data_upd))
                            st.success("Marcado como resgatado.")
                            st.rerun()
                        if col_c.button("Excluir", key=f"del_{inv['id']}"):
                            excluir_investimento(int(inv["id"]))
                            st.rerun()

                # histórico de valores
                hist = historico_investimento(int(inv["id"]))
                if len(hist) > 1:
                    fig_hist = px.line(
                        hist, x="data", y="valor",
                        labels={"data": "", "valor": "R$"},
                        markers=True,
                        color_discrete_sequence=[cor],
                    )
                    fig_hist.update_layout(height=150, margin=dict(t=5, b=5, l=5, r=5))
                    st.plotly_chart(fig_hist, use_container_width=True)

# ── Novo Investimento ─────────────────────────────────────────────────────────
with tab_novo:
    with st.form("novo_inv", clear_on_submit=True):
        col1, col2 = st.columns(2)
        nome = col1.text_input("Nome do investimento *", placeholder="Ex: CDB Nubank 12 meses")
        tipo = col2.selectbox("Tipo *", TIPOS)

        col3, col4 = st.columns(2)
        instituicao = col3.text_input("Instituição", placeholder="Ex: Nubank, XP, Rico...")
        data_aplic = col4.date_input("Data da aplicação *", value=datetime.date.today())

        col5, col6, col7 = st.columns(3)
        valor_inv = col5.number_input("Valor investido (R$) *", min_value=0.01, step=100.0, format="%.2f")
        valor_atu = col6.number_input("Valor atual (R$)", min_value=0.0, step=100.0, format="%.2f",
                                      help="Deixe igual ao investido se acabou de aplicar.")
        rent_esp = col7.number_input("Rentabilidade esperada (% a.a.)", min_value=0.0, step=0.1, format="%.2f")

        col8, col9 = st.columns(2)
        data_venc = col8.date_input("Data de vencimento (opcional)", value=None)
        observacao = col9.text_input("Observação (opcional)")

        if st.form_submit_button("💾 Cadastrar investimento", type="primary"):
            if not nome.strip():
                st.error("Informe o nome.")
            elif valor_inv <= 0:
                st.error("Informe o valor investido.")
            else:
                criar_investimento({
                    "nome": nome.strip(),
                    "tipo": tipo,
                    "instituicao": instituicao.strip() or None,
                    "valor_investido": valor_inv,
                    "valor_atual": valor_atu if valor_atu > 0 else valor_inv,
                    "data_aplicacao": str(data_aplic),
                    "data_vencimento": str(data_venc) if data_venc else None,
                    "rentabilidade_esperada": rent_esp or None,
                    "observacao": observacao.strip() or None,
                })
                st.success(f"Investimento '{nome}' cadastrado!")
                st.rerun()

# ── Resgatados ────────────────────────────────────────────────────────────────
with tab_resgatados:
    df_res = df_todos[df_todos["ativo"] == 0] if not df_todos.empty else pd.DataFrame()
    if df_res.empty:
        st.info("Nenhum investimento resgatado ainda.")
    else:
        show = df_res[["nome", "tipo", "instituicao", "valor_investido", "valor_atual", "rendimento", "rentabilidade_real", "data_aplicacao"]].copy()
        show["valor_investido"] = show["valor_investido"].apply(fmt)
        show["valor_atual"] = show["valor_atual"].apply(fmt)
        show["rendimento"] = show["rendimento"].apply(fmt)
        show["rentabilidade_real"] = show["rentabilidade_real"].apply(fmt_pct)
        show.columns = ["Nome", "Tipo", "Instituição", "Investido", "Resgate", "Rendimento", "Rentab. Real", "Data Aplicação"]
        st.dataframe(show, use_container_width=True, hide_index=True)
