"""
app.py
------
Point d'entrée Streamlit.

Côté staff  : onglets "Séances" et "Résultats questionnaires".
Côté joueur : onglet "Séances" uniquement — les questionnaires sont
              directement intégrés dans la page de la séance concernée.
              Le rendu visuel du menu latéral est identique à celui du staff.
"""

import streamlit as st

import database as db
import auth
from ui_sessions import render_staff_sessions, render_player_sessions
from ui_questionnaires import render_staff_results


st.set_page_config(
    page_title="Club — Séances & Questionnaires",
    page_icon="⚽",
    layout="wide",
)


# 1. Base de données (init + migrations automatiques)
db.init_db()

# 2. Synchronisation des utilisateurs depuis les secrets
try:
    users_from_secrets = st.secrets["users"]
    db.sync_users_from_secrets(
        {name: dict(data) for name, data in users_from_secrets.items()}
    )
except Exception:
    pass


def main() -> None:
    user = auth.current_user()

    if user is None:
        auth.login_form()
        return

    with st.sidebar:
        st.markdown(f"### 👋 {user['full_name']}")
        st.caption(f"Rôle : **{user['role']}**")
        st.markdown("---")

        if user["role"] == "staff":
            page = st.radio(
                "Navigation",
                ["📅 Séances", "📊 Résultats questionnaires"],
                label_visibility="collapsed",
            )
        else:
            # Même aspect visuel que pour le staff (st.radio),
            # mais le joueur n'a qu'une seule page : Séances.
            # Les questionnaires sont intégrés directement dans la page Séance.
            page = st.radio(
                "Navigation",
                ["📅 Séances"],
                label_visibility="collapsed",
            )

        st.markdown("---")
        if st.button("Se déconnecter"):
            auth.logout()

    if user["role"] == "staff":
        if page == "📅 Séances":
            render_staff_sessions()
        elif page == "📊 Résultats questionnaires":
            render_staff_results()
    else:
        # Vue joueur : une seule page, qui inclut déjà le questionnaire
        # de la séance sélectionnée.
        render_player_sessions()


if __name__ == "__main__":
    main()
