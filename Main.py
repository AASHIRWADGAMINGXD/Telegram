from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I am alive! Dattebayo!"

def run():
    # Run on port 8080 or port provided by Render
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
