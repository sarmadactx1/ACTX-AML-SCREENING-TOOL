import json
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="analyst")  # 'admin' or 'analyst'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class ScreeningRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference_id = db.Column(db.String(64), unique=True, nullable=False)
    batch_id = db.Column(db.String(64), nullable=True, index=True)

    subject_name = db.Column(db.String(255), nullable=False, index=True)
    entity_type = db.Column(db.String(20), default="Person")
    country = db.Column(db.String(100), default="")
    dob = db.Column(db.String(40), default="")
    threshold = db.Column(db.Float, default=0.7)
    mode = db.Column(db.String(10), default="Single")  # Single / Bulk

    screened_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    screened_by = db.relationship("User", foreign_keys=[screened_by_id])
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    os_matches_json = db.Column(db.Text, default="[]")
    uae_matches_json = db.Column(db.Text, default="[]")
    un_matches_json = db.Column(db.Text, default="[]")
    un_checked = db.Column(db.Boolean, default=False)
    match_count = db.Column(db.Integer, default=0)
    result_status = db.Column(db.String(20), default="Clear", index=True)  # Clear / Needs review / Possible hit

    review_status = db.Column(db.String(20), default="Pending", index=True)  # Pending / Cleared / Escalated / Reported
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, default="")

    def os_matches(self):
        return json.loads(self.os_matches_json or "[]")

    def uae_matches(self):
        return json.loads(self.uae_matches_json or "[]")

    def un_matches(self):
        return json.loads(self.un_matches_json or "[]")

    def set_matches(self, os_matches, uae_matches, un_matches=None, un_checked=False):
        un_matches = un_matches or []
        self.os_matches_json = json.dumps(os_matches)
        self.uae_matches_json = json.dumps(uae_matches)
        self.un_matches_json = json.dumps(un_matches)
        self.un_checked = un_checked
        self.match_count = len(os_matches) + len(uae_matches) + len(un_matches)


class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, default="")

    @staticmethod
    def get(key, default=None):
        row = Setting.query.get(key)
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = Setting.query.get(key)
        if row is None:
            row = Setting(key=key, value=value)
            db.session.add(row)
        else:
            row.value = value
        db.session.commit()
