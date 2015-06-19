import os, md5, re, time, json, urllib2
from flask import Flask, render_template, send_from_directory, request, jsonify, g

app = Flask(__name__)
app.debug = True
app.config['PROPAGATE_EXCEPTIONS'] = True

@app.route('/')
def show_index():
    return render_template('index.html')

if __name__=="__main__":
    app.run(host='localhost', port=6868, debug=True)

