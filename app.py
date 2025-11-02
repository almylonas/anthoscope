from flask import Flask, render_template
import os

app = Flask(__name__)

# Load Google API key from environment variable (recommended)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "key")

@app.route("/")
def index():
    return render_template("index.html", google_api_key=GOOGLE_API_KEY)

if __name__ == "__main__":
    # Run the Flask app on localhost:5000
    app.run(debug=True)

