import os, md5, re, time, json, urllib, urllib2, subprocess, logging, random, string
from flask import Flask, render_template, send_from_directory, request, jsonify, g
from artifact_link_finder import get_link, NoSuchBuildException
from logging.handlers import RotatingFileHandler
from threading import Lock
from distutils.version import LooseVersion
from collections import defaultdict
import jinja2

app = Flask(__name__)
app.debug = True
handler = RotatingFileHandler('/tmp/zima.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.config['PROPAGATE_EXCEPTIONS'] = True
TEST_DIR = "/usr/local/zima/properties"
#TEST_DIR = "/usr/local/zima/test-properties"
RESULT_DIR = "/usr/local/zima/results"
template_loader = jinja2.ChoiceLoader([app.jinja_loader, jinja2.FileSystemLoader(RESULT_DIR)])
app.jinja_loader = template_loader
token_lock = Lock()
TOKEN_FILE = "/usr/local/zima/tokens"
BAMBOO_URL = "http://tools/bamboo/rest/api/latest/queue/MASTER-MBRC.json?executeAllStages"
CORE_VIEW_URL = "http://base/cores/repoint?parent={}&mbrc={}&token={}"

def submit_single(test_def_fn, test_def, parent_build_id, token):
    job_desc = parse_job_desc(test_def)
    error = check_job_desc(job_desc)
    if error:
        return {'out':'', 'err': error}
    #ALEX: this should take switch into account
    if job_desc['NUM_SM_HOSTS'] == '0':
        properties = "/host=%s" % (job_desc['NUM_TE_HOSTS'])
    else:
        properties = "{ssd=1}/host=%s+/host=%s" % (job_desc['NUM_SM_HOSTS'], job_desc['NUM_TE_HOSTS'])
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append(properties)
    cmd.append("--project")
    cmd.append(token)
    cmd.append("-d")
    cmd.append("/var/local")
    cmd.append("/home/build/perf/runner {} {} {}".format(test_def_fn, parent_build_id, token))
    #app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    cmd.append("/var/local")
    cmd.append("TERM=dumb /home/build/arewefastyet/kickoff-micro -i 5 {} micro {} MASTER".format(build_id, branch))
    #can't make it optional in kickoff, so hardcode since we don't gather-cores for micro anyway
    app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

def submit(suite, parent_build_id, token):
    result = {}
    tests = [fn for fn in os.listdir(TEST_DIR) if suite in fn]
    for fn in tests:
        with open(os.path.join(TEST_DIR,fn), 'r') as fd:
            test_def = fd.read()
        app.logger.info("calling submit_single with job: {}".format(fn))
        result[fn] = submit_single(fn, test_def, parent_build_id, token)
    return result

@app.route('/enqueue')
def enqueue():
    suite = request.args.get('suite', '', type=str)#optional
    branch = request.args.get('branch', 'master', type=str)
    parent_build_id = request.args.get('buildid', type=str)#bamboo id for NPB, etc
    try: #fail fast
        build_url = get_link(parent_build_id)
    except NoSuchBuildException:
        return ("ERROR: no such build", 404)
    result = submit(suite, parent_build_id, get_result_dir(parent_build_id, branch))
    return json.dumps(result)

@app.route('/ross')
def enqueue_ross():
    branch = 'ross_consistency'
    parent_build_id = 'ross_consistency'
    result = submit_ross('', parent_build_id, get_result_dir(parent_build_id, branch))
    return json.dumps(result)

def submit_ross(suite, parent_build_id, token):
    result = {}
    tests = [fn for fn in os.listdir(TEST_DIR) if suite in fn]
    for fn in tests:
        with open(os.path.join(TEST_DIR,fn), 'r') as fd:
            test_def = fd.read()
        result[fn] = submit_single_ross(fn, test_def, parent_build_id, token)
    return result

def submit_single_ross(test_def_fn, test_def, parent_build_id, token):
    job_desc = parse_job_desc(test_def)
    error = check_job_desc(job_desc)
    if error:
        return {'out':'', 'err': error}
    #ALEX: this should take switch into account
    if job_desc['NUM_SM_HOSTS'] == '0':
        properties = "/host=%s" % (job_desc['NUM_TE_HOSTS'])
    else:
        properties = "{ssd=1}/host=%s+/host=%s" % (job_desc['NUM_SM_HOSTS'], job_desc['NUM_TE_HOSTS'])
    cmd = ["oarsub"]
    cmd.append("-l")
    cmd.append(properties)
    cmd.append("--project")
    cmd.append(token)
    cmd.append("-d")
    cmd.append("/var/local")
    cmd.append("-q")
    cmd.append("hipri")
    cmd.append("/home/build/perf/runner-ross {} {} {}".format(test_def_fn, parent_build_id, token))
    #app.logger.info("command: {}".format(" ".join(cmd)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    return {'out':out, 'err':err}

@app.route('/enqueue_micro')
def enqueue_micro():
    branch = request.args.get('branch', 'master', type=str)
    build_id = request.args.get('buildid', type=str)
    result = submit_micro(branch, build_id)
    return json.dumps(result)

@app.route('/enqueue_single_test/<filename>')
def enqueue_single_test(filename):
    branch = request.args.get('branch', 'master', type=str)
    parent_build_id = request.args.get('buildid', type=str)#bamboo id for NPB, etc
    try: #fail fast
        build_url = get_link(parent_build_id)
    except NoSuchBuildException:
        return ("ERROR: no such build", 404)
    try:
        with open(os.path.join(TEST_DIR,filename), 'r') as fd:
            test_def = fd.read()
    except:
        return ("ERROR: test description file not found", 404)
    app.logger.info("calling submit_single with job: {}".format(filename))
    result = submit_single(filename, test_def, parent_build_id, get_result_dir(parent_build_id, branch))
    return json.dumps(result)

#@app.route('/enqueue_single_desc', methods=['POST'])
#def enqueue_single():
#    file = request.files['file']
#    buildID = request.form.get("branch", None)
#    email = request.form.get("email", None)

@app.route('/cancel_runnable/<token>')
def cancel_runnable(token):
    p = subprocess.Popen(["oardel", "--sql", "project = '{}' AND state in ('Waiting')".format(token)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    return json.dumps({'out':out, 'err':err})
#cancel the running ones too? nope ... that's halt
#never cancel jobs that are already done
#when to deactivate the token? at next kick
#still says REGISTERED even though it's just fragging the waiting ones

@app.route('/halt_runnable/<token>')
def halt_runnable(token):
    p = subprocess.Popen(["oardel", "--sql", "project = '{}' AND state not in ('Terminated', 'Error')".format(token)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    return json.dumps({'out':out, 'err':err})

# automated in /etc/cron.hourly/zima-kick
@app.route('/kick')
def kick():
    tokens = get_active_tokens()
    for tok in tokens:
        if oar_complete(tok):
            parent_build_id, branch = deactivate_token(tok)
            if short_circuit(tok):
                app.logger.info(tok+' was noop')
                return ('',200)
            submit_results(tok)
            mbrc_id = start_bamboo_job(tok, parent_build_id, branch)#ALEX: this can fail: try/except
            core_view_repoint(parent_build_id, mbrc_id, tok)
            app.logger.info(tok)#only process one token at a time
            return ('', 200)
    app.logger.info("none complete")
    return ('', 200)

def short_circuit(token):
    return len(os.listdir(os.path.join(RESULT_DIR, token))) == 0

def submit_results(token):#init awfy, go through files and send results, finalize awfy
    pass #not implemented yet...

def core_view_repoint(parent_build_id, mbrc_id, token):
    fd = urllib2.urlopen(CORE_VIEW_URL.format(parent_build_id, mbrc_id, token))
    resp = fd.read()
    if resp:
        app.logger.warn("core_view_repoint: {}".format(resp))

def get_active_tokens():
    with token_lock:
        try:
            with open(TOKEN_FILE, 'r') as fd:
                return json.load(fd)
        except:
            return {}

def oar_complete(tok):
    p = subprocess.Popen(["oarstat", "--sql", "project = '{}' AND state not in ('Terminated', 'Error')".format(tok)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p.wait()
    for line in iter(p.stdout.readline, ''):
        return False
    return True

def deactivate_token(tok):
    with token_lock:
        try:
            with open(TOKEN_FILE, 'r+') as fd:
                tokens = json.load(fd)
                parent_build_id, branch = tokens.pop(tok)
                fd.seek(0)
                fd.truncate()
                json.dump(tokens, fd)
                return parent_build_id, branch
        except:
            app.logger.warn("deactivate_token: open/loads/remove/seek/dump failed")#ALEX: don't swallow

def activate_token(tok, parent_build_id, branch):
    app.logger.info("activate token: {} {} {}".format(tok, parent_build_id, branch))
    with token_lock:
        try:
            with open(TOKEN_FILE, 'r+') as fd:
                tokens = json.load(fd)
                tokens[tok] = parent_build_id, branch
                fd.seek(0)
                json.dump(tokens, fd)
        except:#ALEX: this should be narrower (don't want to overwrite if some other error happened)
            with open(TOKEN_FILE, 'w') as fd:
                tokens = {}
                tokens[tok] = parent_build_id, branch
                json.dump(tokens, fd)
            app.logger.warn("activate_token: open/loads/append/seek/dump failed")

def start_bamboo_job(token, parent_build_id, branch):
    data = urllib.urlencode({"os_username" : "build", 
                             "os_password" : "build", 
                             "bamboo.variable.buildid" : parent_build_id, 
                             "bamboo.variable.branch" : branch, 
                             "bamboo.variable.token": token})
    obj = json.load(urllib2.urlopen(BAMBOO_URL, data))
    return obj['buildResultKey']

@app.route('/test_def/<filename>')
def get_test_def(filename):
    return send_from_directory(TEST_DIR, filename)

@app.route('/job_status')
def job_status():
    return ("ERROR: not yet implemented", 501)

@app.route('/node_status')
def node_status():
    return ("ERROR: not yet implemented", 501)

@app.route('/build_status')
def build_status():
    #synthetic based on 'project' in the OAR job
    # confirmed: www-data user can exec oarsub
    return ("ERROR: not yet implemented", 501)

@app.route('/artifact_collect', methods=['POST'])
def artifact_collect():
    artifact = request.files['artifact']
    token = request.form.get("token", None)
    if not token:
        return ("ERROR: missing token", 400)
    with open(os.path.join(RESULT_DIR,token,artifact.filename), 'w') as fd:
        artifact.save(fd)
    return ('OK\n', 200)

def get_job_data(token):
    filenames = [fn for fn in os.listdir(os.path.join(RESULT_DIR, token)) if os.path.isfile(os.path.join(RESULT_DIR,token,fn))]
    out_files = [fn for fn in filenames if fn[0:4] == 'OAR.' and fn[-7:] == '.stdout']
    #OAR will create both out and err files, even if empty
    jobids = [fn[4:-7] for fn in out_files]
    job_data = {jobid:{'jobid':jobid} for jobid in jobids}
    cmd = ["oarstat", "-Jf"]
    for jobid in jobids:
        cmd.append("-j")
        cmd.append(jobid)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()#ALEX: handle error
    obj = json.loads(out)

    for jobid in jobids:
        status = obj[jobid]["exit_code"] #ALEX: that can be null
        run_time_seconds = obj[jobid]["stopTime"] - obj[jobid]["startTime"]
        job_data[jobid]['status'] = status
        job_data[jobid]['run_time_seconds'] = run_time_seconds
        with open(os.path.join(RESULT_DIR, token, 'OAR.'+jobid+'.stdout'), 'r') as fd:
            name = fd.readline().strip()
        job_data[jobid]['name'] = name
    return job_data.values()

def aggregate(job_data):
    tests = len(job_data)
    failures = 0
    totaltime = 0
    for jd in job_data:
        failures += 0 if jd['status'] == 0 else 1
        totaltime += jd['run_time_seconds']
    return {'tests':tests, 'failures': failures, 'totaltime': totaltime}

@app.route('/get_junit/<token>')
def get_junit(token):
    job_data = get_job_data(token)
    aggregate_data = aggregate(job_data)
    aggregate_data['token'] = token
    return render_template('junit.xml', aggregate_data=aggregate_data, job_data=job_data)

@app.route('/get_stdout/<token>')
def get_stdout(token):
    filenames = [fn for fn in os.listdir(os.path.join(RESULT_DIR, token)) if os.path.isfile(os.path.join(RESULT_DIR,token,fn)) and fn[0:4] == 'OAR.' and fn[-7:] == '.stdout']
    filenames.sort()
    return render_template('log', filenames=filenames, token=token)

@app.route('/get_stderr/<token>')
def get_stderr(token):
    filenames = [fn for fn in os.listdir(os.path.join(RESULT_DIR, token)) if os.path.isfile(os.path.join(RESULT_DIR,token,fn)) and fn[0:4] == 'OAR.' and fn[-7:] == '.stderr']
    filenames.sort()
    return render_template('log', filenames=filenames, token=token)

def get_queue_length():
    p = subprocess.Popen(["oarstat", "-J"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out, err) = p.communicate()
    obj = json.loads(out)
    return len(obj)

def get_running_jobs():
    p = subprocess.Popen(["oarstat", "-J", "--sql", "state = 'Running'"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out, err) = p.communicate()
    return json.loads(out)

def get_idle_nodes():
    p = subprocess.Popen(["oarnodes", "-J"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    oarnodes = json.loads(out)
    res = []
    for _,v in oarnodes.iteritems():
        if "jobs" not in v:
            res.append("{} {}".format(v["host"], v["state"]))
    res.sort(key=LooseVersion)
    return res

def jobs_per_token():
    p = subprocess.Popen(["oarstat"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (oarstat, err) = p.communicate()
    jobs = {}
    regex =  re.compile(".*P=([A-Z]+)")
    for line in oarstat.split('\n'):
        m = regex.match(line)
        if m:
            if m.group(1) in jobs:
                jobs[m.group(1)] = jobs[m.group(1)] + 1
            else:
                jobs[m.group(1)] = 1
    return jobs

def get_job_token_data():
    jobs = jobs_per_token()
    obj = get_active_tokens()
    br_tok = defaultdict(list)
    for tok, vec in obj.iteritems():
        br_tok[vec[1]].append(vec[0]+", "+tok+", "+str(jobs[tok]))
    for br, v in br_tok.iteritems():
        v.sort()
    return br_tok

@app.route('/')
def show_index():
    return render_template('index.html', 
                           queue_length=get_queue_length(),             #int
                           running_jobs=json.dumps(get_running_jobs()), #list
                           idle_nodes=json.dumps(get_idle_nodes()),     #list
                           job_data=json.dumps(get_job_token_data()))   #dict

def get_result_dir(parent_build_id, branch):
    while 1:
        candidate = "".join(random.SystemRandom().choice(string.ascii_uppercase) for x in range(12))
        if not os.path.isdir(os.path.join(RESULT_DIR,candidate)):
            os.mkdir(os.path.join(RESULT_DIR,candidate))
            activate_token(candidate, parent_build_id, branch)
            return candidate

def parse_job_desc(test_def):
    def parse_kv(k, _, v):
        return k, v
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

