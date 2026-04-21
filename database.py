"""
database.py
-----------
Toutes les interactions avec la base SQLite.

Les utilisateurs sont définis dans les secrets Streamlit (.streamlit/secrets.toml
en local, "Settings → Secrets" sur share.streamlit.io). Au démarrage de
l'application, on les synchronise en base via `sync_users_from_secrets()` pour
préserver les relations (convocations, réponses...).
"""

import sqlite3
from pathlib import Path
from typing import Optional, Mapping

DB_PATH = Path(__file__).parent / "data" / "football.db"
PDF_DIR = Path(__file__).parent / "data" / "pdfs"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT UNIQUE NOT NULL,
            role       TEXT NOT NULL,           -- 'staff' ou 'joueur'
            full_name  TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            day_relative TEXT,
            date         TEXT NOT NULL,
            time         TEXT NOT NULL,
            created_by   INTEGER,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS procedes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            name        TEXT NOT NULL,
            duration    INTEGER NOT NULL,
            ordre       INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS convocations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            player_id   INTEGER NOT NULL,
            status      TEXT DEFAULT 'convoque',
            UNIQUE(session_id, player_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id)  REFERENCES users(id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdfs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            filename    TEXT NOT NULL,
            filepath    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questionnaires (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL UNIQUE,
            title       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            questionnaire_id  INTEGER NOT NULL,
            text              TEXT NOT NULL,
            FOREIGN KEY (questionnaire_id) REFERENCES questionnaires(id) ON DELETE CASCADE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id  INTEGER NOT NULL,
            player_id    INTEGER NOT NULL,
            value        INTEGER NOT NULL,
            UNIQUE(question_id, player_id),
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
            FOREIGN KEY (player_id)   REFERENCES users(id)
        );
    """)

    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# Utilisateurs (synchronisés depuis st.secrets)
# -----------------------------------------------------------------------------

def upsert_user(username: str, role: str, full_name: str) -> int:
    """Insère ou met à jour un utilisateur et renvoie son id."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO users (username, role, full_name) VALUES (?, ?, ?)",
            (username, role, full_name),
        )
        user_id = cur.lastrowid
    else:
        user_id = row["id"]
        conn.execute(
            "UPDATE users SET role = ?, full_name = ? WHERE id = ?",
            (role, full_name, user_id),
        )
    conn.commit()
    conn.close()
    return user_id


def sync_users_from_secrets(users: Mapping[str, Mapping]) -> None:
    """
    Synchronise tous les utilisateurs depuis le dict des secrets.
    Format attendu :
        {
            "staff":  {"password": "...", "role": "staff",  "full_name": "..."},
            "mbappe": {"password": "...", "role": "joueur", "full_name": "..."},
            ...
        }
    Le password n'est PAS stocké en base (l'auth est gérée côté secrets).
    """
    for username, data in users.items():
        role = data.get("role", "joueur")
        full_name = data.get("full_name", username)
        upsert_user(username, role, full_name)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return row


def list_players() -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM users WHERE role = 'joueur' ORDER BY full_name"
    ).fetchall()
    conn.close()
    return rows


# -----------------------------------------------------------------------------
# Séances
# -----------------------------------------------------------------------------

def create_session(title, description, day_relative, date, time, created_by) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO sessions (title, description, day_relative, date, time, created_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, description, day_relative, date, time, created_by),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


def list_sessions() -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY date DESC, time DESC"
    ).fetchall()
    conn.close()
    return rows


def list_sessions_for_player(player_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, c.status
           FROM sessions s
           JOIN convocations c ON c.session_id = s.id
           WHERE c.player_id = ?
           ORDER BY s.date DESC, s.time DESC""",
        (player_id,),
    ).fetchall()
    conn.close()
    return rows


def get_session(session_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row


def delete_session(session_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# Procédés
# -----------------------------------------------------------------------------

def add_procede(session_id: int, name: str, duration: int, ordre: int = 0) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO procedes (session_id, name, duration, ordre) VALUES (?, ?, ?, ?)",
        (session_id, name, duration, ordre),
    )
    conn.commit()
    conn.close()


def list_procedes(session_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM procedes WHERE session_id = ? ORDER BY ordre, id",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


# -----------------------------------------------------------------------------
# Convocations
# -----------------------------------------------------------------------------

def convoquer_joueurs(session_id: int, player_ids: list[int]) -> None:
    conn = get_connection()
    for pid in player_ids:
        conn.execute(
            """INSERT OR IGNORE INTO convocations (session_id, player_id, status)
               VALUES (?, ?, 'convoque')""",
            (session_id, pid),
        )
    conn.commit()
    conn.close()


def list_convocations(session_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.*, u.full_name, u.username
           FROM convocations c
           JOIN users u ON u.id = c.player_id
           WHERE c.session_id = ?
           ORDER BY u.full_name""",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


def update_status(session_id: int, player_id: int, status: str) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE convocations SET status = ?
           WHERE session_id = ? AND player_id = ?""",
        (status, session_id, player_id),
    )
    conn.commit()
    conn.close()


def is_player_convoque(session_id: int, player_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM convocations WHERE session_id = ? AND player_id = ?",
        (session_id, player_id),
    ).fetchone()
    conn.close()
    return row is not None


# -----------------------------------------------------------------------------
# PDF
# -----------------------------------------------------------------------------

def add_pdf(session_id: int, filename: str, uploaded_bytes: bytes) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"session_{session_id}_{filename}"
    filepath = PDF_DIR / safe_name
    with open(filepath, "wb") as f:
        f.write(uploaded_bytes)

    conn = get_connection()
    conn.execute(
        "INSERT INTO pdfs (session_id, filename, filepath) VALUES (?, ?, ?)",
        (session_id, filename, str(filepath)),
    )
    conn.commit()
    conn.close()


def list_pdfs(session_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pdfs WHERE session_id = ?", (session_id,)
    ).fetchall()
    conn.close()
    return rows


# -----------------------------------------------------------------------------
# Questionnaires
# -----------------------------------------------------------------------------

def create_questionnaire(session_id: int, title: str, questions: list[str]) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO questionnaires (session_id, title) VALUES (?, ?)",
        (session_id, title),
    )
    q_id = cur.lastrowid
    for qtext in questions:
        if qtext.strip():
            conn.execute(
                "INSERT INTO questions (questionnaire_id, text) VALUES (?, ?)",
                (q_id, qtext.strip()),
            )
    conn.commit()
    conn.close()
    return q_id


def get_questionnaire_by_session(session_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM questionnaires WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    return row


def list_questions(questionnaire_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM questions WHERE questionnaire_id = ? ORDER BY id",
        (questionnaire_id,),
    ).fetchall()
    conn.close()
    return rows


def save_responses(player_id: int, answers: dict[int, int]) -> None:
    conn = get_connection()
    for question_id, value in answers.items():
        conn.execute(
            """INSERT INTO responses (question_id, player_id, value)
               VALUES (?, ?, ?)
               ON CONFLICT(question_id, player_id)
               DO UPDATE SET value = excluded.value""",
            (question_id, player_id, int(value)),
        )
    conn.commit()
    conn.close()


def list_responses(questionnaire_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.value,
                  u.full_name   AS player_name,
                  q.text        AS question_text,
                  q.id          AS question_id,
                  u.id          AS player_id
           FROM responses r
           JOIN questions q ON q.id = r.question_id
           JOIN users u     ON u.id = r.player_id
           WHERE q.questionnaire_id = ?
           ORDER BY q.id, u.full_name""",
        (questionnaire_id,),
    ).fetchall()
    conn.close()
    return rows


def has_player_answered(questionnaire_id: int, player_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        """SELECT 1
           FROM responses r
           JOIN questions q ON q.id = r.question_id
           WHERE q.questionnaire_id = ? AND r.player_id = ?
           LIMIT 1""",
        (questionnaire_id, player_id),
    ).fetchone()
    conn.close()
    return row is not None
