# main.py - Serveur Flask-SocketIO pour bapteme.orender.com
from flask import Flask, request
from flask_socketio import SocketIO, emit
import sqlite3
import datetime
import re
from threading import Lock

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ton-secret-ultra-fort-ici-123456789'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Verrou pour la base de données
db_lock = Lock()

# Initialisation DB
def init_db():
    with sqlite3.connect('mariages.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS mariages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom_epoux TEXT NOT NULL,
                nom_epouse TEXT NOT NULL,
                date_mariage TEXT NOT NULL,
                lieu_mariage TEXT NOT NULL,
                nom_paroisse TEXT NOT NULL,
                officiant TEXT NOT NULL,
                temoin1 TEXT NOT NULL,
                temoin2 TEXT NOT NULL,
                num_acte_local INTEGER NOT NULL,
                num_acte_central TEXT UNIQUE NOT NULL,
                statut_transmission BOOLEAN DEFAULT 0,
                date_transmission TEXT
            )
        ''')
        conn.commit()

# Générer Num_acte_central : AAAA/PP/XXXX
def generer_num_central(paroisse_code, annee):
    with db_lock:
        with sqlite3.connect('mariages.db') as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM mariages WHERE num_acte_central LIKE ?", (f"{annee}/{paroisse_code}/%",))
            count = c.fetchone()[0] + 1
            return f"{annee}/{paroisse_code}/{count:04d}"

init_db()

# Route de test
@app.route('/')
def index():
    return "Serveur Mariages Catholiques ON - bapteme.orender.com"

# Réception d'un nouvel acte
@socketio.on('enregistrer_mariage')
def handle_enregistrer(data):
    try:
        # Extraction et validation
        required = ['nom_epoux', 'nom_epouse', 'date_mariage', 'lieu_mariage',
                    'nom_paroisse', 'officiant', 'temoin1', 'temoin2', 'num_acte_local', 'code_paroisse']
        
        for field in required:
            if not data.get(field):
                emit('erreur', {'msg': f'Champ manquant : {field}'})
                return

        annee = data['date_mariage'][:4]
        num_central = generer_num_central(data['code_paroisse'].upper()[:2], annee)

        with db_lock:
            conn = sqlite3.connect('mariages.db')
            c = conn.cursor()
            c.execute('''
                INSERT INTO mariages 
                (nom_epoux, nom_epouse, date_mariage, lieu_mariage, nom_paroisse, officiant,
                 temoin1, temoin2, num_acte_local, num_acte_central, statut_transmission)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                data['nom_epoux'][:50], data['nom_epouse'][:50], data['date_mariage'],
                data['lieu_mariage'][:100], data['nom_paroisse'][:60], data['officiant'][:50],
                data['temoin1'][:50], data['temoin2'][:50], int(data['num_acte_local']),
                num_central
            ))
            conn.commit()

        # Diffuser à tous les clients connectés
        socketio.emit('nouveau_mariage', {
            'num_acte_central': num_central,
            'nom_epoux': data['nom_epoux'],
            'nom_epouse': data['nom_epouse'],
            'date_mariage': data['date_mariage']
        })

        emit('succes_enregistrement', {
            'msg': 'Acte enregistré et transmis avec succès !',
            'num_acte_central': num_central
        })

    except Exception as e:
        emit('erreur', {'msg': str(e)})

# Recherche en temps réel
@socketio.on('rechercher_mariage')
def handle_recherche(data):
    nom_epoux = data.get('nom_epoux', '').strip().lower()
    nom_epouse = data.get('nom_epouse', '').strip().lower()

    with sqlite3.connect('mariages.db') as conn:
        c = conn.cursor()
        query = "SELECT nom_epoux, nom_epouse, date_mariage, lieu_mariage, num_acte_central FROM mariages WHERE 1=1"
        params = []
        if nom_epoux:
            query += " AND LOWER(nom_epoux) LIKE ?"
            params.append(f"%{nom_epoux}%")
        if nom_epouse:
            query += " AND LOWER(nom_epouse) LIKE ?"
            params.append(f"%{nom_epouse}%")
        
        c.execute(query, params)
        results = c.fetchall()

        emit('resultats_recherche', {
            'results': [
                {
                    'nom_epoux': r[0],
                    'nom_epouse': r[1],
                    'date_mariage': r[2],
                    'lieu_mariage': r[3],
                    'num_acte_central': r[4]
                } for r in results
            ]
        })

# Liste complète des mariages
@socketio.on('lister_tout')
def handle_lister():
    with sqlite3.connect('mariages.db') as conn:
        c = conn.cursor()
        c.execute("SELECT nom_epoux, nom_epouse, date_mariage, num_acte_central, statut_transmission FROM mariages ORDER BY date_mariage DESC")
        rows = c.fetchall()
        emit('liste_complete', {
            'mariages': [
                {
                    'nom_epoux': r[0],
                    'nom_epouse': r[1],
                    'date_mariage': r[2],
                    'num_acte_central': r[3],
                    'transmis': 'Oui' if r[4] else 'En attente'
                } for r in rows
            ]
        })

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
