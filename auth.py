import streamlit as st


def require_login() -> str:
    """Exige login. Retorna user_id (inteiro como string) ou para a execução."""
    if not st.session_state.get("_user_id"):
        _show_login_page()
        st.stop()

    uid = st.session_state["_user_id"]

    if not st.session_state.get("_user_initialized"):
        from db.database import init_user
        init_user(uid)
        st.session_state["_user_initialized"] = True

    return uid


def sidebar_user():
    """Exibe nome do usuário e botão de logout na sidebar."""
    nome = st.session_state.get("_user_nome", "")
    with st.sidebar:
        st.divider()
        st.caption(f"👤 {nome}")
        if st.button("🚪 Sair", use_container_width=True):
            for k in ("_user_id", "_user_nome", "_user_initialized"):
                st.session_state.pop(k, None)
            st.rerun()


def _set_session(uid: str, nome: str):
    st.session_state["_user_id"] = uid
    st.session_state["_user_nome"] = nome
    st.session_state.pop("_user_initialized", None)


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
            from db.queries import autenticar, get_usuario, criar_usuario

            usuario = get_usuario(email)

            if usuario:
                # Usuário já existe no banco — verifica senha
                result = autenticar(email, senha)
                if result:
                    _set_session(*result)
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                # Usuário não existe no banco — tenta migrar de st.secrets
                migrado = _migrar_de_secrets(email, senha)
                if migrado:
                    result = autenticar(email, senha)
                    if result:
                        _set_session(*result)
                        st.rerun()
                else:
                    st.error("E-mail ou senha incorretos.")


def _migrar_de_secrets(email: str, senha: str) -> bool:
    """Se o e-mail/senha estiver em st.secrets, cria o usuário no banco (migração única)."""
    try:
        users = dict(st.secrets.get("users", {}))
        if email in users and users[email] == senha:
            from db.queries import criar_usuario
            nome = email.split("@")[0].replace(".", " ").title()
            criar_usuario(email, nome, senha)
            return True
    except Exception:
        pass
    return False
