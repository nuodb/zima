import os, md5, re, time, json, urllib2, subprocess, logging
from flask import Flask, render_template, send_from_directory, request, jsonify, g
from artifact_link_finder import get_link, NoSuchBuildException
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.debug = True
handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.config['PROPAGATE_EXCEPTIONS'] = True
SUITE_FILE = "suites.json"

def submit_single(job_desc, branch, build_url):
    properties = "{network_address='p81'}"
    cmd = ["oarsub", "-l", properties, "-d", "/home/build", "/home/acharis/bin/test.sh {} {} {}".format(job_desc, branch, build_url)]
    #app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

def submit(suite, branch, build_url):
    with open(SUITE_FILE, 'r') as fd:
        config_data = json.load(fd)
    result = {}
    for job_desc in config_data[suite]:
        app.logger.info("calling submit_single with job_desc: {}".format(job_desc))
        result[job_desc] = submit_single(job_desc, branch, build_url)
    return result

@app.route('/enqueue')
def enqueue():
    app.logger.info("got request")
    suite = request.args.get('suite', 'all', type=str)
    branch = request.args.get('branch', 'master', type=str)
    build_result_key = request.args.get('buildResultKey', type=str)
    try: 
        build_url = get_link(build_result_key)
    except NoSuchBuildException:
        return jsonify(error="no such build")
    #run oarsub lots of times...
    result = submit(suite, branch, build_url)
    return jsonify(resp=result)

@app.route('/')
def show_index():
    return render_template('index.html')

if __name__=="__main__":
    handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(host='localhost', port=6868, debug=True)

