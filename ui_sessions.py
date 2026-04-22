"""
ui_sessions.py
--------------
Interfaces Streamlit pour la partie "Séances".

NOUVELLE LOGIQUE : plus de menu déroulant de choix de séance.
On clique directement sur un événement dans le calendrier pour afficher
ses détails / sa gestion en dessous.

- Calendrier mensuel (streamlit-calendar) avec couleur selon J-relative.
- Clic sur un événement -> stocke l'id dans st.session_state et affiche
  le bloc de détails en dessous.
- Staff : création de séance dans un onglet séparé, puis gestion (édition,
  convocations, PDF, suppression) via le clic sur le calendrier.
- Joueur : consulte ses séances (convocations, détails, PDF) en cliquant sur
  l'événement dans son calendrier.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

import database as db


# ---------------------------------------------------------------------------
# Helpers visuels
# ---------------------------------------------------------------------------

COULEUR_J = {
    "J":    "#2E7D32",   # jour du match
    "J-1":  "#66BB6A",
    "J-2":  "#9CCC65",
    "J-3":  "#FFEB3B",
    "J-4":  "#FFA726",
    "J-5":  "#EF5350",
    "J+1":  "#42A5F5",
    "J+2":  "#5C6BC0",
    "Autre":"#90A4AE",
}


CALENDAR_OPTIONS = {
    "initialView": "dayGridMonth",
    "locale": "fr",
    "firstDay": 1,
    "headerToolbar": {
        "left":   "prev,next today",
        "center": "title",
        "right":  "dayGridMonth,timeGridWeek,listWeek",
    },
    "buttonText": {
        "today": "Aujourd'hui",
        "month": "Mois",
        "week":  "Semaine",
        "list":  "Liste",
    },
    "height": 650,
    "navLinks": True,
    "editable": False,
    "selectable": False,
    "eventDisplay": "block",
}


CALENDAR_CSS = """
.fc-event { cursor: pointer !important; }
.fc-event:hover { opacity: 0.85; }
"""


def _session_to_event(s: dict) -> dict:
    color = COULEUR_J.get(s.get("j_relative") or "Autre", COULEUR_J["Autre"])
    start = f"{s['date']}T{s['time']}"
    label = s["title"]
    if s.get("j_relative"):
        label = f"[{s['j_relative']}] {label}"
    return {
        "id": str(s["id"]),
        "title": label,
        "start": start,
        "backgroundColor": color,
        "borderColor":     color,
    }


def _handle_calendar_click(cal_result, state_key: str) -> None:
    """
    Si le dernier callback est un clic sur un event, mémorise son id dans
    st.session_state[state_key] et rerun.
    """
    if not cal_result:
        return
    cb = cal_result.get("callback")
    if cb == "eventClick":
        event = cal_result.get("eventClick", {}).get("event", {})
        event_id = event.get("id")
        if event_id is not None:
            try:
                sid = int(event_id)
            except (TypeError, ValueError):
                return
            if st.session_state.get(state_key) != sid:
                st.session_state[state_key] = sid
                st.rerun()


# ===========================================================================
# VUE STAFF
# ===========================================================================

def render_staff_sessions() -> None:
    st.header("📅 Séances (staff)")

    tab_cal, tab_new = st.tabs(["Calendrier", "➕ Créer une séance"])

    with tab_new:
        _staff_create_session()

    with tab_cal:
        _staff_calendar_and_details()


# ---------------------------------------------------------------------------
# Création d'une séance
# ---------------------------------------------------------------------------

def _staff_create_session() -> None:
    user = st.session_state["user"]

    with st.form("create_session", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Titre", placeholder="Séance tactique")
            date_val = st.date_input("Date", value=date.today())
            j_rel = st.selectbox(
                "Jour relatif au match",
                list(COULEUR_J.keys()),
                index=list(COULEUR_J.keys()).index("J-1"),
            )
        with col2:
            time_val = st.time_input("Heure", value=datetime.now().time().replace(second=0, microsecond=0))
            description = st.text_area("Description", height=104)

        st.markdown("**Procédés** (optionnel)")
        default_df = pd.DataFrame(
            [
                {"Procédé": "Échauffement", "Durée (min)": 15},
                {"Procédé": "Possession 4v4+3", "Durée (min)": 20},
                {"Procédé": "Match à thème", "Durée (min)": 25},
            ]
        )
        df_proc = st.data_editor(
            default_df,
            num_rows="dynamic",
            use_container_width=True,
            key="procedes_editor_create",
        )

        st.markdown("**Convocations**")
        players = db.list_players()
        player_labels = {f"{p['full_name']} ({p['username']})": p["id"] for p in players}
        selected_labels = st.multiselect(
            "Joueurs convoqués",
            list(player_labels.keys()),
            default=list(player_labels.keys()),
        )

        submitted = st.form_submit_button("Créer la séance")

    if not submitted:
        return

    if not title.strip():
        st.error("Le titre est obligatoire.")
        return

    procedes = [
        (str(row["Procédé"]).strip(), int(row["Durée (min)"] or 0))
        for _, row in df_proc.iterrows()
        if str(row.get("Procédé", "")).strip()
    ]
    session_id = db.create_session(
        title=title.strip(),
        description=description.strip(),
        j_relative=j_rel,
        date=date_val.isoformat(),
        time=time_val.strftime("%H:%M"),
        created_by=user["id"],
        procedes=procedes,
    )
    db.convoquer_joueurs(session_id, [player_labels[l] for l in selected_labels])

    st.success(f"Séance « {title} » créée ✅")
    st.balloons()
    time.sleep(1.8)
    # Pré-sélectionne la nouvelle séance dans le calendrier
    st.session_state["staff_selected_session"] = session_id
    st.rerun()


# ---------------------------------------------------------------------------
# Calendrier + bloc de détails (zone unique, pilotée par le clic)
# ---------------------------------------------------------------------------

def _staff_calendar_and_details() -> None:
    sessions = db.list_sessions()

    if not sessions:
        st.info("Aucune séance pour le moment. Crée-en une via l'onglet « ➕ Créer une séance ».")
        # On efface une éventuelle sélection persistée.
        st.session_state.pop("staff_selected_session", None)
        return

    events = [_session_to_event(s) for s in sessions]

    st.caption(
        "Clique sur une séance dans le calendrier pour afficher et gérer ses détails en dessous."
    )

    cal_result = calendar(
        events=events,
        options=CALENDAR_OPTIONS,
        custom_css=CALENDAR_CSS,
        key="cal_staff",
    )
    _handle_calendar_click(cal_result, "staff_selected_session")

    selected_id = st.session_state.get("staff_selected_session")
    if selected_id is None:
        st.info("👉 Sélectionne une séance dans le calendrier pour voir ses détails.")
        _legend()
        return

    session = db.get_session(selected_id)
    if session is None:
        # La séance a été supprimée -> on nettoie.
        st.session_state.pop("staff_selected_session", None)
        st.rerun()
        return

    st.markdown("---")
    header_cols = st.columns([6, 1])
    with header_cols[0]:
        st.subheader(f"🗂️ {session['title']} — {session['date']} {session['time']}")
    with header_cols[1]:
        if st.button("✖ Fermer", key="close_details", use_container_width=True):
            st.session_state.pop("staff_selected_session", None)
            st.rerun()

    _staff_session_editor(session)
    _legend()


def _legend() -> None:
    with st.expander("🎨 Légende des couleurs par jour relatif"):
        parts = [
            f"<span style='background:{color};padding:2px 8px;border-radius:4px;color:white;margin-right:6px;'>{key}</span>"
            for key, color in COULEUR_J.items()
        ]
        st.markdown(" ".join(parts), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Bloc détail / gestion d'UNE séance (staff)
# ---------------------------------------------------------------------------

def _staff_session_editor(session: dict) -> None:
    session_id = session["id"]

    tab_info, tab_conv, tab_pdf, tab_danger = st.tabs(
        ["✏️ Infos & procédés", "👥 Convocations", "📎 PDF", "🗑️ Supprimer"]
    )

    # --- Infos & procédés -----------------------------------------------------
    with tab_info:
        with st.form(f"edit_session_{session_id}"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Titre", value=session["title"])
                date_val = st.date_input(
                    "Date", value=datetime.fromisoformat(session["date"]).date()
                )
                j_keys = list(COULEUR_J.keys())
                cur_j = session.get("j_relative") or "Autre"
                j_rel = st.selectbox(
                    "Jour relatif",
                    j_keys,
                    index=j_keys.index(cur_j) if cur_j in j_keys else j_keys.index("Autre"),
                )
            with col2:
                t_obj = datetime.strptime(session["time"], "%H:%M").time()
                time_val = st.time_input("Heure", value=t_obj)
                description = st.text_area(
                    "Description", value=session.get("description") or "", height=104
                )

            procedes_cur = db.list_procedes(session_id)
            df_proc = pd.DataFrame(
                [{"Procédé": p["label"], "Durée (min)": p["duration"]} for p in procedes_cur]
                or [{"Procédé": "", "Durée (min)": 0}]
            )
            df_edit = st.data_editor(
                df_proc,
                num_rows="dynamic",
                use_container_width=True,
                key=f"procedes_editor_edit_{session_id}",
            )

            if st.form_submit_button("Enregistrer les modifications"):
                procedes = [
                    (str(row["Procédé"]).strip(), int(row["Durée (min)"] or 0))
                    for _, row in df_edit.iterrows()
                    if str(row.get("Procédé", "")).strip()
                ]
                db.update_session(
                    session_id=session_id,
                    title=title.strip() or session["title"],
                    description=description.strip(),
                    j_relative=j_rel,
                    date=date_val.isoformat(),
                    time=time_val.strftime("%H:%M"),
                    procedes=procedes,
                )
                st.success("Séance mise à jour ✅")
                time.sleep(0.8)
                st.rerun()

    # --- Convocations ---------------------------------------------------------
    with tab_conv:
        players = db.list_players()
        current_convs = db.list_convocations(session_id)
        current_ids = {c["player_id"] for c in current_convs}

        st.markdown("**Liste des joueurs convoqués**")
        player_labels = {f"{p['full_name']} ({p['username']})": p["id"] for p in players}
        default_labels = [l for l, pid in player_labels.items() if pid in current_ids]

        with st.form(f"conv_form_{session_id}"):
            new_selection = st.multiselect(
                "Joueurs convoqués",
                list(player_labels.keys()),
                default=default_labels,
            )
            if st.form_submit_button("Mettre à jour les convocations"):
                db.convoquer_joueurs(session_id, [player_labels[l] for l in new_selection])
                st.success("Convocations mises à jour ✅")
                time.sleep(0.6)
                st.rerun()

        st.markdown("**Statuts**")
        convs = db.list_convocations(session_id)
        if not convs:
            st.info("Aucun joueur convoqué.")
        else:
            status_options = ["convoque", "present", "absent", "malade", "adapte"]
            for c in convs:
                cols = st.columns([4, 3])
                with cols[0]:
                    st.markdown(f"**{c['full_name']}** _({c['username']})_")
                with cols[1]:
                    new_status = st.selectbox(
                        "Statut",
                        status_options,
                        index=status_options.index(c["status"]),
                        key=f"status_{c['id']}",
                        label_visibility="collapsed",
                    )
                    if new_status != c["status"]:
                        db.update_convocation_status(c["id"], new_status)
                        st.rerun()

    # --- PDF ------------------------------------------------------------------
    with tab_pdf:
        pdfs = db.list_pdfs(session_id)
        if pdfs:
            st.markdown("**Documents joints :**")
            for p in pdfs:
                cols = st.columns([5, 1])
                with cols[0]:
                    try:
                        with open(p["path"], "rb") as f:
                            st.download_button(
                                label=f"📄 {p['filename']}",
                                data=f.read(),
                                file_name=p["filename"],
                                mime="application/pdf",
                                key=f"dl_{p['id']}",
                                use_container_width=True,
                            )
                    except FileNotFoundError:
                        st.warning(f"Fichier manquant : {p['filename']}")
                with cols[1]:
                    if st.button("🗑️", key=f"del_pdf_{p['id']}", use_container_width=True):
                        db.delete_pdf(p["id"])
                        st.rerun()
        else:
            st.caption("Aucun PDF pour le moment.")

        # Upload dans un form pour éviter la boucle d'ajout automatique
        with st.form(f"pdf_form_{session_id}", clear_on_submit=True):
            new_pdf = st.file_uploader("Joindre un PDF", type=["pdf"])
            submitted_pdf = st.form_submit_button("Ajouter le PDF")
            if submitted_pdf:
                if new_pdf is not None:
                    db.add_pdf(session_id, new_pdf.name, new_pdf.read())
                    st.success("PDF ajouté ✅")
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.warning("Sélectionne un PDF avant de cliquer.")

    # --- Supprimer ------------------------------------------------------------
    with tab_danger:
        st.warning(
            "La suppression est définitive : convocations, PDF et questionnaire "
            "associés seront également supprimés."
        )
        confirm = st.checkbox("Je confirme vouloir supprimer cette séance", key=f"confirm_del_{session_id}")
        if st.button("Supprimer la séance", type="primary", disabled=not confirm, key=f"btn_del_{session_id}"):
            db.delete_session(session_id)
            st.session_state.pop("staff_selected_session", None)
            st.success("Séance supprimée.")
            time.sleep(0.6)
            st.rerun()


# ===========================================================================
# VUE JOUEUR
# ===========================================================================

def render_player_sessions() -> None:
    st.header("📅 Mes séances")
    user = st.session_state["user"]

    sessions = db.list_sessions_for_player(user["id"])
    if not sessions:
        st.info("Aucune convocation pour le moment.")
        st.session_state.pop("player_selected_session", None)
        return

    events = [_session_to_event(s) for s in sessions]

    st.caption("Clique sur une séance pour afficher ses détails.")

    cal_result = calendar(
        events=events,
        options=CALENDAR_OPTIONS,
        custom_css=CALENDAR_CSS,
        key="cal_player",
    )
    _handle_calendar_click(cal_result, "player_selected_session")

    selected_id = st.session_state.get("player_selected_session")
    if selected_id is None:
        st.info("👉 Sélectionne une séance dans le calendrier pour voir les détails.")
        _legend()
        return

    # Vérifie que le joueur est bien convoqué à cette séance
    if not db.is_player_convoque(selected_id, user["id"]):
        st.session_state.pop("player_selected_session", None)
        st.rerun()
        return

    session = db.get_session(selected_id)
    if session is None:
        st.session_state.pop("player_selected_session", None)
        st.rerun()
        return

    st.markdown("---")
    header_cols = st.columns([6, 1])
    with header_cols[0]:
        j = session.get("j_relative") or ""
        flag = f"[{j}] " if j else ""
        st.subheader(f"🗂️ {flag}{session['title']}")
        st.caption(f"{session['date']} à {session['time']}")
    with header_cols[1]:
        if st.button("✖ Fermer", key="close_player_details", use_container_width=True):
            st.session_state.pop("player_selected_session", None)
            st.rerun()

    if session.get("description"):
        st.markdown(session["description"])

    procedes = db.list_procedes(session["id"])
    if procedes:
        st.markdown("**Procédés :**")
        df = pd.DataFrame(
            [{"Procédé": p["label"], "Durée (min)": p["duration"]} for p in procedes]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

    pdfs = db.list_pdfs(session["id"])
    if pdfs:
        st.markdown("**Documents :**")
        for p in pdfs:
            try:
                with open(p["path"], "rb") as f:
                    st.download_button(
                        label=f"📄 {p['filename']}",
                        data=f.read(),
                        file_name=p["filename"],
                        mime="application/pdf",
                        key=f"player_dl_{p['id']}",
                    )
            except FileNotFoundError:
                st.warning(f"Fichier manquant : {p['filename']}")

    _legend()
