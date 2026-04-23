"""
auth.py
-------
Authentification simple basée sur st.secrets + la base locale.

Le fichier .streamlit/secrets.toml doit contenir une section [users]
sous la forme :

    [users.jdupont]
    full_name = "Jean Dupont"
    password  = "motdepasse"
    role      = "staff"          # ou "player"

La synchronisation dans SQLite est gérée par database.sync_users_from_secrets(),
appelée au démarrage dans app.py.
"""

from __future__ import annotations

import streamlit as st

import database as db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_from_secrets(username: str) -> dict | None:
    """Retourne le dict utilisateur depuis st.secrets (ou None)."""
    try:
        users = st.secrets["users"]
    except Exception:
        return None

    data = users.get(username)
    if data is None:
        return None
    return dict(data)


def _check_credentials(username: str, password: str) -> dict | None:
    """Vérifie le couple user/mot de passe et renvoie le user enrichi de son id DB."""
    data = _get_user_from_secrets(username)
    if data is None:
        return None
    if data.get("password") != password:
        return None

    row = db.get_user_by_username(username)
    if row is None:
        return None

    return {
        "id":        row["id"],
        "username":  username,
        "full_name": data.get("full_name", username),
        "role":      data.get("role", "player"),
    }


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def current_user() -> dict | None:
    """Retourne le user actuellement connecté (stocké dans session_state)."""
    return st.session_state.get("user")


def login_form() -> None:
    """Affiche un formulaire de login. Remplit st.session_state['user'] si OK."""
    st.title("🔐 Connexion")
    st.caption("Connecte-toi avec tes identifiants.")

    with st.form("login_form"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        user = _check_credentials(username.strip(), password)
        if user is None:
            st.error("Identifiant ou mot de passe incorrect.")
        else:
            st.session_state["user"] = user
            st.rerun()


def logout() -> None:
    """Déconnecte l'utilisateur courant."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
