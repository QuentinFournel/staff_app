"""
auth.py
-------
Authentification via les secrets Streamlit.
"""

import streamlit as st

import database as db


def _load_users_from_secrets() -> dict:
    try:
        users = st.secrets["users"]
    except Exception:
        return {}
    return {name: dict(data) for name, data in users.items()}


LOGIN_CSS = """
<style>
.login-logo {
    text-align: center;
    margin: 8px 0 6px 0;
}
.login-logo img {
    max-width: 140px;
    height: auto;
}
.login-club {
    text-align: center;
    font-weight: 700;
    font-size: 1.4rem;
    letter-spacing: 1px;
    margin: 6px 0 0 0;
}
.login-sub {
    text-align: center;
    font-size: 0.9rem;
    color: rgba(120, 120, 120, 0.9);
    margin-bottom: 18px;
}
</style>
"""


def login_form(logo_url: str | None = None) -> None:
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    # Header centré dans une colonne étroite pour que le form fasse pro
    _, col, _ = st.columns([1, 2, 1])

    with col:
        if logo_url:
            st.markdown(
                f'<div class="login-logo"><img src="{logo_url}" alt="AS Cannes"/></div>',
                unsafe_allow_html=True,
            )
        st.markdown('<div class="login-club">AS CANNES</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-sub">Séances & Questionnaires</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            "Bienvenue sur l'outil de gestion des séances et questionnaires du club. "
            "Connecte-toi avec les identifiants transmis par le staff."
        )

        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur").strip().lower()
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter", use_container_width=True)

    if not submitted:
        return

    users = _load_users_from_secrets()
    if not users:
        st.error(
            "Configuration manquante : aucun utilisateur défini dans les secrets. "
            "Le staff doit renseigner les comptes dans `.streamlit/secrets.toml` "
            "(ou dans l'interface Secrets de Streamlit Cloud)."
        )
        return

    if username not in users or users[username].get("password") != password:
        st.error("Identifiants invalides.")
        return

    udata = users[username]
    row = db.get_user_by_username(username)
    if row is None:
        user_id = db.upsert_user(
            username=username,
            role=udata.get("role", "joueur"),
            full_name=udata.get("full_name", username),
        )
    else:
        user_id = row["id"]

    st.session_state["user"] = {
        "id": user_id,
        "username": username,
        "role": udata.get("role", "joueur"),
        "full_name": udata.get("full_name", username),
    }
    st.rerun()


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")
