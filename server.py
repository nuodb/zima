import os, md5, re, time, json, urllib2
from flask import Flask, render_template, send_from_directory, request, jsonify, g
from artifact_link_finder import get_link, NoSuchBuildException

app = Flask(__name__)
app.debug = True
app.config['PROPAGATE_EXCEPTIONS'] = True


@app.route('/enqueue')
def enqueue():
    branch = request.args.get('branch', 'master', type=str)
    build_result_key = request.args.get('buildResultKey', type=str)
    try: 
        build_url = get_link(build_result_key)
    except NoSuchBuildException:
        return jsonify(error="no such build")
    #run oarsub lots of times...
    return jsonify(resp=build_url)

@app.route('/')
def show_index():
    return render_template('index.html')

if __name__=="__main__":
    app.run(host='localhost', port=6868, debug=True)

