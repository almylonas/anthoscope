import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_cors import CORS

# Initialize Flask pointing to the landing subfolder
app = Flask(__name__, static_folder='static/landing', static_url_path='')
CORS(app)

# Use absolute paths to prevent Vercel environment confusion
BASE_DIR = os.getcwd()

def get_db_connection():
    """Returns a new psycopg2 connection using the DATABASE_URL env var."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    return conn


@app.route("/")
def serve_landing():
    """Serves index.html from static/landing/"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/assets/<path:path>')
def serve_assets(path):
    """Serves JS/CSS from static/landing/assets/"""
    return send_from_directory(os.path.join(app.static_folder, 'assets'), path)

@app.route("/map")
def serve_map():
    """Serves map app using the template in /templates/"""
    return render_template("index.html")

@app.route('/static/<path:filename>')
def serve_icons(filename):
    """Serves icons sitting directly in /static/ (cursor, mini, point)"""
    return send_from_directory(os.path.join(BASE_DIR, 'static'), filename)

# --- API ROUTES ---

@app.route("/api/reviews", methods=['POST'])
def create_review():
    """Create a new allergy review in the Neon database."""
    try:
        data = request.json
        conn = get_db_connection()
        cur = conn.cursor()

        # Only insert the three fields the frontend actually sends.
        # pollen_type and severity are not sent by the map form, so
        # they are omitted here to avoid NOT-NULL constraint errors.
        cur.execute("""
            INSERT INTO allergy_reviews
                (center_lat, center_lng, radius_km, review_text)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            data['centerLat'],
            data['centerLng'],
            data['radiusKm'],
            data.get('reviewText', '')
        ))

        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'success': True,
            'id': result[0],
            'createdAt': result[1].isoformat()
        }), 201

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/reviews", methods=['GET'])
def get_reviews():
    """Fetch reviews from the Neon database."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT id, center_lat, center_lng, radius_km, pollen_type,
                   severity, symptoms, review_text, created_at
            FROM allergy_reviews
            ORDER BY created_at DESC
            LIMIT 100
        """)

        reviews = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify({'success': True, 'reviews': [dict(r) for r in reviews]}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Note: app.run() is omitted. Vercel handles execution via vercel.json.