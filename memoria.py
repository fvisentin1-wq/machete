# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. - Memoria permanente SQLite potenziata
Gestione automatica delle conversazioni e delle preferenze/ricordi a lungo termine.
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_DIR, "memoria.db")

def connessione():
    os.makedirs(DB_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def inizializza_memoria():
    with connessione() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversazioni (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ruolo TEXT NOT NULL,
                contenuto TEXT NOT NULL,
                data_creazione DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS preferenze (
                chiave TEXT PRIMARY KEY,
                valore TEXT,
                data_aggiornamento DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()

def salva_messaggio(ruolo, contenuto):
    if ruolo not in ("user", "assistant"):
        return
    if not contenuto or not contenuto.strip():
        return
    try:
        with connessione() as db:
            db.execute(
                """
                INSERT INTO conversazioni (ruolo, contenuto)
                VALUES (?, ?)
                """,
                (ruolo, contenuto.strip())
            )
            db.commit()
    except Exception as e:
        print(f"[ERRORE SALVA MESSAGGIO] {e}")

def carica_ultimi_messaggi(limite=40):
    try:
        with connessione() as db:
            righe = db.execute(
                """
                SELECT ruolo, contenuto
                FROM conversazioni
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,)
            ).fetchall()

        return [
            {
                "role": riga["ruolo"],
                "content": riga["contenuto"]
            }
            for riga in reversed(righe)
        ]
    except Exception:
        return []

def imposta_preferenza(chiave, valore):
    """Salva o aggiorna un ricordo/preferenza permanente dell'utente"""
    chiave_clean = chiave.strip().lower().replace(" ", "_")
    valore_clean = valore.strip()
    try:
        with connessione() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO preferenze (chiave, valore, data_aggiornamento)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (chiave_clean, valore_clean)
            )
            db.commit()
        print(f"[MEMORIA APPRESA] {chiave_clean} -> {valore_clean}")
    except Exception as e:
        print(f"[ERRORE SALVA PREFERENZA] {e}")

def ottieni_preferenza(chiave):
    chiave_clean = chiave.strip().lower().replace(" ", "_")
    try:
        with connessione() as db:
            riga = db.execute(
                """
                SELECT valore
                FROM preferenze
                WHERE chiave = ?
                """,
                (chiave_clean,)
            ).fetchone()
        return riga["valore"] if riga else None
    except Exception:
        return None

def carica_tutte_preferenze():
    try:
        with connessione() as db:
            righe = db.execute(
                """
                SELECT chiave, valore
                FROM preferenze
                ORDER BY data_aggiornamento DESC
                """
            ).fetchall()
        return {riga["chiave"]: riga["valore"] for riga in righe}
    except Exception:
        return {}

def cancella_tutte_preferenze():
    """Cancella tutti i ricordi memorizzati su richiesta dell'utente"""
    try:
        with connessione() as db:
            db.execute("DELETE FROM preferenze")
            db.commit()
        print("[MEMORIA] Tutte le preferenze cancellate.")
    except Exception as e:
        print(f"[ERRORE CANCELLA PREFERENZE] {e}")

def cancella_memoria():
    try:
        with connessione() as db:
            db.execute("DELETE FROM conversazioni")
            db.commit()
    except Exception:
        pass
