import os
import sys
import multiprocessing
import threading
import time
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import hashlib
import pam
import pyffmpeg

from models import *
from defaultConfig import DEFAULT_CONFIG

app = Flask(__name__)
CORS(app)

CONFIGDIR = None
CACHEDIR = "/tmp/uzume"
LIMITCPU = True
streamCleanerThread = None

runningStreams = {}

def create_stream(path, streamfile):
    # os.system(f"{pyffmpeg.FFmpeg().get_ffmpeg_bin()} -i '{path}' -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -vf 'scale=1280:-1' -movflags +faststart -hls_time 5 -hls_list_size 0 -reset_timestamps 1 -hls_segment_filename {streamfile.replace('.m3u8', '') + '_%03d'}.ts {streamfile}")
    os.system(f"{pyffmpeg.FFmpeg().get_ffmpeg_bin()} -i '{path}' -y -c:s webvtt {streamfile.replace('.m3u8', '') + '_sub'}.vtt")
    os.system(f"{pyffmpeg.FFmpeg().get_ffmpeg_bin()} -i '{path}'{' -threads 1 ' if LIMITCPU else ' '}-c:v h264 -preset:v ultrafast -crf 23 -c:a copy -b:a 128k -vf 'scale=1280:-1' -movflags +faststart -hls_time 5 -hls_list_size 0 -reset_timestamps 1 -hls_segment_filename {streamfile.replace('.m3u8', '') + '_%03d'}.ts {streamfile}")

def streamcleaner():
    global runningStreams

    while True:
        print("[INFO] Scanning for not watching streams")
        for hashval in [k for k in runningStreams.keys()]:
            if datetime.datetime.now() - runningStreams[hashval][1] > datetime.timedelta(minutes=5):
                print(f"[INFO] Cleaning up {hashval}")
                current = runningStreams.pop(hashval)
                current[0].terminate()
        time.sleep(60)

def init(configdir, cachedir, limitcpu):
    global CONFIGDIR, CACHEDIR, LIMITCPU

    CONFIGDIR = configdir
    CACHEDIR = cachedir
    LIMITCPU = limitcpu

    os.makedirs(CACHEDIR, exist_ok=True)
    os.makedirs(CONFIGDIR, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(CONFIGDIR, 'database.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    with app.app_context():
        try:
            isFirstRun = Configuration.query.filter_by(key="is_first_run").first()
            if not isFirstRun:
                raise Exception
            
            print("[INFO] Server started.")

        except:
            try:
                os.removedirs("instance")
                # Restart the server
                os.execl(sys.executable, sys.executable, *sys.argv)
            except:
                pass
            db.create_all()
            for config in DEFAULT_CONFIG:
                newConfig = Configuration(key=config, value=DEFAULT_CONFIG[config])
                db.session.add(newConfig)
                db.session.commit()
        
    streamCleanerThread = threading.Thread(target=streamcleaner)
    streamCleanerThread.start()

@app.context_processor
def insert_data():
    return {
        "INSTANCE_NAME": (
            Configuration.query.filter_by(key="instance_name").first().value
            if Configuration.query.filter_by(key="instance_name").first()
            else ""
        ),
        "INSTANCE_DESCRIPTION": (
            Configuration.query.filter_by(key="instance_description").first().value
            if Configuration.query.filter_by(key="instance_description").first()
            else ""
        ),
        "IS_FIRST_RUN": (
            True if Configuration.query.filter_by(key="is_first_run").first().value == "0" else False
            if Configuration.query.filter_by(key="is_first_run").first()
            else ""
        ),
    }


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/firstSetup", methods=["POST"])
def first_setup():
    first_run = Configuration.query.filter_by(key="is_first_run").first()
    if first_run.value == "1":
        return jsonify({"error": "Already set up"}), 400

    instance_name = request.get_json().get("instance_name")
    instance_description = request.get_json().get("instance_description")

    if not (instance_name and instance_description):
        return jsonify({"error": "All fields are required"}), 400

    name_config = Configuration.query.filter_by(key="instance_name").first()
    if name_config:
        name_config.value = instance_name
    else:
        db.session.add(Configuration(key="instance_name", value=instance_name))

    description_config = Configuration.query.filter_by(
        key="instance_description"
    ).first()
    if description_config:
        description_config.value = instance_description
    else:
        db.session.add(
            Configuration(
                key="instance_description", value=instance_description
            )
        )

    first_run.value = "1"
    db.session.commit()

    return jsonify({"message": "Success"}), 200

@app.route("/filelisting", methods=["POST"])
def catch_all():
    def default_listing():
        return {"paths": [{"path": basepath.basepath, "is_dir": True} for basepath in FolderPath.query.all()], "current": "/"}, 200
    

    path = request.get_json(force=True).get("path", '/')
    if not path:
        return {"error": "Path not specified"}, 400
    if not FolderPath.query.all():
        return {"error": "No folder's added yet. Add one first."}, 404
    if path == "/":
        return default_listing()
    
    basePath = FolderPath.query.filter( FolderPath.basepath == path).first()
    if not basePath:
        for basepath in FolderPath.query.all():
            if path.startswith(basepath.basepath):
                basePath = basepath
                break

    if not basePath:
        return default_listing()
    
    return {"paths": [{"path": f"{path}/{child}", "is_dir": os.path.isdir(f"{path}/{child}"), } for child in sorted(os.listdir(path))] + [{"path": '/'.join(path.split('/')[:-1]), "is_dir": True}] , "current": path }, 200

def add_path(path):
    if not (os.path.exists(path) or os.path.isdir(path)):
        return "Invalid path", False

    basePath = FolderPath.query.filter(FolderPath.basepath.like(f"{path}%")).first()
    if basePath:
        return "Path already exists", False
    
    with app.app_context():
        newPath = FolderPath(basepath=path)
        db.session.add(newPath)
        db.session.commit()
    
    return "Path added", True


@app.route("/addpath", methods=["POST"])
def add_path_route():
    requestData = request.get_json(force=True)
    path, username, password = requestData.get("path"), requestData.get("username"), requestData.get("password")

    if not pam.authenticate(username, password):
        return {"error": "Invalid credentials"}, 401
    if not path:
        return {"error": "Path not specified"}, 400
    
    message, status = add_path(path)
    return ({"message": message}, 200) if status else ({"error": message}, 400)


@app.route("/streamready")
def streamready():
    path = request.args.get("path")
    if not path:
        return {"error": "Path not specified"}, 400

    if not FolderPath.query.all():
        return {"error": "No path's added yet. Add one first."}, 404

    basePath = FolderPath.query.filter( FolderPath.basepath == path).first()
    if not basePath:
        for basepath in FolderPath.query.all():
            if path.startswith(basepath.basepath):
                basePath = basepath
                break

    if not basePath:
        return {"error": "Invalid path"}, 400
    
    if not os.path.isfile(path):
        return {"error": "Video not found"}, 404

    probedata = pyffmpeg.FFprobe(path)

    if probedata.metadata[0] == []:
        return {"error": "Invalid Media"}, 400
    
    hashval = hashlib.sha256(path.encode('utf-8')).hexdigest()
   
    if hashval not in runningStreams:
        outputpath = os.path.join(CACHEDIR, f"{hashval}.m3u8")
        process = multiprocessing.Process(target=create_stream, args=(path, outputpath))
        process.daemon = True
        process.start()
        runningStreams[hashval] = [process, datetime.datetime.now()]

    while not os.path.exists(f"{CACHEDIR}/{hashval}.m3u8"):
        time.sleep(0.1)
    
    return {
        "duration": (lambda x: x.second + x.minute * 60 + x.hour * 3600)(datetime.datetime.strptime(probedata.duration, "%H:%M:%S.%f")),
        "filename": probedata.file_name.split("/")[-1],
        "hashval": hashval,
    }, 200

@app.route("/stream/<fname>", methods=["GET"])
def stream(fname):
    fname = fname.replace("..", "").rstrip("/")
    file_path = os.path.join(CACHEDIR, fname)

    if not fname or not os.path.exists(file_path):
        return Response(status=404)
    
    return send_from_directory(CACHEDIR, fname)

@app.route("/stillwatching/<hashval>")
def isstillwatching(hashval):
    global runningStreams

    if hashval not in runningStreams:
        return {"error": "Stream not found"}, 404
    
    runningStreams.update({hashval: [runningStreams[hashval][0], datetime.datetime.now()]})
    return {"message": "updated"}, 200


@app.errorhandler(Exception)
def handle_exception(e):
    return {"error": str(e)}, 500