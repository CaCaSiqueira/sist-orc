import streamlit as st


def require_login() -> str:
    """Exige login. Retorna user_id (email) ou para a execução."""
    if not st.session_state.get("_logged_user"):
        _show_login_page()
        st.stop()

    uid = st.session_state["_logged_user"]

    # Inicializa categorias padrão só na primeira visita da sessão
    if not st.session_state.get("_user_initialized"):
        from db.database import init_user
        init_user(uid)
        st.session_state["_user_initialized"] = True

    return uid


def sidebar_user():
    """Exibe nome do usuário e botão de logout na sidebar."""
    uid = st.session_state.get("_logged_user", "")
    with st.sidebar:
        st.divider()
        st.caption(f"👤 {uid}")
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.pop("_logged_user", None)
            st.session_state.pop("_user_initialized", None)
            st.rerun()


def _show_login_page():
    st.markdown(
        """
        <style>
        .login-box {
            max-width: 420px;
            margin: 80px auto;
            padding: 2rem;
            border-radius: 12px;
            background: #1e1e2e;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 💰 Orçamento Pessoal")
        st.markdown("Controle suas finanças de forma simples e segura.")
        st.markdown("---")
        st.markdown("### 🔐 Faça login para continuar")

        email = st.text_input("E-mail", placeholder="seu@email.com")
        senha = st.text_input("Senha", type="password")

        if st.button("Entrar", type="primary", use_container_width=True):
            users = _get_users()
            if email in users and users[email] == senha:
                st.session_state["_logged_user"] = email
                st.session_state.pop("_user_initialized", None)
                st.rerun()
            else:
                st.error("E-mail ou senha incorretos.")


def _get_users() -> dict:
    """Retorna dicionário {email: senha} dos usuários cadastrados."""
    try:
        users = st.secrets.get("users", {})
        return dict(users)
    except Exception:
        return {}
