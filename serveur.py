# serveur.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import datetime
import re

app = Flask(__name__)
CORS(app)

DATA_FILE = 'central_data.json'
PARISH_CERTS_FILE = 'parish_certs.json'  # certificats (simples tokens) par code paroisse

# --- Utils ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'marriages': []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_parish_certs():
    if os.path.exists(PARISH_CERTS_FILE):
        with open(PARISH_CERTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    # exemple de token pour paroisse "ST" (à remplacer / ajouter)
    sample = {"ST": "secret-token-st"}
    with open(PARISH_CERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    return sample

def parish_code_from_name(name):
    # Prendre 2 lettres significatives (lettres alpha). Si moins, compléter avec X.
    letters = ''.join(c for c in name.upper() if c.isalpha())
    if len(letters) >= 2:
        return letters[:2]
    return (letters + "X")[:2]

def next_sequence_for_parish(data, year, parish_code):
    # compte déjà existants pour l'année+paroisse
    count = 0
    prefix = f"{year}/{parish_code}/"
    for m in data['marriages']:
        if m.get('num_acte_central','').startswith(prefix):
            count += 1
    return count + 1

def generate_central_number(parish_name):
    now = datetime.datetime.utcnow()
    year = now.year
    pc = parish_code_from_name(parish_name)
    seq = next_sequence_for_parish(load_data(), year, pc)
    return f"{year}/{pc}/{seq:04d}"

def validate_date_iso(s):
    try:
        datetime.datetime.fromisoformat(s)
        return True
    except:
        return False

# --- Chargement initial ---
data = load_data()
parish_certs = load_parish_certs()

# --- Routes ---
@app.route('/api/marriages', methods=['GET'])
def list_marriages():
    return jsonify(data['marriages'])

@app.route('/api/transmit', methods=['POST'])
def receive_transmission():
    """
    Endpoint attendu:
    - JSON body avec les champs de l'algorithme (voir plus bas)
    - Header 'X-Parish-Cert' contenant le token de la paroisse
    """
    try:
        payload = request.get_json(force=True)
    except:
        return jsonify({'error': 'JSON invalide'}), 400

    header_token = request.headers.get('X-Parish-Cert', '')
    parish_name = payload.get('Nom_paroisse', '').strip()
    if not parish_name:
        return jsonify({'error': 'Nom_paroisse requis'}), 400

    pc = parish_code_from_name(parish_name)
    expected = parish_certs.get(pc)
    if expected is None:
        return jsonify({'error': f'Paroisse non enregistrée pour code {pc}'}), 401
    if header_token != expected:
        return jsonify({'error': 'Certificat paroissial invalide'}), 401

    # Champs obligatoires
    required = ['Nom_epoux','Nom_epouse','Date_mariage','Lieu_mariage','Nom_paroisse',
                'Officiant','Temoin1','Temoin2','Num_acte_local']
    for r in required:
        if not payload.get(r):
            return jsonify({'error': f'Champ requis manquant: {r}'}), 400

    # vérification date
    date_m = payload.get('Date_mariage')
    if not validate_date_iso(date_m):
        return jsonify({'error': 'Date_mariage doit être en format ISO YYYY-MM-DD'}), 400

    # Générer numéro central
    num_central = generate_central_number(parish_name)

    # Construire l'acte centralisé
    acte = {
        'num_acte_central': num_central,
        'num_acte_local': int(payload.get('Num_acte_local')),
        'Nom_paroisse': parish_name,
        'parish_code': pc,
        'Nom_epoux': payload.get('Nom_epoux'),
        'Nom_epouse': payload.get('Nom_epouse'),
        'Date_mariage': payload.get('Date_mariage'),
        'Lieu_mariage': payload.get('Lieu_mariage'),
        'Officiant': payload.get('Officiant'),
        'Temoin1': payload.get('Temoin1'),
        'Temoin2': payload.get('Temoin2'),
        'statut_transmission': True,
        'Date_transmission': datetime.datetime.utcnow().isoformat()
    }

    # Sauvegarder central
    data['marriages'].append(acte)
    save_data(data)

    # Retour pour mise à jour côté paroisse
    return jsonify({'success': True, 'num_acte_central': num_central, 'Date_transmission': acte['Date_transmission']}), 200

# Endpoint pour administrer (ajouter/modifier tokens) - sécurisé par clé d'admin simple (env)
@app.route('/api/admin/add_parish', methods=['POST'])
def add_parish():
    admin_key = os.environ.get('ADMIN_KEY', 'admin-secret')  # change en prod
    if request.headers.get('X-Admin-Key') != admin_key:
        return jsonify({'error': 'Admin key invalide'}), 401
    payload = request.get_json(force=True)
    name = payload.get('name', '').strip()
    token = payload.get('token', '').strip()
    if not name or not token:
        return jsonify({'error': 'name et token requis'}), 400
    pc = parish_code_from_name(name)
    parish_certs[pc] = token
    with open(PARISH_CERTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(parish_certs, f, ensure_ascii=False, indent=2)
    return jsonify({'success': True, 'code_paroisse': pc}), 200

# simple health
@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
