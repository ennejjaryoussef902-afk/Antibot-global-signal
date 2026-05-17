import os
import json
import sqlite3
from flask import Flask, request, jsonify, redirect
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.oauth2.credentials import Credentials

app = Flask(__name__)

# Il database temporaneo su Vercel (sola lettura per il file system, ma perfetto per l'esecuzione)
FILE_DB = "/tmp/database_bot.db"

# =======================================================
# LOGICA VARIABILI D'AMBIENTE PROTETTE DI VERCEL
# =======================================================
def inizializza_client_youtube():
    """Carica i segreti direttamente dalle Environment Variables di Vercel."""
    try:
        # Prende la stringa JSON memorizzata su Vercel nelle impostazioni
        token_segreto = os.environ.get("YOUTUBE_TOKEN")
        if not token_segreto:
            return None
        
        info_credenziali = json.loads(token_segreto)
        creds = Credentials.from_authorized_user_info(info_credenziali)
        return googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[-] Errore configurazione interna API: {e}")
        return None

def inizializza_db_locale():
    connessione = sqlite3.connect(FILE_DB)
    cursore = connessione.cursor()
    cursore.execute('''
        CREATE TABLE IF NOT EXISTS voti_segnalazioni (
            id_utente_segnalatore TEXT,
            nome_utente_segnalatore TEXT,
            id_canale_bot_cattivo TEXT,
            nome_bot_cattivo TEXT,
            PRIMARY KEY (id_utente_segnalatore, id_canale_bot_cattivo)
        )
    ''')
    connessione.commit()
    connessione.close()

# =======================================================
# ROTTE API (CHIAMATE DIRETTAMENTE DAL FRONTEND)
# =======================================================

@app.route('/api/login')
def login():
    """Genera il flusso di login di Google basandosi sul client_secret nascosto su Vercel."""
    segreti_client = json.loads(os.environ.get("YOUTUBE_CLIENT_SECRET"))
    
    # Configura il redirect automatico usando l'host corrente fornito da Vercel
    protocollo = "https://" if "localhost" not in request.host else "http://"
    redirect_uri = f"{protocollo}{request.host}/api/oauth2callback"
    
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        segreti_client,
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        redirect_uri=redirect_uri
    )
    authorization_url, _ = flow.authorization_url(prompt='select_account')
    return redirect(authorization_url)

@app.route('/api/oauth2callback')
def oauth2callback():
    """Riceve l'autenticazione dall'utente e rimanda alla home con i suoi dati veri."""
    segreti_client = json.loads(os.environ.get("YOUTUBE_CLIENT_SECRET"))
    protocollo = "https://" if "localhost" not in request.host else "http://"
    redirect_uri = f"{protocollo}{request.host}/api/oauth2callback"
    
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        segreti_client,
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        redirect_uri=redirect_uri
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    
    # Interroga Google per sapere chi si è appena loggato
    servizio_utente = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    risposta_canale = servizio_utente.channels().list(mine=True, part="snippet,id").execute()
    
    if risposta_canale.get("items"):
        id_reale = risposta_canale["items"][0]["id"]
        nome_reale = risposta_canale["items"][0]["snippet"]["title"]
        
        # Rimanda l'utente alla pagina principale passando i dati in modo pulito
        return redirect(f"/?id={id_reale}&nome={nome_reale}")
    
    return "Errore identificazione profilo YouTube.", 400

@app.route('/api/mie-segnalazioni', methods=['GET'])
def mie_segnalazioni():
    """Mostra esclusivamente i bot segnalati dall'utente loggato."""
    inizializza_db_locale()
    id_utente = request.args.get("id")
    if not id_utente:
        return jsonify({"status": "error", "message": "Non autorizzato"}), 401
        
    connessione = sqlite3.connect(FILE_DB)
    cursore = connessione.cursor()
    cursore.execute('SELECT nome_bot_cattivo, id_canale_bot_cattivo FROM voti_segnalazioni WHERE id_utente_segnalatore = ?', (id_utente,))
    righe = cursore.fetchall()
    connessione.close()
    
    risultato = [{"nome_bot": r[0], "id_bot": r[1]} for r in righe]
    return jsonify({"status": "success", "bot_segnalati": resultado})

@app.route('/api/cancella-segnalazione', methods=['POST'])
def cancella_segnalazione():
    """Rimuove in modo mirato il voto dell'utente loggato senza toccare gli altri."""
    inizializza_db_locale()
    dati = request.get_json()
    id_utente = dati.get("id_utente")
    id_bot = dati.get("id_bot")
    
    connessione = sqlite3.connect(FILE_DB)
    cursore = connessione.cursor()
    cursore.execute('DELETE FROM voti_segnalazioni WHERE id_utente_segnalatore = ? AND id_canale_bot_cattivo = ?', (id_utente, id_bot))
    connessione.commit()
    connessione.close()
    
    return jsonify({"status": "success", "message": "Voto revocato correttamente."})
