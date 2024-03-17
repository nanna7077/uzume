import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class FolderPath(db.Model):
    __tablename__ = 'folderpaths'

    id = db.Column(db.Integer, primary_key=True)
    basepath = db.Column(db.Integer, nullable=False)
    added_on = db.Column(db.DateTime, nullable=False, default=(lambda x: datetime.datetime.now(datetime.UTC)))

    def __str__(self):
        return f"<{self.id} {self.basepath}>"

class Configuration(db.Model):
    __tablename__ = 'configurations'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), nullable=False)
    value = db.Column(db.String(255), nullable=False)

    def __str__(self):
        return f"<{self.id} {self.key}>"

class FileConvertions(db.Model):
    __tablename__ = 'fileconvertions'

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String, nullable=False)
    hashval = db.Column(db.String, nullable=False)
    convertedpath = db.Column(db.String, nullable=False)
    status = db.Column(db.Integer, nullable=False, default=0)
    added_on = db.Column(db.DateTime, nullable=False, default=(lambda x: datetime.datetime.now(datetime.UTC)))
    completed_on = db.Column(db.DateTime, nullable=True)

    def __str__(self):
        return f"<{self.id} {self.hashval}>"