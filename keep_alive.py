from flask import Flask
from threading import Thread
import logging

# Stop flask from spamming logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask('')

@app.route('/')
def home():
    return "<h1>Bot Zinda Hai! (System Online)</h1>"

def run():
    # Use port 8080 or defaults to 5000 if 8080 is busy
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
