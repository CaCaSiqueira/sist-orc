import streamlit as st


def require_login() -> str:
    """Exige login. Retorna user_id (inteiro como string) ou para a execução."""
    if not st.session_state.get("_db_ready"):
        from db.database import init_db
        init_db()
        st.session_state["_db_ready"] = True

    if not st.session_state.get("_user_id"):
        _show_login_page()
        st.stop()

    uid = st.session_state["_user_id"]

    if not st.session_state.get("_user_initialized"):
        from db.database import init_user
        init_user(uid)
        st.session_state["_user_initialized"] = True

    return uid


def is_admin(uid: str) -> bool:
    """Verifica se o usuário logado é administrador."""
    try:
        admin = st.secrets.get("admin_email", "")
        # uid é o integer id — compara pelo email armazenado na sessão
        email = st.session_state.get("_user_email", "")
        return bool(admin) and email.lower() == admin.lower()
    except Exception:
        return False


def sidebar_user():
    """Exibe logo, nome do usuário e botão de logout na sidebar."""
    nome = st.session_state.get("_user_nome", "")
    with st.sidebar:
        from pathlib import Path
        _logo = Path(__file__).parent / "assets" / "logo.svg"
        if _logo.exists():
            st.image(str(_logo), use_container_width=True)
        st.divider()
        st.caption(f"👤 {nome}")
        if st.button("🚪 Sair", use_container_width=True):
            for k in ("_user_id", "_user_nome", "_user_email", "_user_initialized"):
                st.session_state.pop(k, None)
            st.rerun()


def _set_session(uid: str, nome: str, email: str = ""):
    st.session_state["_user_id"] = uid
    st.session_state["_user_nome"] = nome
    st.session_state["_user_email"] = email
    st.session_state.pop("_user_initialized", None)


def _show_login_page():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 💰 Orçamento Pessoal")
        st.markdown("Controle suas finanças de forma simples e segura.")
        st.markdown("---")
        st.markdown("### 🔐 Login")

        email = st.text_input("E-mail", placeholder="seu@email.com")
        senha = st.text_input("Senha", type="password")

        if st.button("Entrar", type="primary", use_container_width=True):
            from db.queries import autenticar, get_usuario

            usuario = get_usuario(email)
            senha_configurada = usuario and usuario.get("senha_hash", "")

            if senha_configurada:
                # Usuário com senha — autentica normalmente
                result = autenticar(email, senha)
                if result:
                    uid, nome = result
                    _set_session(uid, nome, email.lower().strip())
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                # Sem hash (novo usuário ou hash vazio) — tenta migrar de st.secrets
                migrado = _migrar_de_secrets(email, senha, usuario)
                if migrado:
                    result = autenticar(email, senha)
                    if result:
                        uid, nome = result
                        _set_session(uid, nome, email.lower().strip())
                        st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos.")
                else:
                    st.error("E-mail ou senha incorretos.")


def _migrar_de_secrets(email: str, senha: str, usuario_existente: dict | None) -> bool:
    """Se o e-mail/senha estiver em st.secrets, grava o hash no banco (migração única)."""
    try:
        users = dict(st.secrets.get("users", {}))
        email_lower = email.lower().strip()
        senha_secrets = users.get(email_lower) or users.get(email.strip())
        if senha_secrets and senha_secrets == senha:
            from db.queries import criar_usuario, atualizar_senha
            if usuario_existente:
                # Usuário existe mas sem hash — grava a senha
                atualizar_senha(usuario_existente["id"], senha)
            else:
                # Usuário não existe — cria completo
                nome = email_lower.split("@")[0].replace(".", " ").title()
                criar_usuario(email_lower, nome, senha)
            return True
    except Exception:
        pass
    return False
