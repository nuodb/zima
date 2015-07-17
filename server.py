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
    #consider NamedTuple for job_desc
    properties = "{ssd=1}/host=%s+{ssd=0}/host=%s" % (job_desc['SM'], job_desc['TE'])
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append(properties)
    cmd.append("-d")
    cmd.append("/home/build")
    cmd.append("/home/acharis/bin/run-evil.sh {}".format(build_url))
    #app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}


#in bamboo:
#curl "base/zima/enqueue_micro?branch=${bamboo.repository.branch.name}&buildid=${bamboo.buildResultKey}"
#the buildResultKey for the benchmark run (which hasn't been created yet) is what's used for making
#the link in core-view back to the benchmark run in bamboo...to get to the log+junit results
#so for now, make that optional, and solve that problem a different way later
def submit_micro(branch, build_id):
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append("/host=1")
    cmd.append("-d")
    cmd.append("/home/build")
    cmd.append("/home/build/arewefastyet/kickoff-micro")
    cmd.append("-i")
    cmd.append("5")
    cmd.append(build_id)
    cmd.append("micro")
    cmd.append(branch)
    cmd.append("MASTER")#can't make it optional in kickoff, so hardcode since we don't gather-cores for micro anyway
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

def submit(suite, branch, build_url):
    with open(SUITE_FILE, 'r') as fd:
        config_data = json.load(fd)
    result = {}
    for job_desc in config_data[suite]:
        app.logger.info("calling submit_single with job_desc: {}".format(job_desc))
        result[job_desc['name']] = submit_single(job_desc, branch, build_url)
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

@app.route('/enqueue_micro')
def enqueue_micro():
    branch = request.args.get('branch', 'master', type=str)
    build_id = request.args.get('buildid', type=str)
    result = submit_micro(branch, build_id)
    return jsonify(resp=result)

# @app.route('/enqueue_single', methods=['POST'])
# def enqueue_single():
#     file = request.files['file']
#     buildID = request.form.get("branch", None)
#     email = request.form.get("email", None)

@app.route('/job_status')
def job_status():
    return jsonify("ALEX: not yet implemented")

@app.route('/queue_status')
def queue_status():
    return jsonify("ALEX: not yet implemented")

@app.route('/node_status')
def node_status():
    return jsonify("ALEX: not yet implemented")

@app.route('/build_status')
def build_status():
    #synthetic based on 'project' in the OAR job
    return jsonify("ALEX: not yet implemented")

@app.route('/junit_collect', methods=['POST'])
def junit_collect():
    #recv a junit file for a particular test
    return jsonify("ALEX: not yet implemented")

@app.route('/junit_serve')
def junit_serve():
    #prompted by bamboo, yield the junit file(s) requested
    return jsonify("ALEX: not yet implemented")

@app.route('/')
def show_index():
    return render_template('index.html')

if __name__=="__main__":
    handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(host='localhost', port=6868, debug=True)

