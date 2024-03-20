# uzume

A simple transcoding video streamer.

<img src="https://raw.githubusercontent.com/nanna7077/uzume/master/static/uzume-nobg.png" height="300">

## Install

1. Clone the repository to /opt/uzume
2. Run `pip install -r requirements.txt`
3. Copy 'uzume.service' to '/etc/systemd/system'
4. Run `systemctl daemon-reload`
5. Run `systemctl enable uzume`
6. Run `systemctl start uzume`
7. Goto http://localhost:5000 to complete first setup.
8. Uzume will be available from http://YOUR_SERVER_IP:5000
9. Enjoy :D

## Runtime Flags

- `--port PORT` (default: 5000)
- `--addpath FULLPATH` (Can also be added from the UI)
- `--cachedir CACHEDIR` (default: /tmp/uzume - Change it to a non-temporary directory to store transcoded videos, which will reduce CPU usage.)
- `--configdir CONFIGDIR` (default: ~/.config/.uzume)
- `--donotlimitcpu 1` (default: False, prevents autolimiting the CPU usage to 1 thread per stream.)