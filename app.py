# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. CORE 1.0 (MACHETE OS) - Grafica Classica Quantum HUD + Timeout Fix + MUSIC LAB
Flask + Groq + Whisper + DuckDuckGo Live Search + Memoria SQLite + Edge-TTS + Super-Actions
"""

import os
import sys
import re
# --- AUTO-PULIZIA | NELLE REGEX ---
try:
    for _nome_file in ("app_2.py", "app.py", "jarvis.py"):
        if os.path.exists(_nome_file):
            with open(_nome_file, "r", encoding="utf-8", errors="ignore") as _f:
                _src = _f.read()
            if r"|" in _src or r"|" in _src:
                _pulito = _src.replace(r"|", "|").replace(r"|", "|")
                with open(_nome_file, "w", encoding="utf-8") as _f:
                    _f.write(_pulito)
                print(f"[FIX REGEX] Ripulito \| in {_nome_file}")
except Exception as _e:
    print(f"[FIX REGEX ERR] {_e}")
import threading
import asyncio
import io
import time
import json
import wave
import math
import array
import tempfile
import urllib.parse
import subprocess

from flask import Flask, render_template, jsonify, request, send_file, Response, send_from_directory
import edge_tts
import requests
from groq import Groq

# Ricerca Web Live tramite DuckDuckGo (zero chiavi API aggiuntive necessarie)
try:
    from duckduckgo_search import DDGS
    ddgs_available = True
except ImportError:
    ddgs_available = False
    print("[AVVISO] Per la ricerca web live installare: pip install duckduckgo-search")

import jarvis as jarvis_modulo
from jarvis import (
    calibra_microfono,
    registra,
    trascrivi,
    pensa,
    analizza_immagine,
    analizza_schermo,
    blocca_computer,
    alza_volume,
    abbassa_volume,
    toogle_muto,
    mostra_desktop,
    play_pause_musica,
    prossima_canzone,
    canzone_precedente,
    esegui_azione,
    pulisci_per_voce,
    genera_saluto_avvio,
    normalizza,
    e_allucinazione,
    chiedi_llm,
    MODELLO_CHAT
)

from memoria import (
    inizializza_memoria,
    salva_messaggio,
    carica_ultimi_messaggi,
    carica_tutte_preferenze,
    cancella_tutte_preferenze
)

try:
    import psutil
    psutil.cpu_percent(None)
except ImportError:
    psutil = None
    print("[AVVISO] Manca psutil: CPU e RAM nella grafica mostreranno N/D.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CITTA_METEO = "Chieri"

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
state_lock = threading.Lock()
conversation_lock = threading.Lock()
music_lab_lock = threading.Lock()

MAX_HISTORY = 40
VOICE = "it-IT-ElsaNeural"

system_state = {
    "mode": "idle",
    "message": "Pronto",
    "busy": False,
    "last_user": "",
    "last_reply": ""
}

try:
    inizializza_memoria()
    storia_conversazione = carica_ultimi_messaggi(MAX_HISTORY)
    print("[MEMORIA] Database SQLite attivo.")
except Exception as e:
    print(f"[ERRORE MEMORIA] {e}")
    storia_conversazione = []


def registra_messaggio(ruolo, contenuto):
    if not contenuto or not contenuto.strip():
        return
    with conversation_lock:
        storia_conversazione.append({
            "role": ruolo,
            "content": contenuto
        })
        if len(storia_conversazione) > MAX_HISTORY:
            del storia_conversazione[:-MAX_HISTORY]
        salva_messaggio(ruolo, contenuto)


try:
    chiave_path = os.path.join(BASE_DIR, "chiave.txt")
    with open(chiave_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    GROQ_API_KEY = content.split("=", 1)[-1].strip() if "=" in content else content
    GROQ_API_KEY = GROQ_API_KEY.strip('"').strip("'")
    client_groq = Groq(api_key=GROQ_API_KEY)
    print("[GROQ] Connessione configurata.")
except Exception as e:
    print(f"[ERRORE GROQ] {e}")
    sys.exit(1)

try:
    print("[JARVIS] Calibrazione microfono con noise-gate...")
    SOGLIA_SILENZIO = calibra_microfono()
except Exception:
    SOGLIA_SILENZIO = 0.008

AZIONE_PATTERN = re.compile(r"\[\[AZIONE:([a-zA-Z_]+)|([^\]]*)\]\]")
APP_CORREZIONI = {
    "sotip": "spotify",
    "spotif": "spotify",
    "spoti": "spotify",
    "spotifai": "spotify",
    "spotfy": "spotify",
    "crom": "chrome",
    "gogle": "chrome",
    "gugol": "chrome",
    "discor": "discord",
    "notpad": "notepad",
    "blocco note": "notepad",
    "calcolatrice": "calc"
}


def normalizza_nome_app(nome):
    nome_pulito = nome.strip().lower()
    return APP_CORREZIONI.get(nome_pulito, nome_pulito)


def esegui_comando_ia(testo):
    risultati = AZIONE_PATTERN.findall(testo)
    if not risultati:
        return None
    esiti = []
    for nome_azione, parametro in risultati[:4]:
        nome_azione = nome_azione.strip().lower()
        parametro = parametro.strip()
        if nome_azione == "apri_app":
            parametro = normalizza_nome_app(parametro)
        esito = esegui_azione(nome_azione, parametro, client_groq)
        if esito:
            esiti.append(esito)
    return " ".join(esiti) if esiti else None


def aggiorna_stato(**valori):
    with state_lock:
        system_state.update(valori)


_alterna_annuncio = [False]


def annuncia_notifica(testo):
    registra_messaggio("assistant", testo)
    _alterna_annuncio[0] = not _alterna_annuncio[0]
    marcatore = "\u200b" if _alterna_annuncio[0] else ""
    aggiorna_stato(last_reply=testo + marcatore, mode="speaking", message="Promemoria...")

    def torna_pronto():
        with state_lock:
            if not system_state["busy"]:
                system_state["mode"] = "idle"
                system_state["message"] = "Pronto"

    threading.Timer(1.2, torna_pronto).start()


jarvis_modulo.imposta_notifica(annuncia_notifica)


def cerca_su_internet_live(query, max_risultati=3):
    if not ddgs_available:
        return None
    try:
        with DDGS() as ddgs:
            risultati = list(ddgs.text(query, max_results=max_risultati, region="it-it"))
            if not risultati:
                return None
            frammenti = []
            for r in risultati:
                titolo = r.get("title", "")
                corpo = r.get("body", "")
                if corpo:
                    frammenti.append(f"- {titolo}: {corpo}")
            return "\n".join(frammenti)
    except Exception as e:
        print(f"[ERRORE RICERCA WEB] {e}")
        return None


def deve_cercare_sul_web(testo):
    trigger_espliciti = [
        "notizie", "news", "chi ha vinto", "classifica", "partita", "risultato",
        "meteo domani", "prezzo", "quotazione", "uscita del film", "film al cinema",
        "chi è il presidente", "ultime su", "cosa è successo", "novità", "oggi a"
    ]
    testo_low = testo.lower()
    return any(t in testo_low for t in trigger_espliciti)


RE_VERBO = re.compile(r"^(?:apri|metti|mettimi|cerca|cercami|guarda|riproduci|fammi vedere|fammi|vai|mostrami|fai partire|ascolta)\b\s*")


def _query_pulita(t, servizio):
    """'metti despacito su spotify' -> 'despacito'"""
    t = re.sub(rf"\b(?:su|in|con|dentro|nel|sul)?\s*{servizio}\b", " ", t)
    t = RE_VERBO.sub("", t.strip())
    t = re.sub(r"^(?:(?:la|il|lo|una|un|canzone|brano|musica|video|di|dei|del|della)\s+)+", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def gestisci_super_azioni(testo_lower):
    t = testo_lower

    if re.match(r"^cerca(?:mi)? (?:su|con) google\b", t):
        query = re.sub(r"^cerca(?:mi)? (?:su|con) google", "", t).strip()
        if query:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            subprocess.Popen(f'start "" "{url}"', shell=True)
            return f"Apro la ricerca Google per {query}."

    if "youtube" in t and RE_VERBO.match(t):
        query = _query_pulita(t, "youtube")
        if query:
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            subprocess.Popen(f'start "" "{url}"', shell=True)
            return f"Apro YouTube con i risultati per {query}."
        subprocess.Popen('start "" "https://www.youtube.com"', shell=True)
        return "Apro YouTube."

    if "spotify" in t and RE_VERBO.match(t):
        query = _query_pulita(t, "spotify")
        if query:
            subprocess.Popen(f'start spotify:search:{urllib.parse.quote(query)}', shell=True)
            return f"Cerco e avvio {query} su Spotify."

    if "spegni il pc" in t or "spegni il computer" in t or "arresta il sistema" in t:
        match_min = re.search(r"tra (\d+) minut", t)
        if match_min:
            minuti = int(match_min.group(1))
            subprocess.Popen(f'shutdown -s -t {minuti * 60}', shell=True)
            return f"Arresto programmato tra {minuti} minuti, signor Marcolino."
        elif "annulla" in t:
            subprocess.Popen('shutdown -a', shell=True)
            return "Arresto programmato annullato."
        else:
            subprocess.Popen('shutdown -s -t 60', shell=True)
            return "Il computer si spegnerà tra 60 secondi. Dica 'annulla spegnimento' per fermarlo."

    return None


# ---------- MODALITA' PROGRAMMATORE ----------
RE_CODICE_PAROLE = re.compile(r"\b(python|pyton|phyton|paiton|pitone|script|programma|programmare|codice|funzione|classe|snippet|javascript|html|css|sql|bash|powershell)\b")
RE_CODICE_VERBI = re.compile(r"\b(scrivi|scrivimi|crea|creami|genera|generami|fammi|correggi|correggimi|debug|ottimizza|converti|spiega|spiegami)\b")

SISTEMA_CODICE = {
    "role": "system",
    "content": (
        "Sei MACHETE, l'assistente del signor Marcolino, che non e' un programmatore: spiega in modo semplice. "
        "Quando ti chiede del codice scrivi Python (salvo diversa richiesta), completo e funzionante, "
        "dentro UN solo blocco ```python ... ```, con commenti brevi in italiano. "
        "Prima del blocco scrivi una frase che dice cosa fa. Dopo il blocco, al massimo 3 frasi: "
        "come salvarlo (ad esempio come nome.py), come avviarlo e quali librerie installare con pip. "
        "Se l'utente incolla un errore o del codice, trova il problema e restituisci il codice corretto per intero. "
        "Il codice verra' eseguito su Windows come file .py, senza tastiera: non usare input(), usa print() per mostrare i risultati e valori di esempio. "
        "Non scrivere mai comandi [[AZIONE:...]] e non dire di aver eseguito qualcosa sul computer. Rispondi in italiano."
    )
}


def e_richiesta_codice(testo):
    t = (testo or "").lower()
    if t.startswith("/codice") or "```" in t or "traceback (most recent call last)" in t:
        return True
    if any(x in t for x in ("codice fiscale", "codice postale", "codice sconto", "codice promozionale")):
        return False
    return bool(RE_CODICE_PAROLE.search(t) and RE_CODICE_VERBI.search(t))


def scrivi_codice():
    with conversation_lock:
        recenti = list(storia_conversazione)[-8:]
    return chiedi_llm(client_groq, [SISTEMA_CODICE] + recenti, [MODELLO_CHAT], max_tokens=2500, temperature=0.2)


def elabora_richiesta(user_text):
    """Elabora una richiesta (detta a voce o scritta) e restituisce la risposta."""
    aggiorna_stato(last_user=user_text, message="Analisi richiesta...")
    registra_messaggio("user", user_text)
    user_lower = user_text.lower()

    codice = e_richiesta_codice(user_text)
    esito_super = None if codice else gestisci_super_azioni(normalizza(user_text))
    if codice:
        aggiorna_stato(mode="thinking", message="Scrivo il codice...")
        risposta_originale = scrivi_codice()
    elif esito_super:
        risposta_originale = esito_super
    elif any(w in user_lower for w in ["cosa sai su di me", "cosa ti ricordi di me", "cosa ricordi di me", "cosa sai di me", "mostrami la memoria"]):
        pref = carica_tutte_preferenze()
        if not pref:
            risposta_originale = "I miei archivi sono ancora vergini, signor Marcolino. Mi dica pure cosa desidera che custodisca su di lei."
        else:
            elenco = ", ".join([f"{k.replace('_', ' ')}: {v}" for k, v in pref.items()])
            risposta_originale = f"Ecco cosa ho appreso e custodito su di lei, signor Marcolino: {elenco}."
    elif any(w in user_lower for w in ["cancella la memoria", "dimentica tutto", "azzera la memoria", "cancella preferenze"]):
        cancella_tutte_preferenze()
        risposta_originale = "Ho cancellato tutti i dati personali e le preferenze dai miei archivi, signor Marcolino."
    elif any(w in user_lower for w in ["blocca il pc", "blocca pc", "blocca il computer", "blocca computer", "blocca lo schermo"]):
        risposta_originale = blocca_computer()
    elif any(w in user_lower for w in ["alza il volume", "alza volume", "aumenta il volume", "aumenta volume"]):
        risposta_originale = alza_volume()
    elif any(w in user_lower for w in ["abbassa il volume", "abbassa volume", "diminuisci il volume"]):
        risposta_originale = abbassa_volume()
    elif any(w in user_lower for w in ["metti muto", "disattiva audio", "silenzio audio", "togli l'audio"]):
        risposta_originale = toogle_muto()
    elif any(w in user_lower for w in ["mostra il desktop", "mostra desktop", "minimizza tutto"]):
        risposta_originale = mostra_desktop()
    elif any(w in user_lower for w in ["metti in pausa", "pausa musica", "riprendi musica", "play musica", "stop musica"]):
        risposta_originale = play_pause_musica()
    elif any(w in user_lower for w in ["prossima canzone", "cambia canzone", "salta canzone", "prossima traccia"]):
        risposta_originale = prossima_canzone()
    elif any(w in user_lower for w in ["canzone precedente", "traccia precedente"]):
        risposta_originale = canzone_precedente()
    elif ("schermo" in user_lower or "monitor" in user_lower or "display" in user_lower) and any(k in user_lower for k in ["guarda", "leggi", "vedi", "analizza", "cosa c'è", "spiega", "controlla"]):
        aggiorna_stato(mode="thinking", message="Cattura e analisi monitor...")
        risposta_originale = analizza_schermo(client_groq, user_text)
    else:
        pref_utente = carica_tutte_preferenze()
        profilo_str = ", ".join([f"{k}: {v}" for k, v in pref_utente.items()]) if pref_utente else "Nessuna preferenza specifica registrata."

        dati_web_live = ""
        if deve_cercare_sul_web(user_text):
            aggiorna_stato(mode="thinking", message="Ricerca dati sul web live...")
            risultati_web = cerca_su_internet_live(user_text)
            if risultati_web:
                dati_web_live = f"\n[DATI AGGIORNATI REPERITI IN TEMPO REALE DAL WEB]:\n{risultati_web}\n"

        system_prompt = {
            "role": "system",
            "content": f"Sei Machete, l'assistente IA personale del signor Marcolino. Stile operativo ad alta tecnologia. Dati appresi sull'utente: [{profilo_str}]. {dati_web_live} Rispondi in modo conciso, naturale e diretto."
        }

        with conversation_lock:
            messaggi = [system_prompt] + list(storia_conversazione)

        aggiorna_stato(mode="thinking", message="Sintesi risposta neurale...")
        risposta_originale = pensa(client_groq, messaggi) or "Non ho capito, signor Marcolino."
        esito = esegui_comando_ia(risposta_originale)
        if esito:
            risposta_originale = esito

    risposta_finale = pulisci_per_voce(risposta_originale)
    registra_messaggio("assistant", risposta_finale)
    aggiorna_stato(last_reply=risposta_finale, mode="speaking", message="Parlo...")
    return risposta_finale


def worker_ascolto_e_risposta():
    try:
        aggiorna_stato(mode="listening", message="In ascolto...", busy=True)

        risultato_container = []

        def task_registrazione():
            try:
                res = registra(SOGLIA_SILENZIO)
                risultato_container.append(res)
            except Exception as e:
                print(f"[ERRORE REGISTRAZIONE] {e}")

        t_reg = threading.Thread(target=task_registrazione, daemon=True)
        t_reg.start()
        t_reg.join(timeout=10.0)

        if t_reg.is_alive():
            print("[AVVISO] Timeout registrazione scaduto, sblocco microfono.")
            aggiorna_stato(mode="idle", message="Tempo di ascolto scaduto.", busy=False)
            return

        audio_file = risultato_container[0] if risultato_container else None
        if not audio_file:
            aggiorna_stato(mode="idle", message="Nessun audio rilevato.", busy=False)
            return

        aggiorna_stato(mode="thinking", message="Elaborazione audio...")
        user_text = trascrivi(client_groq, audio_file)
        if not user_text or e_allucinazione(user_text):
            if user_text:
                print(f"[WHISPER] Frase ignorata (rumore o allucinazione): {user_text}")
            aggiorna_stato(mode="idle", message="Non ho capito.", busy=False)
            return

        elabora_richiesta(user_text)

    except Exception as e:
        aggiorna_stato(mode="error", message="Errore.", last_reply=f"Errore: {e}")
    finally:
        with state_lock:
            system_state["busy"] = False
            if system_state["mode"] != "error":
                system_state["mode"] = "idle"
                system_state["message"] = "Pronto"


# ---------- MUSIC LAB ENDPOINTS ----------
_last_audio_bytes = None
_last_audio_mime = "audio/mpeg"


class _AudioBuffer(io.BytesIO):
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name


def _decodifica_pcm_ffmpeg(raw_bytes: bytes, sr: int = 22050):
    """Decodifica MP3 o WAV in campioni float32 mono tramite ffmpeg + numpy."""
    try:
        import numpy as np
        cmd = [
            "ffmpeg", "-v", "error",
            "-i", "pipe:0",
            "-f", "f32le", "-ac", "1", "-ar", str(sr),
            "pipe:1"
        ]
        p = subprocess.run(
            cmd, input=raw_bytes, capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if p.returncode != 0 or not p.stdout:
            return None, sr
        samples = np.frombuffer(p.stdout, dtype=np.float32)
        if samples.size < sr // 2:
            return None, sr
        return samples, sr
    except Exception:
        return None, sr


def _trascrivi_traccia_whisper(raw_bytes: bytes, filename: str, groq_client) -> str:
    """Trascrive voce/rap dal file audio tramite la funzione trascrivi di jarvis."""
    if groq_client is None:
        return ""
    tmp_path = None
    try:
        ext = os.path.splitext(filename)[1].lower() or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            tf.write(raw_bytes)
            tmp_path = tf.name
        try:
            testo = trascrivi(groq_client, tmp_path)
        except TypeError:
            testo = trascrivi(groq_client, _AudioBuffer(raw_bytes, filename))
        if not testo:
            return ""
        pulito = str(testo).strip()
        if e_allucinazione(pulito):
            return ""
        return pulito[:2500]
    except Exception as e:
        print(f"[MUSIC LAB WHISPER] {e}")
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _stima_tonalita_pitch_class(samples, sr: int) -> str:
    """Stima la tonalita dominante (es. D minor, C minor, G minor) tramite profilo cromatico."""
    try:
        import numpy as np
        seg = samples[:min(samples.size, sr * 25)]
        win = 4096
        if seg.size < win:
            return "D minor"
        n_hops = min(40, seg.size // win)
        chroma = np.zeros(12, dtype=np.float64)
        freqs = np.fft.rfftfreq(win, d=1.0 / sr)
        valid = (freqs >= 65.0) & (freqs <= 1050.0)
        f_valid = freqs[valid]
        midi = np.round(69.0 + 12.0 * np.log2(f_valid / 440.0)).astype(int) % 12
        hann = np.hanning(win)

        for k in range(n_hops):
            chunk = seg[k * win:(k + 1) * win] * hann
            mag = np.abs(np.fft.rfft(chunk))[valid] ** 2
            np.add.at(chroma, midi, mag)

        if chroma.sum() <= 0:
            return "D minor"
        chroma = chroma / chroma.sum()

        # Profili Krumhansl-Schmuckler semplificati (maggiore / minore)
        maj_prof = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        min_prof = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        notes_names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

        best_score = -1e9
        best_key = "D minor"
        for root in range(12):
            c_rot = np.roll(chroma, -root)
            s_maj = float(np.corrcoef(c_rot, maj_prof)[0, 1])
            s_min = float(np.corrcoef(c_rot, min_prof)[0, 1])
            if s_maj > best_score:
                best_score = s_maj
                best_key = f"{notes_names[root]} major"
            if s_min > best_score:
                best_score = s_min
                best_key = f"{notes_names[root]} minor"
        return best_key
    except Exception:
        return "D minor"


def _stima_bpm_da_inviluppo(inviluppo, rate_hz):
    if not inviluppo or len(inviluppo) < 8:
        return 120
    media = sum(inviluppo) / len(inviluppo)
    soglia = media * 1.18
    picchi_idx = []
    for i in range(1, len(inviluppo) - 1):
        if inviluppo[i] > soglia and inviluppo[i] >= inviluppo[i - 1] and inviluppo[i] >= inviluppo[i + 1]:
            if not picchi_idx or (i - picchi_idx[-1]) * (1.0 / rate_hz) >= 0.25:
                picchi_idx.append(i)
    if len(picchi_idx) < 2:
        return 120
    intervalli_sec = [
        (picchi_idx[k] - picchi_idx[k - 1]) / float(rate_hz)
        for k in range(1, len(picchi_idx))
    ]
    intervalli_validi = [dt for dt in intervalli_sec if 0.25 <= dt <= 1.5]
    if not intervalli_validi:
        return 120
    avg_dt = sum(intervalli_validi) / len(intervalli_validi)
    bpm = 60.0 / avg_dt
    while bpm < 70:
        bpm *= 2.0
    while bpm > 180:
        bpm /= 2.0
    return int(round(bpm))


def _estrai_waveform_e_metriche(raw_bytes: bytes, filename: str, groq_client=None):
    n_peaks = 64
    samples, sr = _decodifica_pcm_ffmpeg(raw_bytes, sr=22050)

    if samples is not None:
        import numpy as np
        duration_sec = round(float(samples.size) / float(sr), 2)

        chunks = np.array_split(np.abs(samples), n_peaks)
        raw_peaks = np.array([float(np.percentile(c, 95)) if c.size else 0.0 for c in chunks])
        mx = float(raw_peaks.max()) if raw_peaks.size else 1.0
        if mx > 1e-6:
            peaks = [round(max(0.05, min(1.0, float(v / mx))), 3) for v in raw_peaks]
        else:
            peaks = [0.1] * n_peaks

        hop = max(1, sr // 20)
        n_frames = samples.size // hop
        if n_frames > 16:
            trimmed = samples[:n_frames * hop].reshape(n_frames, hop)
            env = np.sqrt(np.mean(trimmed ** 2, axis=1))
            diff = np.maximum(0.0, np.diff(env))
            thr = float(diff.mean() + 0.6 * diff.std())
            peaks_idx = np.where((diff[1:-1] > thr) & (diff[1:-1] >= diff[:-2]) & (diff[1:-1] >= diff[2:]))[0] + 1
            if peaks_idx.size >= 2:
                times = peaks_idx / 20.0
                intervals = np.diff(times)
                valid = intervals[(intervals >= 0.25) & (intervals <= 1.5)]
                if valid.size > 0:
                    bpm_val = 60.0 / float(np.median(valid))
                    while bpm_val < 70:
                        bpm_val *= 2.0
                    while bpm_val > 180:
                        bpm_val /= 2.0
                    bpm = int(round(bpm_val))
                else:
                    bpm = 120
            else:
                bpm = 120
        else:
            bpm = 120

        # Media spettrale su piu' finestre del brano (non solo i primi millisecondi)
        win_fft = 2048
        if samples.size >= win_fft:
            idxs = np.linspace(0, samples.size - win_fft, num=min(24, max(1, samples.size // win_fft)), dtype=int)
            hann = np.hanning(win_fft)
            freqs = np.fft.rfftfreq(win_fft, d=1.0 / sr)
            sub_e = 0.0
            mid_e = 0.0
            high_e = 0.0
            for idx in idxs:
                seg_fft = samples[idx:idx + win_fft] * hann
                spec = np.abs(np.fft.rfft(seg_fft)) ** 2
                sub_e += float(np.sum(spec[freqs < 250]))
                mid_e += float(np.sum(spec[(freqs >= 250) & (freqs < 4000)]))
                high_e += float(np.sum(spec[freqs >= 4000]))
            tot_e = max(1e-9, sub_e + mid_e + high_e)
            sub_r = round(sub_e / tot_e, 2)
            mid_r = round(mid_e / tot_e, 2)
            high_r = round(high_e / tot_e, 2)
        else:
            sub_r, mid_r, high_r = 0.34, 0.33, 0.33

        onset_density = "HIGH" if bpm >= 135 else ("MED" if bpm >= 100 else "LOW")
        key_est = _stima_tonalita_pitch_class(samples, sr)
    else:
        peaks = [0.2] * n_peaks
        duration_sec = 0.0
        bpm = 120
        onset_density = "MED"
        key_est = "D minor"

        if filename.lower().endswith(".wav"):
            try:
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate() or 44100
                    ch = wf.getnchannels() or 1
                    sw = wf.getsampwidth() or 2
                    duration_sec = round(frames / float(rate), 2)
                    pcm = wf.readframes(frames)
                    if sw == 2 and len(pcm) >= 2:
                        wav_samples = array.array("h")
                        wav_samples.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
                        if ch > 1:
                            wav_samples = wav_samples[::ch]
                        total = len(wav_samples)
                        if total > 0:
                            step = max(1, total // n_peaks)
                            raw_peaks = []
                            for i in range(n_peaks):
                                chunk = wav_samples[i * step:(i + 1) * step]
                                if not chunk:
                                    raw_peaks.append(0.05)
                                else:
                                    m = max(abs(x) for x in chunk) / 32768.0
                                    raw_peaks.append(m)
                            mx = max(raw_peaks) or 1.0
                            peaks = [round(max(0.06, min(1.0, v / mx)), 3) for v in raw_peaks]

                            win = max(1, rate // 20)
                            env = []
                            for j in range(0, total - win, win):
                                seg = wav_samples[j:j + win]
                                rms = math.sqrt(sum((x / 32768.0) ** 2 for x in seg) / len(seg))
                                env.append(rms)
                            bpm = _stima_bpm_da_inviluppo(env, 20.0)
                            onset_density = "HIGH" if bpm >= 135 else ("MED" if bpm >= 100 else "LOW")
            except Exception as e:
                print(f"[MUSIC LAB WAV PARSE] {e}")

        if duration_sec <= 0:
            duration_sec = round(max(1.0, len(raw_bytes) / 16000.0), 2)
            for i in range(n_peaks):
                val = 0.25 + 0.45 * abs(math.sin(i * 0.47) * math.cos(i * 0.19))
                peaks[i] = round(min(1.0, val), 3)

        sub_r, mid_r, high_r = 0.42, 0.35, 0.23

    segments = []
    seg_count = 12
    c_len = max(1, len(peaks) // seg_count)
    for s in range(seg_count):
        part = peaks[s * c_len:(s + 1) * c_len]
        avg = sum(part) / max(1, len(part))
        lvl = "high" if avg >= 0.68 else ("medium" if avg >= 0.38 else "low")
        segments.append({"index": s + 1, "energy_norm": round(avg, 2), "level": lvl})

    transcript = _trascrivi_traccia_whisper(raw_bytes, filename, groq_client)

    metrics = {
        "filename": filename,
        "duration_sec": duration_sec,
        "bpm": bpm,
        "onset_density": onset_density,
        "estimated_key": key_est,
        "spectrum": {
            "sub_bass_ratio": sub_r,
            "mids_ratio": mid_r,
            "highs_ratio": high_r,
        },
        "energy_segments": segments,
        "transcript": transcript,
    }
    return {"peaks": peaks}, metrics


@app.route("/music-lab/upload-analyze", methods=["POST"])
def music_lab_upload_analyze():
    global _last_audio_bytes, _last_audio_mime
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Nessun file audio ricevuto."}), 400

    low = f.filename.lower()
    if not (low.endswith(".mp3") or low.endswith(".wav")):
        return jsonify({"error": "Formato non supportato: carica un file .mp3 o .wav."}), 400

    raw = f.read()
    if not raw:
        return jsonify({"error": "File audio vuoto."}), 400

    with music_lab_lock:
        _last_audio_bytes = raw
        _last_audio_mime = "audio/wav" if low.endswith(".wav") else "audio/mpeg"

    waveform, metrics = _estrai_waveform_e_metriche(raw, f.filename, groq_client=client_groq)
    return jsonify({
        "ok": True,
        "filename": f.filename,
        "audio_url": "/music-lab/audio-stream",
        "waveform": waveform,
        "metrics": metrics,
    })


@app.route("/music-lab/audio-stream", methods=["GET"])
def music_lab_audio_stream():
    with music_lab_lock:
        raw = _last_audio_bytes
        mime = _last_audio_mime
    if not raw:
        return ("Nessun audio caricato", 404)
    return send_file(io.BytesIO(raw), mimetype=mime, as_attachment=False)


@app.route("/music-lab/interpret", methods=["POST"])
def music_lab_interpret():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "profile")
    metrics = data.get("metrics", {})
    notes = str(data.get("notes", "")).strip()

    if mode == "suno_style":
        istruzioni = (
            "Sei un producer e prompt engineer esperto per Suno AI. "
            "Genera un prompt Suno Style in INGLESE, tecnico, concreto e privo di fronzoli, rigorosamente entro 1000 caratteri. "
            "REGOLE OBBLIGATORIE:\n"
            "1. Suno da' massimo peso alle prime parole: inizia SUBITO con il sottogenere specifico "
            "(es. Memphis trap, West Coast trap, G-funk trap, UK drill, NY drill, dark crunk, industrial trap, boom bap), "
            "seguito subito dalla tonalita' (es. D minor) e dal BPM esatto dalle metriche.\n"
            "2. Specifica poi strumentazione e sound design reali del sottogenere (es. distorted 808s, cowbell, eerie horror synths, "
            "G-funk lead whistle, West Coast bounce bass, rapid triplet hi-hats, gritty lo-fi tape saturation, punchy snare).\n"
            "3. Specifica carattere vocale/flow (es. aggressive double-time chopper rap, raw Memphis vocal cadence, laid-back West Coast delivery) "
            "e mood coerente con la tonalita' (niente contraddizioni tipo 'happy' su tonalita' minore scura).\n"
            "4. Restituisci SOLO il testo del prompt pronto da incollare su Suno, senza virgolette, titoli o spiegazioni."
        )
    elif mode == "lyrics":
        istruzioni = (
            "Sei un paroliere esperto di rap, trap e produzione musicale per Suno AI. "
            "Scrivi il testo completo (Lyrics) entro 5000 caratteri, coerente con sottogenere, BPM, tonalita', "
            "trascrizione vocale (se presente) e note dell'utente. "
            "Usa tag strutturali in inglese tra parentesi quadre con indicazioni dinamiche brevi, ad esempio: "
            "[Intro - dark atmospheric buildup], [Verse 1 - aggressive fast flow], [Chorus - heavy 808 drop], "
            "[Verse 2 - double-time chopper cadence], [Bridge - stripped back bass], [Outro]. "
            "Restituisci SOLO il testo con i tag, senza commenti introduttivi o finali."
        )
    else:
        istruzioni = (
            "Sei un A&R e sound analyst esperto in hip-hop, trap e musica elettronica/urban. "
            "Analizza le metriche audio (BPM, tonalita', spettro sub/mid/high, segmenti energetici), l'eventuale trascrizione e le note. "
            "Non dare risposte generiche: identifica il sottogenere piu' specifico e credibile (es. Memphis trap, West Coast trap, "
            "hardcore drill, dark crunk, industrial rap, boom bap, phonk, ecc.). "
            "Restituisci ESCLUSIVAMENTE un oggetto JSON valido (senza markdown ```json) con esattamente queste 5 chiavi in italiano: "
            "genre (genere principale + sottogenere specifico), "
            "subgenre (sottogenere esatto e scena di riferimento, es. Memphis trap / West Coast trap), "
            "mood (atmosfera, tonalita' e livello di aggressivita'/energia), "
            "atmosphere_and_mix (dettaglio tecnico su 808/sub, percussioni, timbro e carattere vocale), "
            "summary (sintesi chiara in 2-3 frasi del carattere della traccia e consigli pratici per Suno)."
        )

    messaggi = [
        {"role": "system", "content": istruzioni},
        {"role": "user", "content": f"Metriche audio: {json.dumps(metrics, ensure_ascii=False)}\nNote utente: {notes}"}
    ]

    try:
        testo = chiedi_llm(client_groq, messaggi, [MODELLO_CHAT], max_tokens=2000, temperature=0.65)
        if not testo:
            return jsonify({"error": "Risposta vuota dal modello Groq."}), 500
        testo = testo.strip()
        if mode == "profile":
            # Rimuove eventuali fence ```json ... ``` se il modello li aggiunge
            testo = re.sub(r"^```(?:json)?\s*|\s*```$", "", testo).strip()
        elif mode == "suno_style":
            testo = testo[:1000]
        elif mode == "lyrics":
            testo = testo[:5000]
        return jsonify({"ok": True, "result": testo})
    except Exception as e:
        return jsonify({"error": f"Errore chiamata Groq: {e}"}), 500


@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route("/api/status")
def get_status():
    with state_lock:
        stato = dict(system_state)
    return jsonify(stato)


@app.route('/api/stream')
def sse_stream():
    def event_stream():
        last_state_str = None
        tick = 0
        while True:
            with state_lock:
                current_state_str = json.dumps(system_state)

            if current_state_str != last_state_str:
                last_state_str = current_state_str
                yield f"event: status\ndata: {current_state_str}\n\n"

            if tick % 3 == 0 and psutil is not None:
                mem = psutil.virtual_memory()
                telemetry = {
                    "ok": True,
                    "cpu": psutil.cpu_percent(None),
                    "ram_used": mem.used / 1024 ** 3,
                    "ram_total": mem.total / 1024 ** 3,
                    "ram_percent": mem.percent
                }
                yield f"event: telemetry\ndata: {json.dumps(telemetry)}\n\n"

            tick += 1
            time.sleep(0.5)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@app.route('/api/presence', methods=['POST'])
def handle_presence():
    saluto = "Bentornato alla postazione, signor Marcolino. Tutti i sistemi sono operativi."
    aggiorna_stato(last_reply=saluto, mode="speaking", message="Presenza rilevata...")
    return jsonify({"ok": True, "text": saluto})


@app.route("/api/welcome")
def get_welcome():
    messaggio_avvio = genera_saluto_avvio()
    aggiorna_stato(last_reply=messaggio_avvio, mode="speaking", message="Saluto iniziale...")
    return jsonify({"ok": True, "text": messaggio_avvio})


@app.route("/api/listen", methods=["POST"])
def post_listen():
    with state_lock:
        if system_state["busy"]:
            return jsonify({"ok": False, "message": "Occupato."}), 409
        system_state["busy"] = True
        system_state["mode"] = "listening"
        system_state["message"] = "Ascolto..."

    threading.Thread(target=worker_ascolto_e_risposta, daemon=True).start()
    return jsonify({"ok": True})


CARTELLA_PROGETTI = os.path.join(BASE_DIR, "progetti_machete")


@app.route("/api/codice/esegui", methods=["POST"])
def post_codice_esegui():
    """Salva lo script in progetti_machete e lo esegue (massimo 20 secondi). Parte solo se premi ESEGUI."""
    import time as _time
    dati = request.get_json(silent=True) or {}
    codice = str(dati.get("code", ""))
    if not codice.strip() or len(codice) > 30000:
        return jsonify({"ok": False, "message": "Codice vuoto o troppo lungo."}), 400
    os.makedirs(CARTELLA_PROGETTI, exist_ok=True)
    nome = re.sub(r"[^A-Za-z0-9_-]", "_", str(dati.get("name", "script")))[:30] or "script"
    percorso = os.path.join(CARTELLA_PROGETTI, f"{nome}_{_time.strftime('%Y%m%d_%H%M%S')}_{int(_time.time() * 1000) % 1000:03d}.py")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(codice)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    def _testo(x):
        if x is None:
            return ""
        return x if isinstance(x, str) else x.decode("utf-8", "replace")

    try:
        r = subprocess.run(
            [sys.executable, percorso], cwd=CARTELLA_PROGETTI, env=env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        esito = {"ok": True, "returncode": r.returncode, "stdout": r.stdout[-6000:],
                 "stderr": r.stderr[-6000:], "timeout": False}
    except subprocess.TimeoutExpired as e:
        esito = {"ok": True, "returncode": None, "stdout": _testo(e.stdout)[-6000:],
                 "stderr": _testo(e.stderr)[-6000:], "timeout": True}
    except Exception as e:
        esito = {"ok": False, "message": str(e)}
    esito["file"] = os.path.relpath(percorso, BASE_DIR)
    return jsonify(esito)


@app.route("/api/codice/correggi", methods=["POST"])
def post_codice_correggi():
    """Rimanda all'IA il codice e l'errore ottenuto, e restituisce la versione corretta."""
    dati = request.get_json(silent=True) or {}
    codice = str(dati.get("code", ""))[:30000]
    errore = str(dati.get("error", ""))[:4000]
    if not codice.strip():
        return jsonify({"ok": False, "message": "Codice vuoto."}), 400
    richiesta = ("Questo codice Python da' un problema.\n\nCODICE:\n```python\n" + codice + "\n```\n\n"
                 "RISULTATO O ERRORE:\n" + (errore or "(nessun errore, ma non fa quello che volevo)") +
                 "\n\nCorreggilo e restituisci il codice completo.")
    try:
        risposta = chiedi_llm(client_groq, [SISTEMA_CODICE, {"role": "user", "content": richiesta}],
                              [MODELLO_CHAT], max_tokens=2500, temperature=0.2)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500
    registra_messaggio("user", "Correggi il codice. Errore: " + errore[:300])
    registra_messaggio("assistant", risposta)
    return jsonify({"ok": True, "reply": risposta})


@app.route("/api/codice/cartella", methods=["POST"])
def post_codice_cartella():
    os.makedirs(CARTELLA_PROGETTI, exist_ok=True)
    try:
        os.startfile(CARTELLA_PROGETTI)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/ask", methods=["POST"])
def post_ask():
    """Messaggio scritto a mano: stessa elaborazione della voce, ma restituisce subito il testo."""
    dati = request.get_json(silent=True) or {}
    testo = str(dati.get("text", "")).strip()[:8000]
    if not testo:
        return jsonify({"ok": False, "message": "Testo vuoto."}), 400
    with state_lock:
        if system_state["busy"]:
            return jsonify({"ok": False, "message": "Occupato."}), 409
        system_state["busy"] = True
        system_state["mode"] = "thinking"
        system_state["message"] = "Elaborazione testo..."
    try:
        risposta = elabora_richiesta(testo)
    except Exception as e:
        aggiorna_stato(mode="error", message="Errore.", last_reply=f"Errore: {e}")
        risposta = f"Errore: {e}"
    finally:
        with state_lock:
            system_state["busy"] = False
            if system_state["mode"] != "error":
                system_state["mode"] = "idle"
                system_state["message"] = "Pronto"
    return jsonify({"ok": True, "reply": risposta})


@app.route("/api/stop", methods=["POST"])
def post_stop():
    with state_lock:
        system_state["busy"] = False
        system_state["mode"] = "idle"
        system_state["message"] = "Pronto"
    return jsonify({"ok": True})


@app.route('/api/vision', methods=['POST'])
def vision():
    dati = request.json or {}
    base64_image = dati.get('image')
    if not base64_image:
        return jsonify({"error": "Nessuna immagine ricevuta"}), 400

    descrizione = analizza_immagine(client_groq, base64_image)
    return jsonify({"description": descrizione})


@app.route('/api/screen_vision', methods=['POST'])
def screen_vision():
    dati = request.json or {}
    prompt = dati.get('prompt', 'Cosa vedi sullo schermo?')
    aggiorna_stato(mode="thinking", message="Analisi monitor...")
    descrizione = analizza_schermo(client_groq, prompt)
    aggiorna_stato(last_reply=descrizione, mode="speaking", message="Parlo...")
    return jsonify({"description": descrizione})


async def generate_audio_bytes(text):
    communicate = edge_tts.Communicate(text, VOICE, pitch="-2Hz", rate="+0%")
    mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]
    return mp3_data


@app.route('/api/tts', methods=['POST'])
def generate_tts():
    data = request.json or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "Vuoto"}), 400
    try:
        mp3_bytes = asyncio.run(generate_audio_bytes(text))
        return send_file(io.BytesIO(mp3_bytes), mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/system')
def get_system():
    if psutil is None:
        return jsonify({"ok": False})
    mem = psutil.virtual_memory()
    return jsonify({
        "ok": True,
        "cpu": psutil.cpu_percent(None),
        "ram_used": mem.used / 1024 ** 3,
        "ram_total": mem.total / 1024 ** 3,
        "ram_percent": mem.percent
    })


@app.route('/api/weather')
def get_weather():
    try:
        res = requests.get(f"https://wttr.in/{CITTA_METEO},Italy?format=j1&lang=it", timeout=4)
        if res.status_code == 200:
            current = res.json()['current_condition'][0]
            desc = (current.get('lang_it') or [{}])[0].get('value') or current['weatherDesc'][0]['value']
            return jsonify({"ok": True, "city": CITTA_METEO, "temp": current['temp_C'], "desc": desc})
    except Exception:
        pass
    return jsonify({"ok": False, "city": CITTA_METEO, "temp": "--", "desc": "N/D"})


if __name__ == "__main__":
    print("[MACHETE OS] Avvio server tattico con RICERCA LIVE + MUSIC LAB su http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)