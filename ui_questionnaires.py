"""
ui_questionnaires.py
--------------------
Interfaces Streamlit pour la partie "Questionnaires post-séance".
"""

import time

import pandas as pd
import streamlit as st

import database as db


HIDE_SLIDER_VALUE_CSS = """
<style>
div[data-testid="stSlider"] [data-testid="stThumbValue"] {
    color: transparent !important;
    text-shadow: none !important;
    background: transparent !important;
    box-shadow: none !important;
}
div[data-testid="stSlider"] [data-testid="stSliderTickBarMin"],
div[data-testid="stSlider"] [data-testid="stSliderTickBarMax"] {
    visibility: hidden;
}
</style>
"""


# =============================================================================
# VUE STAFF
# =============================================================================

def render_staff_questionnaires() -> None:
    st.header("📝 Questionnaires (staff)")

    tab_create, tab_results = st.tabs(["Créer un questionnaire", "📊 Résultats"])

    with tab_create:
        _staff_create_questionnaire()

    with tab_results:
        _staff_view_results()


def _staff_create_questionnaire() -> None:
    sessions = db.list_sessions()
    if not sessions:
        st.info("Crée d'abord une séance pour pouvoir lui associer un questionnaire.")
        return

    sessions_libres = [
        s for s in sessions if db.get_questionnaire_by_session(s["id"]) is None
    ]
    if not sessions_libres:
        st.info("Toutes les séances ont déjà un questionnaire.")
        return

    options = {
        f"{s['date']} {s['time']} — {s['title']}": s["id"]
        for s in sessions_libres
    }
    choix = st.selectbox("Séance associée", list(options.keys()))
    session_id = options[choix]

    with st.form("create_quest", clear_on_submit=True):
        title = st.text_input(
            "Titre du questionnaire",
            value="Ressenti après séance",
        )
        st.markdown(
            "Ajoute tes questions ci-dessous (une ligne par question). "
            "Les questions vides seront ignorées."
        )
        default_df = pd.DataFrame([
            {"Question": "Comment as-tu ressenti l'intensité de la séance ?"},
            {"Question": "Comment évalues-tu ta forme physique ?"},
            {"Question": "Niveau de plaisir sur cette séance ?"},
        ])
        df_questions = st.data_editor(
            default_df,
            num_rows="dynamic",
            use_container_width=True,
            key="questions_editor",
        )

        submitted = st.form_submit_button("Créer le questionnaire")

    if submitted:
        questions = [
            str(q).strip() for q in df_questions["Question"] if str(q).strip()
        ]
        if not questions:
            st.error("Ajoute au moins une question.")
            return
        db.create_questionnaire(
            session_id, title.strip() or "Questionnaire", questions
        )

        st.success("Questionnaire créé ✅")
        st.balloons()
        time.sleep(1.8)
        st.rerun()


def _staff_view_results() -> None:
    sessions = db.list_sessions()
    sessions_avec_quest = [
        s for s in sessions if db.get_questionnaire_by_session(s["id"]) is not None
    ]
    if not sessions_avec_quest:
        st.info("Aucun questionnaire créé pour le moment.")
        return

    options = {
        f"{s['date']} {s['time']} — {s['title']}": s["id"]
        for s in sessions_avec_quest
    }
    choix = st.selectbox("Séance à consulter", list(options.keys()))
    session_id = options[choix]
    quest = db.get_questionnaire_by_session(session_id)

    st.markdown(f"### {quest['title']}")
    responses = db.list_responses(quest["id"])
    if not responses:
        st.info("Aucune réponse enregistrée pour l'instant.")
        return

    df = pd.DataFrame([{
        "Joueur":   r["player_name"],
        "Question": r["question_text"],
        "Valeur (0-100)": r["value"],
    } for r in responses])

    st.markdown("**Réponses détaillées**")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("**Moyenne par question**")
    pivot = df.groupby("Question")["Valeur (0-100)"].agg(["mean", "count"]).round(1)
    pivot = pivot.rename(columns={"mean": "Moyenne", "count": "Nb réponses"})
    st.dataframe(pivot, use_container_width=True)

    st.markdown("**Vue par joueur**")
    pivot_players = df.pivot_table(
        index="Joueur", columns="Question", values="Valeur (0-100)", aggfunc="mean"
    )
    st.dataframe(pivot_players, use_container_width=True)


# =============================================================================
# VUE JOUEUR
# =============================================================================

def render_player_questionnaires() -> None:
    st.header("📝 Mes questionnaires")
    user = st.session_state["user"]

    sessions = db.list_sessions_for_player(user["id"])
    sessions_with_q = []
    for s in sessions:
        q = db.get_questionnaire_by_session(s["id"])
        if q is not None:
            sessions_with_q.append((s, q))

    if not sessions_with_q:
        st.info("Aucun questionnaire disponible pour tes séances.")
        return

    def label(s, q):
        deja = db.has_player_answered(q["id"], user["id"])
        flag = "✅ " if deja else "🟠 "
        return f"{flag}{s['date']} {s['time']} — {s['title']}"

    labels = [label(s, q) for s, q in sessions_with_q]
    idx = st.selectbox(
        "Choisis un questionnaire",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
    )
    session, quest = sessions_with_q[idx]

    _player_fill_questionnaire(session, quest, user["id"])


def _player_fill_questionnaire(session, quest, player_id: int) -> None:
    st.markdown(f"### {quest['title']}")
    st.caption(f"Séance : {session['title']} ({session['date']} {session['time']})")

    questions = db.list_questions(quest["id"])
    if not questions:
        st.info("Ce questionnaire ne contient pas encore de questions.")
        return

    if db.has_player_answered(quest["id"], player_id):
        st.info("Tu as déjà répondu — tu peux modifier tes réponses ci-dessous.")

    st.markdown(
        "Déplace le curseur : **à gauche = négatif**, **à droite = positif**. "
        "_Aucun chiffre n'est affiché pour ne pas biaiser ta réponse._"
    )

    st.markdown(HIDE_SLIDER_VALUE_CSS, unsafe_allow_html=True)

    with st.form(f"quest_form_{quest['id']}"):
        answers: dict[int, int] = {}

        for q in questions:
            st.markdown(f"**{q['text']}**")

            col_neg, col_slider, col_pos = st.columns([1, 10, 1])
            with col_neg:
                st.markdown(
                    "<div style='text-align:center; font-size:1.6em;'>👎</div>"
                    "<div style='text-align:center; font-size:0.8em; color:#888;'>Négatif</div>",
                    unsafe_allow_html=True,
                )
            with col_pos:
                st.markdown(
                    "<div style='text-align:center; font-size:1.6em;'>👍</div>"
                    "<div style='text-align:center; font-size:0.8em; color:#888;'>Positif</div>",
                    unsafe_allow_html=True,
                )
            with col_slider:
                value = st.slider(
                    "Ressenti",
                    min_value=0,
                    max_value=100,
                    value=50,
                    step=1,
                    key=f"q_{q['id']}",
                    label_visibility="collapsed",
                )
            answers[q["id"]] = int(value)
            st.markdown("")

        if st.form_submit_button("Envoyer mes réponses"):
            db.save_responses(player_id, answers)
            st.success("Merci, tes réponses ont été enregistrées ✅")
            st.balloons()
