"""
ui_sessions.py
--------------
Interfaces Streamlit pour la partie "Calendrier / Gestion des séances".

- Calendrier mensuel interactif (streamlit-calendar).
- Ballons animés à la création d'une séance.
"""

import time
from datetime import date as date_type, time as time_type
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

import database as db


STATUTS = ["convoque", "present", "absent", "malade", "adapte"]
STATUT_EMOJI = {
    "convoque": "📩 Convoqué",
    "present":  "✅ Présent",
    "absent":   "❌ Absent",
    "malade":   "🤒 Malade",
    "adapte":   "🔄 Adapté",
}

COULEUR_J = {
    "J-5": "#6c757d",
    "J-4": "#17a2b8",
    "J-3": "#007bff",
    "J-2": "#28a745",
    "J-1": "#fd7e14",
    "J":   "#dc3545",
    "J+1": "#6f42c1",
    "J+2": "#20c997",
}


def _sessions_to_events(sessions) -> list[dict]:
    events = []
    for s in sessions:
        start = f"{s['date']}T{s['time']}:00"
        try:
            h, m = map(int, s["time"].split(":"))
            end_h = (h * 60 + m + 90) // 60
            end_m = (h * 60 + m + 90) % 60
            end = f"{s['date']}T{end_h:02d}:{end_m:02d}:00"
        except Exception:
            end = start
        events.append({
            "id": str(s["id"]),
            "title": f"{s['day_relative'] or ''} · {s['title']}",
            "start": start,
            "end": end,
            "backgroundColor": COULEUR_J.get(s["day_relative"], "#1f77b4"),
            "borderColor":     COULEUR_J.get(s["day_relative"], "#1f77b4"),
        })
    return events


def _calendar_options() -> dict:
    return {
        "editable": False,
        "selectable": True,
        "initialView": "dayGridMonth",
        "locale": "fr",
        "firstDay": 1,
        "headerToolbar": {
            "left":   "prev,next today",
            "center": "title",
            "right":  "dayGridMonth,timeGridWeek,listWeek",
        },
        "buttonText": {
            "today":  "Aujourd'hui",
            "month":  "Mois",
            "week":   "Semaine",
            "list":   "Liste",
        },
        "height": 650,
    }


def _get_selected_id_from_calendar_state(state) -> int | None:
    if not state:
        return None
    ev = state.get("eventClick")
    if ev and isinstance(ev, dict):
        event = ev.get("event") or {}
        if event.get("id"):
            try:
                return int(event["id"])
            except ValueError:
                return None
    return None


# =============================================================================
# VUE STAFF
# =============================================================================

def render_staff_sessions() -> None:
    st.header("📅 Calendrier des séances (staff)")

    tab_calendar, tab_create = st.tabs(["Calendrier", "➕ Créer une séance"])

    with tab_calendar:
        _staff_calendar_view()

    with tab_create:
        _staff_create_session_form()


def _staff_calendar_view() -> None:
    sessions = db.list_sessions()
    if not sessions:
        st.info("Aucune séance enregistrée. Crée-en une via l'onglet ➕.")
        return

    events = _sessions_to_events(sessions)
    state = calendar(
        events=events,
        options=_calendar_options(),
        key="staff_calendar",
    )
    selected_id = _get_selected_id_from_calendar_state(state)

    st.markdown("---")
    st.subheader("Détails et gestion d'une séance")
    options = {f"{s['date']} {s['time']} — {s['title']}": s["id"] for s in sessions}
    default_idx = 0
    if selected_id:
        for i, sid in enumerate(options.values()):
            if sid == selected_id:
                default_idx = i
                break
    choix = st.selectbox(
        "Choisir une séance",
        list(options.keys()),
        index=default_idx,
        key="staff_select_session",
    )
    _staff_session_detail(options[choix])


def _staff_session_detail(session_id: int) -> None:
    session = db.get_session(session_id)
    if not session:
        st.warning("Séance introuvable.")
        return

    st.markdown(f"### {session['title']}")
    st.caption(f"{session['date']} à {session['time']} — {session['day_relative'] or ''}")
    if session["description"]:
        st.write(session["description"])

    procedes = db.list_procedes(session_id)
    if procedes:
        st.markdown("**Procédés / contenus**")
        df_proc = pd.DataFrame([{
            "Ordre": p["ordre"],
            "Contenu": p["name"],
            "Durée (min)": p["duration"],
        } for p in procedes])
        st.table(df_proc)
    else:
        st.info("Aucun procédé enregistré pour cette séance.")

    with st.expander("➕ Ajouter un procédé"):
        with st.form(f"add_proc_{session_id}"):
            c1, c2, c3 = st.columns([3, 1, 1])
            name = c1.text_input("Nom du procédé")
            duration = c2.number_input("Durée (min)", min_value=1, value=15, step=1)
            ordre = c3.number_input("Ordre", min_value=0, value=0, step=1)
            if st.form_submit_button("Ajouter"):
                if name.strip():
                    db.add_procede(session_id, name.strip(), int(duration), int(ordre))
                    st.success("Procédé ajouté.")
                    st.rerun()
                else:
                    st.warning("Le nom est obligatoire.")

    st.markdown("**Documents PDF**")
    pdfs = db.list_pdfs(session_id)
    for pdf in pdfs:
        fp = Path(pdf["filepath"])
        if fp.exists():
            with open(fp, "rb") as f:
                st.download_button(
                    f"📄 {pdf['filename']}",
                    data=f.read(),
                    file_name=pdf["filename"],
                    mime="application/pdf",
                    key=f"pdf_{pdf['id']}",
                )
    uploaded = st.file_uploader(
        "Joindre un PDF", type=["pdf"], key=f"upload_{session_id}"
    )
    if uploaded is not None:
        db.add_pdf(session_id, uploaded.name, uploaded.read())
        st.success("PDF ajouté.")
        st.rerun()

    st.markdown("**Convocations**")
    _staff_convocations_block(session_id)

    with st.expander("⚠️ Supprimer la séance"):
        if st.button("Supprimer définitivement", key=f"del_{session_id}"):
            db.delete_session(session_id)
            st.success("Séance supprimée.")
            st.rerun()


def _staff_convocations_block(session_id: int) -> None:
    joueurs = db.list_players()
    convocations = db.list_convocations(session_id)
    deja_convoques = {c["player_id"] for c in convocations}

    candidats = [j for j in joueurs if j["id"] not in deja_convoques]
    if candidats:
        with st.form(f"convoc_form_{session_id}"):
            noms = st.multiselect(
                "Convoquer des joueurs",
                options=[j["full_name"] for j in candidats],
            )
            if st.form_submit_button("Convoquer"):
                ids = [j["id"] for j in candidats if j["full_name"] in noms]
                if ids:
                    db.convoquer_joueurs(session_id, ids)
                    st.success(f"{len(ids)} joueur(s) convoqué(s).")
                    st.rerun()

    if convocations:
        st.caption("Statut de chaque joueur convoqué :")
        for c in convocations:
            cols = st.columns([3, 2])
            cols[0].write(f"👤 {c['full_name']}")
            new_status = cols[1].selectbox(
                "Statut",
                options=STATUTS,
                index=STATUTS.index(c["status"]) if c["status"] in STATUTS else 0,
                format_func=lambda s: STATUT_EMOJI[s],
                key=f"status_{session_id}_{c['player_id']}",
                label_visibility="collapsed",
            )
            if new_status != c["status"]:
                db.update_status(session_id, c["player_id"], new_status)
                st.toast(f"Statut mis à jour pour {c['full_name']}", icon="✅")
    else:
        st.info("Aucun joueur convoqué pour cette séance.")


def _staff_create_session_form() -> None:
    user = st.session_state["user"]

    with st.form("create_session", clear_on_submit=True):
        c1, c2 = st.columns(2)
        title = c1.text_input("Titre de la séance")
        day_relative = c2.selectbox(
            "Jour relatif au match",
            ["J-5", "J-4", "J-3", "J-2", "J-1", "J", "J+1", "J+2"],
            index=4,
        )
        c3, c4 = st.columns(2)
        session_date = c3.date_input("Date", value=date_type.today())
        session_time = c4.time_input("Heure", value=time_type(10, 0))
        description = st.text_area("Description")

        st.markdown("**Procédés de la séance**")
        procedes_raw = st.data_editor(
            pd.DataFrame([{"Contenu": "", "Durée (min)": 15}]),
            num_rows="dynamic",
            use_container_width=True,
            key="proc_editor",
        )

        st.markdown("**Joueurs à convoquer**")
        joueurs = db.list_players()
        noms_selectionnes = st.multiselect(
            "Sélectionne les joueurs",
            options=[j["full_name"] for j in joueurs],
        )

        pdf_file = st.file_uploader("Joindre un PDF (optionnel)", type=["pdf"])

        submitted = st.form_submit_button("Créer la séance")

    if submitted:
        if not title.strip():
            st.error("Le titre est obligatoire.")
            return

        session_id = db.create_session(
            title=title.strip(),
            description=description.strip(),
            day_relative=day_relative,
            date=session_date.isoformat(),
            time=session_time.strftime("%H:%M"),
            created_by=user["id"],
        )

        for ordre, row in enumerate(procedes_raw.itertuples(index=False), start=1):
            contenu = str(row[0]).strip() if row[0] else ""
            duree = int(row[1]) if row[1] else 0
            if contenu and duree > 0:
                db.add_procede(session_id, contenu, duree, ordre)

        ids = [j["id"] for j in joueurs if j["full_name"] in noms_selectionnes]
        if ids:
            db.convoquer_joueurs(session_id, ids)

        if pdf_file is not None:
            db.add_pdf(session_id, pdf_file.name, pdf_file.read())

        st.success("Séance créée avec succès ✅")
        st.balloons()
        time.sleep(1.8)
        st.rerun()


# =============================================================================
# VUE JOUEUR
# =============================================================================

def render_player_sessions() -> None:
    user = st.session_state["user"]
    st.header("📅 Mes convocations")

    sessions = db.list_sessions_for_player(user["id"])
    if not sessions:
        st.info("Tu n'as aucune convocation pour le moment.")
        return

    events = _sessions_to_events(sessions)
    state = calendar(
        events=events,
        options=_calendar_options(),
        key="player_calendar",
    )
    selected_id = _get_selected_id_from_calendar_state(state)

    st.markdown("---")
    st.subheader("Détail d'une séance")
    options = {
        f"{s['date']} {s['time']} — {s['title']} ({STATUT_EMOJI.get(s['status'], '')})": s["id"]
        for s in sessions
    }
    default_idx = 0
    if selected_id:
        for i, sid in enumerate(options.values()):
            if sid == selected_id:
                default_idx = i
                break
    choix = st.selectbox(
        "Choisir une séance",
        list(options.keys()),
        index=default_idx,
        key="player_select_session",
    )
    _render_player_session_detail(options[choix])


def _render_player_session_detail(session_id: int) -> None:
    session = db.get_session(session_id)
    if not session:
        return

    st.markdown(f"### {session['title']}")
    st.caption(f"{session['date']} à {session['time']} — {session['day_relative'] or ''}")
    if session["description"]:
        st.write(session["description"])

    procedes = db.list_procedes(session_id)
    if procedes:
        st.markdown("**Procédés de la séance**")
        df_proc = pd.DataFrame([{
            "Ordre": p["ordre"],
            "Contenu": p["name"],
            "Durée (min)": p["duration"],
        } for p in procedes])
        st.table(df_proc)

    pdfs = db.list_pdfs(session_id)
    if pdfs:
        st.markdown("**Documents joints**")
        for pdf in pdfs:
            fp = Path(pdf["filepath"])
            if fp.exists():
                with open(fp, "rb") as f:
                    st.download_button(
                        f"📄 {pdf['filename']}",
                        data=f.read(),
                        file_name=pdf["filename"],
                        mime="application/pdf",
                        key=f"ppdf_{pdf['id']}",
                    )
