"""Flask REST API for private car ownership evaluations."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from calculator import CalculationError, calculate_evaluation


db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(36), primary_key=True)
    nickname = db.Column(db.String(32), nullable=False)
    nickname_key = db.Column(db.String(32), unique=True, nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    evaluations = db.relationship("Evaluation", back_populates="user", cascade="all, delete-orphan")


class Evaluation(db.Model):
    __tablename__ = "evaluations"
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    input = db.Column(db.JSON, nullable=False)
    result = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    user = db.relationship("User", back_populates="evaluations")


def _db_url():
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.getenv("DB_URL"):
        return os.environ["DB_URL"]
    if os.getenv("MYSQL_HOST"):
        return URL.create(
            "mysql+pymysql",
            username=os.getenv("MYSQL_USER", "carcost"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            host=os.getenv("MYSQL_HOST", "db"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.getenv("MYSQL_DATABASE", "carcost"),
            query={"charset": "utf8mb4"},
        )
    # Local development default. Production Compose always supplies MySQL env.
    return "sqlite:///carcost.sqlite3"


def _json_error(status: int, code: str, message: str, field: str | None = None):
    body = {"error": {"code": code, "message": message}}
    if field:
        body["error"]["field"] = field
    return jsonify(body), status


def _body():
    if not request.is_json:
        raise CalculationError("body", "Invia dati JSON con Content-Type application/json.")
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise CalculationError("body", "Invia un oggetto JSON valido.")
    return value


def _token_from_request(body=None):
    value = request.headers.get("X-Session-Token") or (body or {}).get("token")
    if not value:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            value = authorization[7:]
    return value


def _user_for_token(token):
    if not isinstance(token, str) or len(token) < 30 or len(token) > 256:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user = db.session.execute(select(User).where(User.token_hash == digest)).scalar_one_or_none()
    return user if user and hmac.compare_digest(user.token_hash, digest) else None


def session_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        user = _user_for_token(_token_from_request())
        if user is None:
            return _json_error(401, "session_required", "Sessione non valida. Inserisci il tuo codice di accesso o scegli un nuovo nickname.")
        return function(user, *args, **kwargs)
    return wrapper


def _detail(row):
    return {"id": row.id, "title": row.title, "input": row.input, "result": row.result,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}


def _summary(row):
    vehicle = row.input.get("vehicle") or {}
    return {"id": row.id, "title": row.title,
            "vehicle": {"make": vehicle.get("make"), "model": vehicle.get("model"),
                        "trim": vehicle.get("trim"), "condition": vehicle.get("condition")},
            "summary": row.result.get("summary", {}), "updated_at": row.updated_at.isoformat()}


CATALOG = {
    "makes": [
        {"name": "Alfa Romeo", "models": ["Giulia", "Giulietta", "Stelvio", "Tonale", "Junior"]},
        {"name": "Audi", "models": ["A1", "A3", "A4", "Q2", "Q3", "Q5"]},
        {"name": "BMW", "models": ["Serie 1", "Serie 3", "X1", "X3", "i3"]},
        {"name": "Citroën", "models": ["C3", "C4", "C5 Aircross"]},
        {"name": "Dacia", "models": ["Sandero", "Duster", "Jogger", "Spring"]},
        {"name": "Fiat", "models": ["Panda", "500", "500X", "Tipo", "Grande Panda"]},
        {"name": "Ford", "models": ["Fiesta", "Focus", "Puma", "Kuga"]},
        {"name": "Hyundai", "models": ["i10", "i20", "i30", "Kona", "Tucson", "IONIQ 5"]},
        {"name": "Jeep", "models": ["Avenger", "Renegade", "Compass"]},
        {"name": "Kia", "models": ["Picanto", "Rio", "Ceed", "Sportage", "EV3"]},
        {"name": "Mercedes-Benz", "models": ["Classe A", "Classe C", "GLA", "GLC"]},
        {"name": "Nissan", "models": ["Micra", "Juke", "Qashqai", "Leaf"]},
        {"name": "Opel", "models": ["Corsa", "Astra", "Mokka", "Grandland"]},
        {"name": "Peugeot", "models": ["208", "2008", "308", "3008"]},
        {"name": "Renault", "models": ["Clio", "Captur", "Megane", "R5"]},
        {"name": "Skoda", "models": ["Fabia", "Octavia", "Kamiq", "Karoq"]},
        {"name": "Toyota", "models": ["Aygo X", "Yaris", "Corolla", "C-HR", "RAV4"]},
        {"name": "Volkswagen", "models": ["Polo", "Golf", "T-Cross", "T-Roc", "Tiguan", "ID.3"]},
        {"name": "Volvo", "models": ["EX30", "XC40", "XC60", "V60"]},
    ],
    "options": {
        "condition": ["new", "km0", "used", "owned"],
        "fuel_type": ["petrol", "diesel", "lpg", "cng", "hybrid", "phev", "electric"],
        "insurance_channel": ["online", "agency"],
        "tyre_tier": ["base", "good"],
        "tyre_type": ["all_season", "summer", "winter", "seasonal"],
        "sale_channel": ["private", "dealer", "trade_in"],
    },
    "defaults": {
        "usage": {"years": 4, "annual_km": 15000, "charging_efficiency": .90},
        "tyres": {"life_km": 40000, "life_years": 6},
        "maintenance": {"service_interval_km": 15000, "service_interval_months": 12},
        "scenarios": {"fuel_increase_pct": 20, "insurance_increase_pct": 20,
                      "maintenance_increase_pct": 30, "residual_drop_pct": 20,
                      "income_drop_pct": 10, "extra_repair": 0},
    },
    "note": "Modelli indicativi per l'autocompletamento: marca e modello si possono sempre scrivere liberamente. Nessun prezzo è una quotazione live.",
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=_db_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    with app.app_context():
        for attempt in range(10):
            try:
                db.create_all()
                break
            except OperationalError:
                if attempt == 9 or app.config.get("TESTING"):
                    raise
                time.sleep(2)

    @app.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(CalculationError)
    def calculation_error(error):
        return _json_error(422, "validation_error", error.message, error.field)

    @app.errorhandler(413)
    def too_large(_):
        return _json_error(413, "payload_too_large", "Valutazione troppo grande.")

    @app.get("/api/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "ok", "database": "ok"})
        except Exception:
            return jsonify({"status": "unavailable", "database": "unavailable"}), 503

    @app.get("/api/catalog")
    def catalog():
        return jsonify(CATALOG)

    @app.post("/api/sessions")
    def session():
        body = _body()
        nickname = body.get("nickname")
        if not isinstance(nickname, str):
            return _json_error(422, "validation_error", "Inserisci un nickname.", "nickname")
        nickname = " ".join(nickname.strip().split())
        if not re.fullmatch(r"[\w .-]{2,32}", nickname, re.UNICODE):
            return _json_error(422, "validation_error", "Usa 2–32 lettere, numeri, spazi, punti, trattini o underscore.", "nickname")
        nickname_key = nickname.casefold()
        existing = db.session.execute(select(User).where(User.nickname_key == nickname_key)).scalar_one_or_none()
        if existing:
            token = _token_from_request(body)
            if _user_for_token(token) == existing:
                return jsonify({"nickname": existing.nickname, "token": token})
            return _json_error(409, "nickname_taken", "Nickname già usato. Inserisci il codice di accesso salvato oppure scegli un altro nickname.")
        token = secrets.token_urlsafe(32)
        user = User(id=str(uuid.uuid4()), nickname=nickname, nickname_key=nickname_key,
                    token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest())
        db.session.add(user)
        db.session.commit()
        return jsonify({"nickname": nickname, "token": token}), 201

    @app.get("/api/me")
    @session_required
    def me(user):
        return jsonify({"nickname": user.nickname, "evaluations_count": len(user.evaluations)})

    @app.post("/api/calculate")
    def calculate():
        return jsonify(calculate_evaluation(_body()))

    @app.route("/api/evaluations", methods=["GET", "POST"])
    @session_required
    def evaluations(user):
        if request.method == "GET":
            rows = db.session.execute(select(Evaluation).where(Evaluation.user_id == user.id)
                                      .order_by(Evaluation.updated_at.desc())).scalars().all()
            return jsonify([_summary(row) for row in rows])
        body = _body()
        result = calculate_evaluation(body)
        vehicle = body.get("vehicle") or {}
        title = body.get("title") or f"{(vehicle.get('make') or 'Auto')} {(vehicle.get('model') or '').strip()}".strip()
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise CalculationError("title", "Il titolo deve avere da 1 a 100 caratteri.")
        row = Evaluation(id=str(uuid.uuid4()), user_id=user.id, title=title.strip(), input=body, result=result)
        db.session.add(row)
        db.session.commit()
        return jsonify(_detail(row)), 201

    @app.route("/api/evaluations/<string:evaluation_id>", methods=["GET", "PUT", "DELETE"])
    @session_required
    def evaluation_detail(user, evaluation_id):
        row = db.session.execute(select(Evaluation).where(Evaluation.id == evaluation_id,
                                                             Evaluation.user_id == user.id)).scalar_one_or_none()
        if row is None:
            return _json_error(404, "not_found", "Valutazione non trovata.")
        if request.method == "GET":
            return jsonify(_detail(row))
        if request.method == "DELETE":
            db.session.delete(row)
            db.session.commit()
            return "", 204
        body = _body()
        result = calculate_evaluation(body)
        title = body.get("title") or row.title
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise CalculationError("title", "Il titolo deve avere da 1 a 100 caratteri.")
        row.title = title.strip()
        row.input = body
        row.result = result
        row.updated_at = utcnow()
        db.session.commit()
        return jsonify(_detail(row))

    return app
