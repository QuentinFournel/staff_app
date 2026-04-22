"""
database.py
-----------
Couche d'accès SQLite pour l'application Club — Séances & Questionnaires.

Les utilisateurs sont définis dans les secrets Streamlit (pas de mot de passe
stocké ici). La table `users` sert uniquement à relier un joueur aux
convocations, séances et questionnaires via un `user_id` stable.

Tables :
    users, sessions, procedes, convocations, pdfs,
    questionnaires, questions, responses
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable


DB_PATH = Path(__file__).parent / "data" / "football.db"
PDF_DIR = Path(__file__).parent / "data" / "pdfs"


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    with get_conn() as conn:
        c = conn.cursor()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                role       TEXT NOT NULL CHECK (role IN ('staff','joueur')),
                full_name  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                j_relative  TEXT,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                created_by  INTEGER NOT NULL REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS procedes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                label      TEXT NOT NULL,
                duration   INTEGER NOT NULL,
                ordre      INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS convocations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                player_id  INTEGER NOT NULL REFERENCES users(id),
                status     TEXT NOT NULL DEFAULT 'convoque'
                    CHECK (status IN ('convoque','present','absent','malade','adapte')),
                UNIQUE (session_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS pdfs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                filename   TEXT NOT NULL,
                path       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questionnaires (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
                title      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                questionnaire_id   INTEGER NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
                text               TEXT NOT NULL,
                ordre              INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS responses (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id  INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                player_id    INTEGER NOT NULL REFERENCES users(id),
                value        INTEGER NOT NULL CHECK (value BETWEEN 0 AND 100),
                UNIQUE (question_id, player_id)
            );
            """
        )


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------

def upsert_user(username: str, role: str, full_name: str) -> int:
    """Crée ou met à jour un utilisateur à partir des secrets. Retourne son id."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO users (username, role, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                role = excluded.role,
                full_name = excluded.full_name
            """,
            (username, role, full_name),
        )
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        return c.fetchone()["id"]


def sync_users_from_secrets(users_dict: dict) -> None:
    """Synchronise la table users avec le contenu des secrets Streamlit."""
    for username, data in users_dict.items():
        upsert_user(
            username=str(username).lower().strip(),
            role=data.get("role", "joueur"),
            full_name=data.get("full_name", username),
        )


def get_user_by_username(username: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.lower().strip(),)
        ).fetchone()
    return row


def list_players() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name FROM users WHERE role = 'joueur' ORDER BY full_name"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Séances
# ---------------------------------------------------------------------------

def create_session(
    title: str,
    description: str,
    j_relative: str,
    date: str,
    time: str,
    created_by: int,
    procedes: Iterable[tuple[str, int]] = (),
) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO sessions (title, description, j_relative, date, time, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, description, j_relative, date, time, created_by),
        )
        session_id = c.lastrowid
        for i, (label, duration) in enumerate(procedes):
            c.execute(
                "INSERT INTO procedes (session_id, label, duration, ordre) VALUES (?, ?, ?, ?)",
                (session_id, label, duration, i),
            )
    return session_id


def update_session(
    session_id: int,
    title: str,
    description: str,
    j_relative: str,
    date: str,
    time: str,
    procedes: Iterable[tuple[str, int]],
) -> None:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            UPDATE sessions
               SET title=?, description=?, j_relative=?, date=?, time=?
             WHERE id=?
            """,
            (title, description, j_relative, date, time, session_id),
        )
        c.execute("DELETE FROM procedes WHERE session_id = ?", (session_id,))
        for i, (label, duration) in enumerate(procedes):
            c.execute(
                "INSERT INTO procedes (session_id, label, duration, ordre) VALUES (?, ?, ?, ?)",
                (session_id, label, duration, i),
            )


def delete_session(session_id: int) -> None:
    # On purge les PDF sur disque avant suppression en cascade.
    for pdf in list_pdfs(session_id):
        try:
            os.remove(pdf["path"])
        except OSError:
            pass
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def list_sessions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY date ASC, time ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_procedes(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM procedes WHERE session_id = ? ORDER BY ordre ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sessions_for_player(player_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*
              FROM sessions s
              JOIN convocations c ON c.session_id = s.id
             WHERE c.player_id = ?
             ORDER BY s.date ASC, s.time ASC
            """,
            (player_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Convocations
# ---------------------------------------------------------------------------

def convoquer_joueurs(session_id: int, player_ids: Iterable[int]) -> None:
    """Remplace la liste des convocations par celle fournie."""
    ids = list(player_ids)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM convocations WHERE session_id = ? AND player_id NOT IN (%s)"
            % (",".join("?" * len(ids)) if ids else "NULL"),
            (session_id, *ids) if ids else (session_id,),
        )
        for pid in ids:
            c.execute(
                """
                INSERT INTO convocations (session_id, player_id, status)
                VALUES (?, ?, 'convoque')
                ON CONFLICT(session_id, player_id) DO NOTHING
                """,
                (session_id, pid),
            )


def list_convocations(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.status, u.id AS player_id, u.full_name, u.username
              FROM convocations c
              JOIN users u ON u.id = c.player_id
             WHERE c.session_id = ?
             ORDER BY u.full_name
            """,
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_convocation_status(convocation_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE convocations SET status = ? WHERE id = ?",
            (status, convocation_id),
        )


def is_player_convoque(session_id: int, player_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM convocations WHERE session_id = ? AND player_id = ?",
            (session_id, player_id),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------------

def add_pdf(session_id: int, filename: str, content: bytes) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"session_{session_id}_{filename}"
    path = PDF_DIR / safe_name
    with open(path, "wb") as f:
        f.write(content)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pdfs (session_id, filename, path) VALUES (?, ?, ?)",
            (session_id, filename, str(path)),
        )


def list_pdfs(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pdfs WHERE session_id = ?", (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_pdf(pdf_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT path FROM pdfs WHERE id = ?", (pdf_id,)).fetchone()
        if row:
            try:
                os.remove(row["path"])
            except OSError:
                pass
        conn.execute("DELETE FROM pdfs WHERE id = ?", (pdf_id,))


# ---------------------------------------------------------------------------
# Questionnaires
# ---------------------------------------------------------------------------

def create_questionnaire(session_id: int, title: str, questions: Iterable[str]) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO questionnaires (session_id, title) VALUES (?, ?)",
            (session_id, title),
        )
        qid = c.lastrowid
        for i, qtext in enumerate(questions):
            c.execute(
                "INSERT INTO questions (questionnaire_id, text, ordre) VALUES (?, ?, ?)",
                (qid, qtext, i),
            )
    return qid


def get_questionnaire_by_session(session_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM questionnaires WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def list_questions(questionnaire_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM questions WHERE questionnaire_id = ? ORDER BY ordre ASC",
            (questionnaire_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_responses(player_id: int, answers: dict[int, int]) -> None:
    """`answers` : {question_id: value}. Upsert pour permettre la modif."""
    with get_conn() as conn:
        c = conn.cursor()
        for qid, val in answers.items():
            c.execute(
                """
                INSERT INTO responses (question_id, player_id, value)
                VALUES (?, ?, ?)
                ON CONFLICT(question_id, player_id) DO UPDATE SET
                    value = excluded.value
                """,
                (qid, player_id, val),
            )


def has_player_answered(questionnaire_id: int, player_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1
              FROM responses r
              JOIN questions q ON q.id = r.question_id
             WHERE q.questionnaire_id = ? AND r.player_id = ?
             LIMIT 1
            """,
            (questionnaire_id, player_id),
        ).fetchone()
    return row is not None


def list_responses(questionnaire_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.value,
                   q.text AS question_text,
                   u.full_name AS player_name
              FROM responses r
              JOIN questions q ON q.id = r.question_id
              JOIN users u ON u.id = r.player_id
             WHERE q.questionnaire_id = ?
             ORDER BY u.full_name, q.ordre
            """,
            (questionnaire_id,),
        ).fetchall()
    return [dict(r) for r in rows]
