import os
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import multiprocessing
import shutil
import datetime
from flask import Flask, render_template, request, jsonify, Response, send_file
import hashlib
import pam
import pyffmpeg

from models import *
from defaultConfig import DEFAULT_CONFIG, UNSUPPORTED_FILETYPES

app = Flask(__name__)

CACHEDIR = None
CONFIGDIR = None

def hash_file(file_name):
    """Return the SHA1 hash of a file"""
    with open(file_name, 'rb') as f:
        data = f.read(1024)
        hasher = hashlib.sha1()
        while data:
            hasher.update(data)
            data = f.read(1024)
    return hasher.hexdigest()

def unsupported_file_converter(path, newpath):
    def free_space_check():
        total, used, free = shutil.disk_usage(CACHEDIR)
        return free // (2**30)
    
    while (free_space_check() < 15 or os.listdir(CACHEDIR) == 0):
        print("[INFO] Cache is full. Cleaning up.")
        for file in sorted(os.listdir(CACHEDIR), key=os.path.getmtime):
            os.remove(os.path.join(CACHEDIR, file))
    if free_space_check() < 15:
        print("[ERROR] Cache drive is full. Nothing to cleanup. Aborting.")
        return False
    
    with app.app_context():
        conv = FileConvertions(path=path, hashval=hash_file(path), convertedpath=newpath)
        db.session.add(conv)
        db.session.commit()

    ffbin = pyffmpeg.FFmpeg(enable_log=False).get_ffmpeg_bin()
    os.system(f"{ffbin} -i \"{path}\" \"{newpath}\" -hide_banner -loglevel error -codec copy")

    with app.app_context():
        conv = FileConvertions.query.filter_by(path=path).first()
        conv.status = True
        conv.completed_on = datetime.datetime.now(datetime.UTC)
        db.session.commit()
    return True


class FileSystemEventHandler_(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            process = multiprocessing.Process(target=unsupported_file_converter, args=(event.src_path, os.path.join(CACHEDIR, f"{hash_file(event.src_path)}.mp4")))
            process.daemon = True
            process.start()
    
    def on_moved(self, event):
        if not event.is_directory:
            process = multiprocessing.Process(target=unsupported_file_converter, args=(event.dest_path, os.path.join(CACHEDIR, f"{hash_file(event.src_path)}.mp4")))
            process.daemon = True
            process.start()
    
    def on_deleted(self, event):
        if not event.is_directory:
            with app.app_context():
                fileconvertion = FileConvertions.query.filter_by(path=event.src_path).first()
                os.remove(fileconvertion.path)
                db.session.delete(fileconvertion)
                db.session.commit()


def batch_unsupported_file_converter(folderpaths):
    print("[INFO] Scanning for unsupported file types.")
    with app.app_context():
        for basepath in folderpaths:
            print(f"[INFO] Converting unsupported files in {basepath}.")
            for root, _, files in os.walk(basepath):
                for file in files:
                    if '.'+file.split(".")[-1] in UNSUPPORTED_FILETYPES:
                        if not os.path.exists(os.path.join(CACHEDIR, f"{hash_file(os.path.join(root, file))}.mp4")):
                            if FileConvertions.query.filter_by(path=os.path.join(root, file)).first():
                                os.remove(os.path.join(CACHEDIR, f"{hash_file(os.path.join(root, file))}.mp4"))
                                db.session.delete(FileConvertions.query.filter_by(path=os.path.join(root, file)).first())
                                db.session.commit()
                            unsupported_file_converter(os.path.join(root, file), os.path.join(CACHEDIR, f"{hash_file(os.path.join(root, file))}.mp4"))
    print("[INFO] Scanned and fixed unsupported file types.")


def init(configdir, cachedir):
    global CACHEDIR, CONFIGDIR

    CACHEDIR = cachedir
    CONFIGDIR = configdir

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
            
            total, used, free = shutil.disk_usage(CACHEDIR)
            if free // (2**30) > 15:
                process = multiprocessing.Process(target=batch_unsupported_file_converter, args=([basepath.basepath for basepath in FolderPath.query.all()],))
                process.daemon = True
                process.start()
                    
            print("[INFO] Starting Filesystem Observer.")
            event_handler = FileSystemEventHandler_()
            observer = Observer()
            for basepath in FolderPath.query.all():
                observer.schedule(event_handler, basepath.basepath, recursive=True)
            observer.start()
            print("[INFO] Filesystem Observer started.")

            print("[INFO] Continuing interrupted jobs.")
            for conv in FileConvertions.query.all():
                if conv.status:
                    continue
                os.remove(conv.convertedpath)
                process = multiprocessing.Process(target=unsupported_file_converter, args=(conv.path, os.path.join(CACHEDIR, f"{hash_file(conv.path)}.mp4")))
                process.daemon = True
                process.start()

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
        "CURRENT_CONVERTIONS": [
            {
                "path": conv.path,
                "hash": conv.hashval,
                "convertedpath": conv.convertedpath,
                "status": True if conv.status == 1 else False,
                "added_on": conv.added_on,
                "completed_on": conv.completed_on
            }
            for conv in FileConvertions.query.all()
        ],
        "CURRENT_CONVERTIONS_COUNT": len(FileConvertions.query.filter_by(status=0).all())
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
    def is_converted(filepath):
        convertion = FileConvertions.query.filter(FileConvertions.path == filepath).first()
        if convertion:
            return {"hash": convertion.hashval, "status": convertion.status, "added_on": convertion.added_on, "completed_on": convertion.completed_on}

        return None
    
    def default_listing():
        return {"paths": [{"path": basepath.basepath, "is_dir": True} for basepath in FolderPath.query.all()], "convertion": None, "current": "/"}, 200
    

    path = request.get_json(force=True).get("path", '/')
    if not path:
        return {"error": "Path not specified"}, 400

    if not FolderPath.query.all():
        return {"error": "No path's added yet. Add one first."}, 404

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
    
    return {"paths": [{"path": f"{path}/{child}", "is_dir": os.path.isdir(f"{path}/{child}"), "convertion": is_converted(f"{path}/{child}") } for child in sorted(os.listdir(path))] + [{"path": '/'.join(path.split('/')[:-1]), "is_dir": True}] , "current": path }, 200

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
    
    process = multiprocessing.Process(target=batch_unsupported_file_converter, args=([basepath.basepath for basepath in FolderPath.query.all()],))
    process.daemon = True
    process.start()
    
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

    altfile = os.path.join(CACHEDIR, f"{hash_file(path)}.mp4")
    for filetype in UNSUPPORTED_FILETYPES:
        if '.'+path.split(".")[-1] == filetype:
            if os.path.exists(altfile):
                path = altfile
                break
            else:
                return {"error": "Not ready yet."}, 400
    
    probedata = pyffmpeg.FFprobe(path)

    if probedata.metadata[0] == []:
        return {"error": "Invalid Media"}, 400
    
    return {
        "duration": probedata.duration,
        "filename": probedata.file_name.split("/")[-1],
    }, 200


@app.route("/stream")
def stream():
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
        return Response("Video not found", status=404)
    
    probedata = pyffmpeg.FFprobe(path)

    if probedata.metadata[0] == []:
        return Response("Invalid Media", status=400)
    
    altfile = os.path.join(CACHEDIR, f"{hash_file(path)}.mp4")
    for filetype in UNSUPPORTED_FILETYPES:
        if '.'+path.split(".")[-1] == filetype:
            if os.path.exists(altfile):
                path = altfile
                convertion = FileConvertions.query.filter(FileConvertions.path == path).first()
                if convertion and convertion.status == 0:
                    return Response("Caching In Progress", status=404)
                break
            else:
                return Response("Not ready yet", status=400)
            
    return send_file(path)

