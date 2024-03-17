# uzume

A simple video streamer with transcoding support.

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