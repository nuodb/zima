import os, md5, re, time, json, urllib2, subprocess, logging, random, string
from flask import Flask, render_template, send_from_directory, request, jsonify, g
from artifact_link_finder import get_link, NoSuchBuildException
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.debug = True
handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.config['PROPAGATE_EXCEPTIONS'] = True
TEST_DIR = "/usr/local/zima/properties"

def submit_single(test_def_fn, test_def, branch, build_result_key, token):
    job_desc = parse_job_desc(test_def)
    error = check_job_desc(job_desc)
    if error:
        return {'out':'', 'err': error}
    properties = "{ssd=1}/host=%s+{ssd=0}/host=%s" % (job_desc['NUM_SM_HOSTS'], job_desc['NUM_TE_HOSTS'])
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append(properties)
    cmd.append("-d")
    cmd.append("/var/local")
    cmd.append("/home/build/perf/runner {} {} {}".format(test_def_fn, branch, build_result_key))
    #app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

#in bamboo:
#curl "base/zima/enqueue_micro?branch=${bamboo.repository.branch.name}&buildid=${bamboo.buildResultKey}"
#the buildResultKey for the benchmark run (which hasn't been created yet) is what's used for making
#bamboo-link in core-view back to the benchmark run in bamboo...to get to the log+junit results
#so for now, make that optional, and solve that problem a different way later
def submit_micro(branch, build_id):
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append("/host=1,walltime=4:0:0")
    cmd.append("-d")
    cmd.append("/home/build")
    cmd.append("TERM=dumb /home/build/arewefastyet/kickoff-micro -i 5 {} micro {} MASTER".format(build_id, branch))
    #can't make it optional in kickoff, so hardcode since we don't gather-cores for micro anyway
    app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

def submit(suite, branch, build_result_key, token):
    result = {}
    tests = [fn for fn in os.listdir(TEST_DIR) if suite in fn]
    for fn in tests:
        with open(fn, 'r') as fd:
            test_def = fd.read()
        app.logger.info("calling submit_single with job: {}".format(fn))
        result[fn] = submit_single(fn, test_def, branch, build_result_key, token)
    return result

@app.route('/enqueue')
def enqueue():
    suite = request.args.get('suite', '', type=str)
    branch = request.args.get('branch', 'master', type=str)
    build_result_key = request.args.get('buildResultKey', type=str)
    try: #fail fast
        build_url = get_link(build_result_key)
    except NoSuchBuildException:
        return jsonify(error="no such build")
    result = submit(suite, branch, build_result_key, get_token())
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

@app.route('/get_test_def/<filename>')
def get_test_def(filename):
    return send_from_directory(TEST_DIR, filename)

@app.route('/job_status')
def job_status():
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

def get_token():
    candidate = "".join(random.SystemRandom().choice(string.ascii_uppercase) for x in range(12))
    #ALEX: if candidate safe
    return token

def parse_job_desc(test_def):
    def parse_kv(k, _, v):
        return k, int(v)
    return dict([parse_kv(*x.partition("=")) for x in test_def.strip().split('\n')])

def check_job_desc(job_desc):
    if 'DISABLED' in job_desc:
        return 'Test disabled'
    required = ['SCRIPT', 'NUM_TE_HOSTS', 'NUM_SM_HOSTS']
    errstr = "You must specify all of: {}".format(", ".join(required))
    if all(key in job_desc for key in required):
        return None
    else:
        return errstr

if __name__=="__main__":
    handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.run(host='localhost', port=6868, debug=True)

