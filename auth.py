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


def login_form() -> None:
    st.title("⚽ Connexion")
    st.markdown(
        "Bienvenue sur l'outil de gestion des séances et questionnaires du club. "
        "Connecte-toi avec les identifiants qui t'ont été transmis par le staff."
    )

    with st.form("login_form"):
        username = st.text_input("Nom d'utilisateur").strip().lower()
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

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
