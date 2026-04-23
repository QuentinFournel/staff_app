"""
database.py
-----------
Couche d'accès SQLite pour l'application "Séances & Questionnaires".

Tables :
    users             (id, username UNIQUE, full_name, role)
    sessions          (id, title, description, j_relative, date, time, created_by)
    procedes          (id, session_id, position, label, duration)
    convocations      (id, session_id, player_id, status) — UNIQUE(session, player)
    session_pdfs      (id, session_id, filename, path)
    questionnaires    (id, session_id UNIQUE, title)
    questions         (id, questionnaire_id, position, text)
    responses         (id, player_id, question_id, value) — UNIQUE(player, question)
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
DB_PATH = DATA_DIR / "club.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Init & migrations
# ---------------------------------------------------------------------------

def init_db() -> None:
    with get_conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                role      TEXT NOT NULL CHECK (role IN ('staff','player'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                j_relative  TEXT,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                created_by  INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS procedes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                position   INTEGER NOT NULL DEFAULT 0,
                label      TEXT NOT NULL,
                duration   INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS convocations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                player_id  INTEGER NOT NULL,
                status     TEXT NOT NULL DEFAULT 'convoque',
                UNIQUE(session_id, player_id),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (player_id)  REFERENCES users(id)    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_pdfs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                filename   TEXT NOT NULL,
                path       TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS questionnaires (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE,
                title      TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS questions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                questionnaire_id INTEGER NOT NULL,
                position         INTEGER NOT NULL DEFAULT 0,
                text             TEXT NOT NULL,
                FOREIGN KEY (questionnaire_id) REFERENCES questionnaires(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS responses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id   INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                value       INTEGER NOT NULL,
                UNIQUE(player_id, question_id),
                FOREIGN KEY (player_id)   REFERENCES users(id)     ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            );
            """
        )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def sync_users_from_secrets(secrets_users: dict) -> None:
    """Crée / met à jour les utilisateurs listés dans secrets.toml."""
    with get_conn() as c:
        for username, data in secrets_users.items():
            full_name = data.get("full_name", username)
            role      = data.get("role", "player")
            c.execute(
                """
                INSERT INTO users (username, full_name, role)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    full_name = excluded.full_name,
                    role      = excluded.role
                """,
                (username, full_name, role),
            )


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_conn() as c:
        return c.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def list_players() -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT id, username, full_name FROM users WHERE role = 'player' ORDER BY full_name"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def list_sessions() -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM sessions ORDER BY date, time"
        ).fetchall()
    return [dict(r) for r in rows]


def list_sessions_for_player(player_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT s.*
            FROM sessions s
            JOIN convocations c ON c.session_id = s.id
            WHERE c.player_id = ?
            ORDER BY s.date, s.time
            """,
            (player_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def create_session(
    *,
    title: str,
    description: str,
    j_relative: str,
    date: str,
    time: str,
    created_by: int | None,
    procedes: Iterable[tuple[str, int]],
) -> int:
    with get_conn() as c:
        cur = c.execute(
            """
            INSERT INTO sessions (title, description, j_relative, date, time, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, description, j_relative, date, time, created_by),
        )
        session_id = cur.lastrowid
        for pos, (label, duration) in enumerate(procedes):
            c.execute(
                """
                INSERT INTO procedes (session_id, position, label, duration)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, pos, label, int(duration)),
            )
    return session_id


def update_session(
    *,
    session_id: int,
    title: str,
    description: str,
    j_relative: str,
    date: str,
    time: str,
    procedes: Iterable[tuple[str, int]],
) -> None:
    with get_conn() as c:
        c.execute(
            """
            UPDATE sessions
            SET title = ?, description = ?, j_relative = ?, date = ?, time = ?
            WHERE id = ?
            """,
            (title, description, j_relative, date, time, session_id),
        )
        c.execute("DELETE FROM procedes WHERE session_id = ?", (session_id,))
        for pos, (label, duration) in enumerate(procedes):
            c.execute(
                """
                INSERT INTO procedes (session_id, position, label, duration)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, pos, label, int(duration)),
            )


def delete_session(session_id: int) -> None:
    # Supprime aussi les PDFs sur le disque (FK ON DELETE CASCADE
    # retire les lignes, mais les fichiers restent).
    with get_conn() as c:
        rows = c.execute(
            "SELECT path FROM session_pdfs WHERE session_id = ?", (session_id,)
        ).fetchall()
        for r in rows:
            try:
                os.remove(r["path"])
            except OSError:
                pass
        c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# ---------------------------------------------------------------------------
# Procédés
# ---------------------------------------------------------------------------

def list_procedes(session_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM procedes WHERE session_id = ? ORDER BY position, id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Convocations
# ---------------------------------------------------------------------------

def convoquer_joueurs(session_id: int, player_ids: Iterable[int]) -> None:
    player_ids = list(player_ids)
    with get_conn() as c:
        c.execute("DELETE FROM convocations WHERE session_id = ?", (session_id,))
        for pid in player_ids:
            c.execute(
                """
                INSERT INTO convocations (session_id, player_id, status)
                VALUES (?, ?, 'convoque')
                """,
                (session_id, pid),
            )


def list_convocations(session_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT c.id, c.player_id, c.status,
                   u.username, u.full_name
            FROM convocations c
            JOIN users u ON u.id = c.player_id
            WHERE c.session_id = ?
            ORDER BY u.full_name
            """,
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_convocation_status(conv_id: int, status: str) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE convocations SET status = ? WHERE id = ?",
            (status, conv_id),
        )


def is_player_convoque(session_id: int, player_id: int) -> bool:
    with get_conn() as c:
        row = c.execute(
            "SELECT 1 FROM convocations WHERE session_id = ? AND player_id = ?",
            (session_id, player_id),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------------

def add_pdf(session_id: int, filename: str, data: bytes) -> int:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    target = PDF_DIR / f"session_{session_id}_{safe_name}"
    with open(target, "wb") as f:
        f.write(data)

    with get_conn() as c:
        cur = c.execute(
            """
            INSERT INTO session_pdfs (session_id, filename, path)
            VALUES (?, ?, ?)
            """,
            (session_id, filename, str(target)),
        )
        return cur.lastrowid


def list_pdfs(session_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM session_pdfs WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_pdf(pdf_id: int) -> None:
    with get_conn() as c:
        row = c.execute(
            "SELECT path FROM session_pdfs WHERE id = ?", (pdf_id,)
        ).fetchone()
        if row is not None:
            try:
                os.remove(row["path"])
            except OSError:
                pass
        c.execute("DELETE FROM session_pdfs WHERE id = ?", (pdf_id,))


# ---------------------------------------------------------------------------
# Questionnaires
# ---------------------------------------------------------------------------

def get_questionnaire_by_session(session_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM questionnaires WHERE session_id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def create_questionnaire(session_id: int, title: str, questions: list[str]) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO questionnaires (session_id, title) VALUES (?, ?)",
            (session_id, title),
        )
        quest_id = cur.lastrowid
        for pos, text in enumerate(questions):
            c.execute(
                """
                INSERT INTO questions (questionnaire_id, position, text)
                VALUES (?, ?, ?)
                """,
                (quest_id, pos, text),
            )
    return quest_id


def update_questionnaire(quest_id: int, title: str, questions: list[str]) -> None:
    """Met à jour titre + questions. Supprime les anciennes questions (et donc
    les réponses associées, via ON DELETE CASCADE)."""
    with get_conn() as c:
        c.execute(
            "UPDATE questionnaires SET title = ? WHERE id = ?",
            (title, quest_id),
        )
        c.execute(
            "DELETE FROM questions WHERE questionnaire_id = ?", (quest_id,)
        )
        for pos, text in enumerate(questions):
            c.execute(
                """
                INSERT INTO questions (questionnaire_id, position, text)
                VALUES (?, ?, ?)
                """,
                (quest_id, pos, text),
            )


def delete_questionnaire(quest_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM questionnaires WHERE id = ?", (quest_id,))


def list_questions(quest_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT * FROM questions
            WHERE questionnaire_id = ?
            ORDER BY position, id
            """,
            (quest_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Réponses
# ---------------------------------------------------------------------------

def list_responses(quest_id: int) -> list[dict]:
    with get_conn() as c:
        rows = c.execute(
            """
            SELECT r.value,
                   q.text AS question_text,
                   u.full_name AS player_name
            FROM responses r
            JOIN questions q ON q.id = r.question_id
            JOIN users     u ON u.id = r.player_id
            WHERE q.questionnaire_id = ?
            ORDER BY u.full_name, q.position
            """,
            (quest_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def has_player_answered(quest_id: int, player_id: int) -> bool:
    with get_conn() as c:
        row = c.execute(
            """
            SELECT 1 FROM responses r
            JOIN questions q ON q.id = r.question_id
            WHERE q.questionnaire_id = ? AND r.player_id = ?
            LIMIT 1
            """,
            (quest_id, player_id),
        ).fetchone()
    return row is not None


def save_responses(player_id: int, answers: dict[int, int]) -> None:
    """answers : {question_id: value}. Remplace les réponses existantes."""
    with get_conn() as c:
        for qid, value in answers.items():
            c.execute(
                """
                INSERT INTO responses (player_id, question_id, value)
                VALUES (?, ?, ?)
                ON CONFLICT(player_id, question_id) DO UPDATE SET
                    value = excluded.value
                """,
                (player_id, int(qid), int(value)),
            )
