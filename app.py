"""
app.py
------
Point d'entrée Streamlit.

Sidebar : logo club, carte utilisateur, nav (côté joueur uniquement — côté
staff tout tient sur la page Séances, le questionnaire vit dans l'onglet
de la séance).
"""

import streamlit as st

import database as db
import auth
from ui_sessions import render_staff_sessions, render_player_sessions
from ui_questionnaires import render_player_questionnaires


AS_CANNES_LOGO_URL = (
    "https://upload.wikimedia.org/wikipedia/fr/7/72/AS_Cannes_foot_Logo_2017.svg"
)


st.set_page_config(
    page_title="AS Cannes — Séances & Questionnaires",
    page_icon=AS_CANNES_LOGO_URL,
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


SIDEBAR_CSS = """
<style>
.sb-logo-wrap {
    display: flex;
    justify-content: center;
    margin: 6px 0 12px 0;
}
.sb-logo-wrap img {
    max-width: 130px;
    height: auto;
}
.sb-club {
    text-align: center;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: 0.5px;
    margin: 0;
}
.sb-club-sub {
    text-align: center;
    font-size: 0.78rem;
    color: rgba(120, 120, 120, 0.9);
    margin: 2px 0 10px 0;
}
.sb-user {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(125, 125, 125, 0.08);
    margin-bottom: 6px;
}
.sb-user-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1f4fa3, #e8132c);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.95rem;
    flex-shrink: 0;
}
.sb-user-meta { line-height: 1.15; min-width: 0; }
.sb-user-name {
    font-weight: 600;
    font-size: 0.92rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.sb-user-role {
    font-size: 0.72rem;
    color: rgba(120, 120, 120, 0.9);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
</style>
"""


def _render_sidebar(user: dict) -> str | None:
    """Sidebar : logo + carte user + nav (joueur) + logout. Retourne la page choisie."""
    with st.sidebar:
        st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

        # Logo + bandeau club
        st.markdown(
            f'<div class="sb-logo-wrap">'
            f'<img src="{AS_CANNES_LOGO_URL}" alt="AS Cannes"/>'
            f'</div>'
            f'<div class="sb-club">AS CANNES</div>'
            f'<div class="sb-club-sub">Séances & Questionnaires</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # Carte utilisateur
        initial = (user["full_name"] or user["username"] or "?")[:1].upper()
        st.markdown(
            f'<div class="sb-user">'
            f'  <div class="sb-user-avatar">{initial}</div>'
            f'  <div class="sb-user-meta">'
            f'    <div class="sb-user-name">{user["full_name"]}</div>'
            f'    <div class="sb-user-role">{user["role"]}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        page = None
        if user["role"] == "joueur":
            st.markdown("")
            page = st.radio(
                "Navigation",
                ["📅 Mes séances", "📝 Mes questionnaires"],
                label_visibility="collapsed",
            )

        st.markdown("---")
        if st.button("Se déconnecter", use_container_width=True):
            auth.logout()

    return page


def main() -> None:
    user = auth.current_user()

    if user is None:
        auth.login_form(logo_url=AS_CANNES_LOGO_URL)
        return

    page = _render_sidebar(user)

    if user["role"] == "staff":
        render_staff_sessions()
    else:
        if page == "📅 Mes séances":
            render_player_sessions()
        elif page == "📝 Mes questionnaires":
            render_player_questionnaires()


if __name__ == "__main__":
    main()
