"""
ui_questionnaires.py
--------------------
- Formulaire de remplissage joueur (appelé depuis la page Séance côté joueur).
- Vue staff des résultats consolidés (utilisée depuis l'onglet Questionnaire
  de chaque séance, via render_questionnaire_results).
"""

import streamlit as st
import pandas as pd

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
# VUE STAFF — Résultats consolidés (affiché dans l'onglet Questionnaire)
# =============================================================================

def render_questionnaire_results(quest: dict) -> None:
    """Affiche le tableau + pivots d'un questionnaire donné."""
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
# VUE JOUEUR — Formulaire de remplissage
# =============================================================================

def render_player_fill_questionnaire(
    quest: dict,
    player_id: int,
    show_title: bool = True,
) -> None:
    """Formulaire slider 0-100 aveugle. Appelable depuis la page Séance joueur."""
    if show_title:
        st.markdown(f"### {quest['title']}")

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

        if st.form_submit_button("Envoyer mes réponses", use_container_width=True):
            db.save_responses(player_id, answers)
            st.success("Merci, tes réponses ont été enregistrées ✅")
            st.balloons()
