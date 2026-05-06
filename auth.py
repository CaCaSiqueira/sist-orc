import streamlit as st


def require_login() -> str:
    """Exige login. Retorna user_id (email) ou para a execução."""
    if not st.user.is_logged_in:
        _show_login_page()
        st.stop()

    uid = st.user.email

    # Inicializa categorias padrão só na primeira visita da sessão
    if not st.session_state.get("_user_initialized"):
        from db.database import init_user
        init_user(uid)
        st.session_state["_user_initialized"] = True

    return uid


def sidebar_user():
    """Exibe nome do usuário e botão de logout na sidebar."""
    with st.sidebar:
        st.divider()
        nome = st.user.name or st.user.email
        st.caption(f"👤 {nome}")
        st.button("🚪 Sair", on_click=st.logout, use_container_width=True, key="_logout_btn")


def _show_login_page():
    st.set_page_config(page_title="Login — Orçamento Pessoal", page_icon="💰", layout="centered")
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 💰 Orçamento Pessoal")
        st.markdown("Controle suas finanças de forma simples e segura.")
        st.markdown("---")
        st.markdown("### Faça login para continuar")
        st.button(
            "🔐 Entrar com Google",
            on_click=st.login,
            type="primary",
            use_container_width=True,
        )
