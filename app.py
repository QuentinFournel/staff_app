"""
app.py
------
Point d'entrée Streamlit.
Lance l'application avec :
    streamlit run app.py

Au démarrage :
1. Création des tables SQLite si besoin.
2. Synchronisation des utilisateurs depuis les secrets Streamlit.
   -> Ajoute / met à jour en base les comptes définis dans secrets.toml.
   -> Aucun utilisateur n'est créé depuis l'UI.
"""

import streamlit as st

import database as db
import auth
from ui_sessions import render_staff_sessions, render_player_sessions
from ui_questionnaires import render_staff_questionnaires, render_player_questionnaires


st.set_page_config(
    page_title="Club — Séances & Questionnaires",
    page_icon="https://upload.wikimedia.org/wikipedia/fr/7/72/AS_Cannes_foot_Logo_2017.svg",
    layout="wide",
)


# 1. Base de données
db.init_db()

# 2. Synchronisation des utilisateurs depuis les secrets
try:
    users_from_secrets = st.secrets["users"]
    db.sync_users_from_secrets(
        {name: dict(data) for name, data in users_from_secrets.items()}
    )
except Exception:
    # Pas de secrets disponibles -> on affichera un message explicite au login.
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
                ["📅 Séances", "📝 Questionnaires"],
                label_visibility="collapsed",
            )
        else:
            page = st.radio(
                "Navigation",
                ["📅 Mes séances", "📝 Mes questionnaires"],
                label_visibility="collapsed",
            )

        st.markdown("---")
        if st.button("Se déconnecter"):
            auth.logout()

    if user["role"] == "staff":
        if page == "📅 Séances":
            render_staff_sessions()
        elif page == "📝 Questionnaires":
            render_staff_questionnaires()
    else:
        if page == "📅 Mes séances":
            render_player_sessions()
        elif page == "📝 Mes questionnaires":
            render_player_questionnaires()


if __name__ == "__main__":
    main()
