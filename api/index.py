import os
import json
import sqlite3
from flask import Flask, request, jsonify, redirect, session
from flask_cors import CORS
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.oauth2.credentials import Credentials

app = Flask(__name__)
CORS(app)

# CHIAVE DI SICUREZZA FONDAMENTALE: Senza questa Google fa crashare Flask su Vercel!
app.secret_key = os.environ.get("VERCEL_SECRET_KEY", "chiave_super_segreta_per_i_cookie_902")

FILE_DB = "/tmp/database_bot.db"

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

# ==========================================
# ROTTE API PROTETTE
# ==========================================

@app.route('/api/login')
def login():
    stringa_segreti = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not stringa_segreti:
        return jsonify({"status": "error", "message": "Configurazione server mancante (YOUTUBE_CLIENT_SECRET)"}), 500
        
    segreti_client = json.loads(stringa_segreti)
    
    protocollo = "https://" if "localhost" not in request.host else "http://"
    redirect_uri = f"{protocollo}{request.host}/api/oauth2callback"
    
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        segreti_client,
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        redirect_uri=redirect_uri
    )
    
    # Salviamo lo stato di sicurezza per evitare attacchi CSRF
    authorization_url, state = flow.authorization_url(prompt='select_account')
    session['oauth_state'] = state
    
    return redirect(authorization_url)

@app.route('/api/oauth2callback')
def oauth2callback():
    stringa_segreti = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not stringa_segreti:
        return "Errore di configurazione interno: manca YOUTUBE_CLIENT_SECRET nelle env di Vercel.", 500
        
    segreti_client = json.loads(stringa_segreti)
    protocollo = "https://" if "localhost" not in request.host else "http://"
    redirect_uri = f"{protocollo}{request.host}/api/oauth2callback"
    
    # Forziamo le librerie di Google ad accettare le richieste HTTPS di Vercel
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        segreti_client,
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        redirect_uri=redirect_uri,
        state=session.get('oauth_state')
    )
    
    url_richiesta = request.url
    if "localhost" not in request.host and url_richiesta.startswith("http://"):
        url_richiesta = url_richiesta.replace("http://", "https://", 1)

    try:
        flow.fetch_token(authorization_response=url_richiesta)
        creds = flow.credentials
        
        servizio_utente = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
        risposta_canale = servizio_utente.channels().list(mine=True, part="snippet,id").execute()
        
        if risposta_canale.get("items"):
            id_reale = risposta_canale["items"][0]["id"]
            nome_reale = risposta_canale["items"][0]["snippet"]["title"]
            return redirect(f"/?id={id_reale}&nome={nome_reale}")
            
    except Exception as e:
        return f"Crash durante lo scambio del Token con Google. Errore reale: {str(e)}", 500
    
    return "Impossibile identificare il tuo canale YouTube.", 400

@app.route('/api/mie-segnalazioni', methods=['GET'])
def mie_segnalazioni():
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
    return jsonify({"status": "success", "bot_segnalati": risultato})

@app.route('/api/cancella-segnalazione', methods=['POST'])
def cancella_segnalazione():
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
