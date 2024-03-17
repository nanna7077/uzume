import os
import argparse
import waitress
import server

WebServerProcess = None

parser = argparse.ArgumentParser("uzume")
parser.add_argument("--port", type=int)
parser.add_argument("--addpath", type=str)
parser.add_argument("--cachedir", type=str, default=os.path.join(os.path.expanduser("~/.cache"), ".uzume"))
parser.add_argument("--configdir", type=str, default=os.path.join(os.path.expanduser("~/.config"), ".uzume"))

args = parser.parse_args()

if args.port:
    PORT = args.port
else:
    PORT = 5000

if args.addpath:
    message, status = server.add_path(args.addpath)
    if not status:
        print(f"[Error] {message}")
        exit()
    else:
        print(f"[Success] {message}")

try:
    print(f"[INFO] Web Server Listening on http://0.0.0.0:{PORT}")
    server.init(args.configdir, args.cachedir)
    waitress.serve(server.app, host="0.0.0.0", port=PORT)
except Exception as err:
    print("[ERROR] Error Starting Web Server", err)