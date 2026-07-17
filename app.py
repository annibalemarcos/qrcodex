import hashlib
import io
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import qrcode
from qrcode.image.pure import PyPNGImage
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, make_response, redirect, render_template, request,
    send_file, session, url_for
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "qrcodex-dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "qrcodex.db"),
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text, default="")
    price_label = db.Column(db.String(80), default="R$ 0")
    daily_limit = db.Column(db.Integer, nullable=True)   # None = ilimitado
    monthly_limit = db.Column(db.Integer, nullable=True) # None = ilimitado
    max_qrcodes = db.Column(db.Integer, nullable=True)   # None = ilimitado
    is_active = db.Column(db.Boolean, default=True)
    is_public = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    users = db.relationship("User", back_populates="plan")

    def limit_text(self):
        daily = "ilimitado" if self.daily_limit is None else f"{self.daily_limit}/dia"
        monthly = "ilimitado" if self.monthly_limit is None else f"{self.monthly_limit}/mês"
        qrs = "QRs ilimitados" if self.max_qrcodes is None else f"{self.max_qrcodes} QR(s)"
        return f"{daily} · {monthly} · {qrs}"


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    plan = db.relationship("Plan", back_populates="users")
    qrcodes = db.relationship("QRCode", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    target_url = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="qrcodes")
    visits = db.relationship("Visit", back_populates="qrcode", cascade="all, delete-orphan")


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qrcode_id = db.Column(db.Integer, db.ForeignKey("qr_code.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ip_hash = db.Column(db.String(64), default="")
    user_agent = db.Column(db.String(255), default="")
    referrer = db.Column(db.String(255), default="")
    allowed = db.Column(db.Boolean, default=True)

    qrcode = db.relationship("QRCode", back_populates="visits")


class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, default="")


# ----------------------------- helpers -----------------------------

def now_utc():
    return datetime.now(timezone.utc)


def today_start():
    n = now_utc()
    return datetime(n.year, n.month, n.day, tzinfo=timezone.utc)


def month_start():
    n = now_utc()
    return datetime(n.year, n.month, 1, tzinfo=timezone.utc)


def get_setting(key, default=""):
    row = Setting.query.get(key)
    return row.value if row else default


def set_setting(key, value):
    row = Setting.query.get(key)
    if not row:
        row = Setting(key=key)
        db.session.add(row)
    row.value = str(value)
    db.session.commit()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "site_name": get_setting("site_name", "QRCodex"),
        "signup_open": get_setting("signup_open", "1") == "1",
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Entre na sua conta para continuar.", "warning")
            return redirect(url_for("login", next=request.path))
        if not user.is_active:
            session.clear()
            flash("Sua conta está desativada. Fale com o suporte/admin.", "danger")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def normalize_url(raw):
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return raw


def slugify(text):
    allowed = string.ascii_lowercase + string.digits + "-"
    text = (text or "").lower().strip().replace("_", "-").replace(" ", "-")
    text = "".join(ch for ch in text if ch in allowed)
    text = "-".join(part for part in text.split("-") if part)
    return text[:50] or "qr"


def unique_slug(base, model):
    base = slugify(base)
    slug = base
    i = 2
    while model.query.filter_by(slug=slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


def random_slug(prefix="qr"):
    while True:
        slug = f"{prefix}-{secrets.token_urlsafe(5).replace('_', '').replace('-', '').lower()}"
        if not QRCode.query.filter_by(slug=slug).first():
            return slug


def hash_ip(ip):
    salt = app.config["SECRET_KEY"][:16]
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def count_allowed_visits(qrcode_id, since):
    return Visit.query.filter(
        Visit.qrcode_id == qrcode_id,
        Visit.allowed.is_(True),
        Visit.created_at >= since,
    ).count()


def plan_allows_redirect(qrcode):
    plan = qrcode.user.plan or Plan.query.filter_by(is_default=True).first()
    if not plan or not plan.is_active:
        return False, "Plano indisponível ou desativado."

    daily = count_allowed_visits(qrcode.id, today_start())
    monthly = count_allowed_visits(qrcode.id, month_start())

    if plan.daily_limit is not None and daily >= plan.daily_limit:
        return False, f"Limite diário atingido: {plan.daily_limit} redirecionamento(s)/dia."
    if plan.monthly_limit is not None and monthly >= plan.monthly_limit:
        return False, f"Limite mensal atingido: {plan.monthly_limit} redirecionamento(s)/mês."
    return True, "OK"


def usage_for_qr(qrcode):
    return {
        "today": count_allowed_visits(qrcode.id, today_start()),
        "month": count_allowed_visits(qrcode.id, month_start()),
        "total": Visit.query.filter_by(qrcode_id=qrcode.id, allowed=True).count(),
    }


def user_qr_limit_reached(user):
    plan = user.plan
    if not plan or plan.max_qrcodes is None:
        return False
    active_count = QRCode.query.filter_by(user_id=user.id).count()
    return active_count >= plan.max_qrcodes


# ----------------------------- seed -----------------------------

def seed_database():
    db.create_all()

    if not Plan.query.first():
        free = Plan(
            name="Free",
            slug="free",
            description="Plano inicial para validar a ideia sem susto no cartão.",
            price_label="R$ 0",
            daily_limit=10,
            monthly_limit=100,
            max_qrcodes=1,
            is_default=True,
        )
        qr1 = Plan(
            name="QR1",
            slug="qr1",
            description="Para pequenos negócios, cardápios, links de bio e campanhas simples.",
            price_label="R$ 19/mês",
            daily_limit=100,
            monthly_limit=3000,
            max_qrcodes=5,
        )
        qr2 = Plan(
            name="QR2",
            slug="qr2",
            description="Para campanhas com tráfego maior e múltiplos QR Codes.",
            price_label="R$ 49/mês",
            daily_limit=500,
            monthly_limit=15000,
            max_qrcodes=20,
        )
        db.session.add_all([free, qr1, qr2])

    if not Setting.query.get("site_name"):
        db.session.add(Setting(key="site_name", value="QRCodex"))
    if not Setting.query.get("signup_open"):
        db.session.add(Setting(key="signup_open", value="1"))

    admin_email = os.getenv("ADMIN_EMAIL", "admin@qrcodex.local").lower().strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "000000")
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        default_plan = Plan.query.filter_by(is_default=True).first()
        admin = User(
            name="Admin QRCodex",
            email=admin_email,
            is_admin=True,
            is_active=True,
            plan=default_plan,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
    db.session.commit()


with app.app_context():
    seed_database()


# ----------------------------- public/auth -----------------------------

@app.route("/")
def index():
    plans = Plan.query.filter_by(is_active=True, is_public=True).order_by(Plan.id.asc()).all()
    return render_template("index.html", plans=plans)


@app.route("/register", methods=["GET", "POST"])
def register():
    if get_setting("signup_open", "1") != "1":
        flash("Novos cadastros estão pausados no momento.", "warning")
        return redirect(url_for("login"))

    plans = Plan.query.filter_by(is_active=True, is_public=True).order_by(Plan.id.asc()).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        plan_id = request.form.get("plan_id")

        if not name or not email or not password:
            flash("Preencha nome, e-mail e senha.", "danger")
            return render_template("register.html", plans=plans)
        if len(password) < 6:
            flash("Use uma senha com pelo menos 6 caracteres.", "danger")
            return render_template("register.html", plans=plans)
        if User.query.filter_by(email=email).first():
            flash("Esse e-mail já está cadastrado.", "danger")
            return render_template("register.html", plans=plans)

        plan = Plan.query.get(plan_id) if plan_id else None
        if not plan or not plan.is_active or not plan.is_public:
            plan = Plan.query.filter_by(is_default=True).first()

        user = User(name=name, email=email, plan=plan)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        flash("Conta criada. Agora é só apontar o QR para onde o dinheiro mora.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html", plans=plans)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("E-mail ou senha inválidos.", "danger")
            return render_template("login.html")
        if not user.is_active:
            flash("Essa conta está desativada.", "danger")
            return render_template("login.html")
        session["user_id"] = user.id
        next_url = request.args.get("next") or url_for("dashboard")
        return redirect(next_url)
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da conta.", "info")
    return redirect(url_for("index"))


# ----------------------------- user dashboard -----------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    qrs = QRCode.query.filter_by(user_id=user.id).order_by(QRCode.created_at.desc()).all()
    usage = {qr.id: usage_for_qr(qr) for qr in qrs}
    return render_template("dashboard.html", qrs=qrs, usage=usage)


@app.route("/qrcodes/new", methods=["GET", "POST"])
@login_required
def qrcode_new():
    user = current_user()
    if user_qr_limit_reached(user):
        flash("Seu plano atingiu o limite de QR Codes. Suba o plano ou peça ao admin para liberar.", "warning")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        target_url = normalize_url(request.form.get("target_url", ""))
        custom_slug = request.form.get("slug", "").strip()
        notes = request.form.get("notes", "").strip()
        if not title or not target_url:
            flash("Preencha título e URL de destino válida.", "danger")
            return render_template("qrcode_form.html", qr=None)
        slug = unique_slug(custom_slug or title, QRCode) if custom_slug else random_slug(slugify(title))
        qr = QRCode(user_id=user.id, title=title, target_url=target_url, slug=slug, notes=notes)
        db.session.add(qr)
        db.session.commit()
        flash("QR Code criado. Agora ele já conta visitas e redireciona.", "success")
        return redirect(url_for("dashboard"))
    return render_template("qrcode_form.html", qr=None)


@app.route("/qrcodes/<int:qr_id>/edit", methods=["GET", "POST"])
@login_required
def qrcode_edit(qr_id):
    user = current_user()
    qr = QRCode.query.get_or_404(qr_id)
    if qr.user_id != user.id and not user.is_admin:
        abort(403)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        target_url = normalize_url(request.form.get("target_url", ""))
        notes = request.form.get("notes", "").strip()
        is_active = request.form.get("is_active") == "1"
        if not title or not target_url:
            flash("Preencha título e URL de destino válida.", "danger")
            return render_template("qrcode_form.html", qr=qr)
        qr.title = title
        qr.target_url = target_url
        qr.notes = notes
        qr.is_active = is_active
        db.session.commit()
        flash("QR Code atualizado.", "success")
        return redirect(url_for("dashboard"))
    return render_template("qrcode_form.html", qr=qr)


@app.route("/qrcodes/<int:qr_id>/delete", methods=["POST"])
@login_required
def qrcode_delete(qr_id):
    user = current_user()
    qr = QRCode.query.get_or_404(qr_id)
    if qr.user_id != user.id and not user.is_admin:
        abort(403)
    db.session.delete(qr)
    db.session.commit()
    flash("QR Code apagado.", "info")
    return redirect(url_for("dashboard"))


@app.route("/qrcodes/<int:qr_id>")
@login_required
def qrcode_detail(qr_id):
    user = current_user()
    qr = QRCode.query.get_or_404(qr_id)
    if qr.user_id != user.id and not user.is_admin:
        abort(403)
    visits = Visit.query.filter_by(qrcode_id=qr.id).order_by(Visit.created_at.desc()).limit(100).all()
    usage = usage_for_qr(qr)
    return render_template("qrcode_detail.html", qr=qr, visits=visits, usage=usage)


@app.route("/qr-image/<slug>.png")
def qr_image(slug):
    qr = QRCode.query.filter_by(slug=slug).first_or_404()
    target = url_for("redirect_qr", slug=qr.slug, _external=True)

    # Usa PyPNGImage para gerar PNG puro, sem Pillow.
    # Isso evita erro no Windows com Python 3.14, onde Pillow antigo tenta compilar zlib.
    qr_builder = qrcode.QRCode(version=None, box_size=10, border=4)
    qr_builder.add_data(target)
    qr_builder.make(fit=True)
    img = qr_builder.make_image(image_factory=PyPNGImage)

    buffer = io.BytesIO()
    img.save(buffer)
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png", download_name=f"{qr.slug}.png")


@app.route("/q/<slug>")
def redirect_qr(slug):
    qr = QRCode.query.filter_by(slug=slug).first_or_404()
    if not qr.is_active or not qr.user.is_active:
        return render_template("blocked.html", title="QR Code pausado", message="Este QR Code está desativado no momento."), 423

    allowed, message = plan_allows_redirect(qr)
    visit = Visit(
        qrcode_id=qr.id,
        user_id=qr.user_id,
        ip_hash=hash_ip(request.headers.get("X-Forwarded-For", request.remote_addr or "")),
        user_agent=(request.headers.get("User-Agent") or "")[:255],
        referrer=(request.headers.get("Referer") or "")[:255],
        allowed=allowed,
    )
    db.session.add(visit)
    db.session.commit()

    if not allowed:
        return render_template("blocked.html", title="Limite atingido", message=message), 429
    return redirect(qr.target_url, code=302)


# ----------------------------- admin -----------------------------

@app.route("/admin")
@login_required
@admin_required
def admin_home():
    total_users = User.query.count()
    total_qrs = QRCode.query.count()
    total_visits = Visit.query.filter_by(allowed=True).count()
    blocked_visits = Visit.query.filter_by(allowed=False).count()
    last_visits = Visit.query.order_by(Visit.created_at.desc()).limit(10).all()
    return render_template(
        "admin_home.html",
        total_users=total_users,
        total_qrs=total_qrs,
        total_visits=total_visits,
        blocked_visits=blocked_visits,
        last_visits=last_visits,
    )


@app.route("/admin/plans")
@login_required
@admin_required
def admin_plans():
    plans = Plan.query.order_by(Plan.id.asc()).all()
    return render_template("admin_plans.html", plans=plans)


@app.route("/admin/plans/new", methods=["GET", "POST"])
@app.route("/admin/plans/<int:plan_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_plan_form(plan_id=None):
    plan = Plan.query.get_or_404(plan_id) if plan_id else None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = slugify(request.form.get("slug", "").strip() or name)
        description = request.form.get("description", "").strip()
        price_label = request.form.get("price_label", "").strip() or "Sob consulta"
        daily_limit_raw = request.form.get("daily_limit", "").strip()
        monthly_limit_raw = request.form.get("monthly_limit", "").strip()
        max_qrcodes_raw = request.form.get("max_qrcodes", "").strip()
        is_active = request.form.get("is_active") == "1"
        is_public = request.form.get("is_public") == "1"
        is_default = request.form.get("is_default") == "1"

        def parse_optional_int(value):
            if value == "":
                return None
            try:
                parsed = int(value)
                return parsed if parsed >= 0 else None
            except ValueError:
                return None

        if not name:
            flash("Nome do plano é obrigatório.", "danger")
            return render_template("admin_plan_form.html", plan=plan)

        duplicated = Plan.query.filter(Plan.slug == slug)
        if plan:
            duplicated = duplicated.filter(Plan.id != plan.id)
        if duplicated.first():
            flash("Esse slug de plano já existe.", "danger")
            return render_template("admin_plan_form.html", plan=plan)

        if not plan:
            plan = Plan()
            db.session.add(plan)
        plan.name = name
        plan.slug = slug
        plan.description = description
        plan.price_label = price_label
        plan.daily_limit = parse_optional_int(daily_limit_raw)
        plan.monthly_limit = parse_optional_int(monthly_limit_raw)
        plan.max_qrcodes = parse_optional_int(max_qrcodes_raw)
        plan.is_active = is_active
        plan.is_public = is_public
        plan.is_default = is_default

        if is_default:
            Plan.query.filter(Plan.id != (plan.id or 0)).update({"is_default": False})
        db.session.commit()
        flash("Plano salvo.", "success")
        return redirect(url_for("admin_plans"))
    return render_template("admin_plan_form.html", plan=plan)


@app.route("/admin/plans/<int:plan_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_plan_delete(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    if plan.users:
        plan.is_active = False
        plan.is_public = False
        flash("Plano possui usuários. Desativei em vez de apagar, para não quebrar nada.", "warning")
    else:
        db.session.delete(plan)
        flash("Plano apagado.", "info")
    db.session.commit()
    return redirect(url_for("admin_plans"))


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    plans = Plan.query.order_by(Plan.id.asc()).all()
    return render_template("admin_users.html", users=users, plans=plans)


@app.route("/admin/users/<int:user_id>/update", methods=["POST"])
@login_required
@admin_required
def admin_user_update(user_id):
    user = User.query.get_or_404(user_id)
    plan_id = request.form.get("plan_id")
    user.name = request.form.get("name", user.name).strip() or user.name
    user.plan_id = int(plan_id) if plan_id else user.plan_id
    user.is_active = request.form.get("is_active") == "1"
    user.is_admin = request.form.get("is_admin") == "1"
    db.session.commit()
    flash("Usuário atualizado.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    if request.method == "POST":
        set_setting("site_name", request.form.get("site_name", "QRCodex").strip() or "QRCodex")
        set_setting("signup_open", "1" if request.form.get("signup_open") == "1" else "0")
        flash("Configurações salvas.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html")


@app.route("/admin/visits")
@login_required
@admin_required
def admin_visits():
    visits = Visit.query.order_by(Visit.created_at.desc()).limit(300).all()
    return render_template("admin_visits.html", visits=visits)


@app.errorhandler(403)
def forbidden(_):
    return render_template("blocked.html", title="Sem acesso", message="Você não tem permissão para ver essa área."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("blocked.html", title="Não encontrado", message="Esse link não existe ou saiu para comprar pão."), 404


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5432"))
    app.run(host="0.0.0.0", port=port, debug=True)
