"""Vercel entrypoint: one Flask app, durable SQL progress, private evidence."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, send_from_directory, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from storage import Store, users, events, blank_progress

ROOT = Path(__file__).resolve().parent


def create_app(settings=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', ''),
        ADMIN_PASSWORD=os.environ.get('ADMIN_PASSWORD', ''),
        DATABASE_URL=os.environ.get('DATABASE_URL', ''),
        ONLINE=bool(os.environ.get('VERCEL')),
        REGISTRATION_OPEN=os.environ.get('REGISTRATION_OPEN', 'true').lower() == 'true',
        DATA_DIR=ROOT / 'private_data',
        MAX_CONTENT_LENGTH=8192,
        SESSION_COOKIE_NAME='northstar_online',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if settings:
        app.config.update(settings)
    app.config['SESSION_COOKIE_SECURE'] = app.config['ONLINE']
    issues = []
    if len(app.config['SECRET_KEY']) < 32:
        issues.append('SECRET_KEY must contain at least 32 random characters.')
    if len(app.config['ADMIN_PASSWORD']) < 12:
        issues.append('ADMIN_PASSWORD must contain at least 12 characters.')
    database_url = app.config['DATABASE_URL']
    if not database_url:
        issues.append('Connect a PostgreSQL database and set DATABASE_URL.')
    elif app.config['ONLINE'] and not database_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        issues.append('Online deployments require PostgreSQL; local SQLite is not persistent on Vercel.')
    data = Path(app.config['DATA_DIR'])
    if not (data / 'challenges.json').is_file():
        issues.append('Evidence has not been built. Set Build Command to python build.py and redeploy.')
    stages = json.loads((data / 'challenges.json').read_text(encoding='utf-8')) if (data / 'challenges.json').exists() else []
    store = None
    if not issues:
        try:
            store = Store(database_url)
        except Exception:
            issues.append('DATABASE_URL is invalid. Use the PostgreSQL connection string from your provider.')
    app.extensions['store'] = store
    app.extensions['stages'] = stages
    admin_signature = hashlib.sha256(app.config['ADMIN_PASSWORD'].encode()).hexdigest()

    def score(progress):
        earned = sum(s['value'] for s in stages if s['id'] in progress['solves'])
        spent = sum(h['cost'] for s in stages for i, h in enumerate(s['hints']) if f"{s['id']}:{i}" in progress['hints'])
        return earned - spent

    def allowed(stage, progress):
        return all(i in progress['solves'] for i in range(1, stage))

    def player(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            if not g.user:
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return guarded

    def gate(stage):
        if not g.user:
            abort(401, 'Sign in to open this evidence.')
        if not allowed(stage, g.user['progress']):
            abort(403, 'Solve the preceding stages to unlock this evidence.')

    def mutate_player(action):
        def checked(progress, row):
            if not row['active'] or row['epoch'] != session.get('epoch'):
                abort(403, 'Your session changed. Sign in again.')
            return action(progress, row)
        return store.mutate(g.user['id'], checked)

    def admin(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            if not g.admin:
                return redirect(url_for('admin_login'))
            return fn(*args, **kwargs)
        return guarded

    def throttle(key, maximum, seconds=60):
        if not store.limit(key, maximum, seconds):
            abort(429, 'Too many attempts. Wait for the next rate-limit window and try again.')

    @app.before_request
    def initialize_request():
        g.user, g.admin = None, False
        if request.path.startswith('/assets/'):
            return
        if issues:
            return render_template('setup.html', issues=issues), 503
        store.initialize()
        if session.get('uid'):
            user = store.user(session['uid'])
            if user and user['active'] and user['epoch'] == session.get('epoch'):
                g.user = user
            else:
                session.clear()
        g.admin = hmac.compare_digest(session.get('admin', ''), admin_signature)
        if request.method == 'POST':
            supplied = request.form.get('csrf', '')
            expected = session.get('csrf', '')
            if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
                abort(400, 'This form expired. Reload the page and try again.')

    @app.context_processor
    def context():
        if not issues:
            session.setdefault('csrf', secrets.token_urlsafe(24))
        return dict(csrf=session.get('csrf', ''), viewer=g.get('user'), is_admin=g.get('admin', False), stages=stages, score=score, allowed=allowed)

    @app.after_request
    def headers(response):
        response.headers.update({
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'same-origin',
            'Cache-Control': 'private, no-store',
            'Content-Security-Policy': "default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        })
        if app.config['ONLINE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        app.logger.error('Database operation failed (%s)', type(error).__name__)
        return render_template('error.html', code=503, message='The database is temporarily unavailable. Please retry. Organizers: check the database connection and deployment logs.'), 503

    for code in (400, 401, 403, 404, 413, 429):
        app.register_error_handler(code, lambda error: (render_template('error.html', code=error.code, message=error.description), error.code))

    @app.get('/assets/<path:name>')
    def assets(name):
        return send_from_directory(ROOT / 'public/assets', name)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'stages': len(stages), 'storage': 'postgresql' if store.postgres else 'local-sqlite'}

    @app.get('/')
    def home():
        return render_template('home.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if not app.config['REGISTRATION_OPEN']:
            abort(403, 'Registration is closed for this event.')
        if request.method == 'POST':
            throttle('register:' + hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest(), 10, 3600)
            name = request.form.get('name', '').strip().lower()
            password = request.form.get('password', '')
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,31}', name) or name in ('admin', 'organizer'):
                flash('Choose a name of 3–32 lowercase letters, numbers, underscores or hyphens. Admin names are reserved.', 'error')
                return render_template('auth.html', mode='register'), 400
            if not 12 <= len(password) <= 128:
                flash('Use a password of 12–128 characters.', 'error')
                return render_template('auth.html', mode='register'), 400
            try:
                with store.engine.begin() as conn:
                    uid = conn.execute(users.insert().values(name=name, password_hash=generate_password_hash(password), progress=blank_progress(), epoch=0, active=1, created=time.time()).returning(users.c.id)).scalar_one()
            except IntegrityError:
                flash('That name is unavailable. Choose another.', 'error')
                return render_template('auth.html', mode='register'), 400
            session.clear()
            session.update(uid=uid, epoch=0)
            session.permanent = True
            return redirect(url_for('challenges'))
        return render_template('auth.html', mode='register')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            name = request.form.get('name', '').strip().lower()[:32]
            throttle('login:' + hashlib.sha256(name.encode()).hexdigest(), 10)
            with store.engine.connect() as conn:
                user = conn.execute(select(users).where(users.c.name == name)).mappings().first()
            if user and user['active'] and check_password_hash(user['password_hash'], request.form.get('password', '')):
                session.clear()
                session.update(uid=user['id'], epoch=user['epoch'])
                session.permanent = True
                return redirect(url_for('challenges'))
            flash('Name or password not recognized.', 'error')
            return render_template('auth.html', mode='login'), 403
        return render_template('auth.html', mode='login')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))

    @app.get('/challenges')
    @player
    def challenges():
        return render_template('challenges.html', progress=g.user['progress'])

    @app.get('/challenges/<int:sid>')
    @player
    def challenge(sid):
        if not 1 <= sid <= 6:
            abort(404)
        gate(sid)
        return render_template('challenge.html', stage=stages[sid-1], progress=g.user['progress'])

    @app.post('/challenges/<int:sid>/flag')
    @player
    def submit_flag(sid):
        if not 1 <= sid <= 6:
            abort(404)
        gate(sid)
        throttle(f"flag:{g.user['id']}", 20)
        correct = hmac.compare_digest(request.form.get('flag', '').strip().encode(), stages[sid-1]['flag'].encode())
        if not correct:
            store.audit(g.user['name'], f'wrong-flag:{sid}')
            flash('That flag does not match. Check the spelling and letter case.', 'error')
            return redirect(url_for('challenge', sid=sid))
        def solve(progress, row):
            if not row['active'] or row['epoch'] != session['epoch'] or not allowed(sid, progress):
                abort(403)
            if sid in progress['solves']:
                return False
            progress['solves'] = progress['solves'] + [sid]
            return True
        added = mutate_player(solve)
        if added:
            store.audit(g.user['name'], f'solved:{sid}')
        flash('Stage solved. Your progress is saved.' if added else 'You already solved this stage.', 'success')
        return redirect(url_for('challenges'))

    @app.post('/challenges/<int:sid>/hint/<int:hid>')
    @player
    def buy_hint(sid, hid):
        if not 1 <= sid <= 6 or hid not in (0, 1):
            abort(404)
        gate(sid)
        def purchase(progress, row):
            if not row['active'] or row['epoch'] != session['epoch'] or not allowed(sid, progress):
                abort(403)
            key = f'{sid}:{hid}'
            if key not in progress['hints']:
                progress['hints'] = progress['hints'] + [key]
        mutate_player(purchase)
        return redirect(url_for('challenge', sid=sid))

    @app.get('/scoreboard')
    def scoreboard():
        with store.engine.connect() as conn:
            rows = conn.execute(select(users.c.name, users.c.progress, users.c.created).where(users.c.active == 1)).mappings().all()
        leaders = sorted(rows, key=lambda u: (-score(u['progress']), u['created']))
        return render_template('scoreboard.html', leaders=leaders)

    @app.get('/archive/')
    @app.get('/archive/<name>')
    @player
    def archive(name='index.html'):
        if name == 'event-original.png':
            gate(2)
            return send_file(data / 'stage1/event-original.png', as_attachment=True, conditional=False)
        if name == 'pixel-note.txt':
            gate(2)
            return send_file(data / 'stage1/pixel-note.txt', mimetype='text/plain', conditional=False)
        if name not in {'index.html','staff.html','events.html','archive.html','notice-061.html','notice-062.html','notice-063.html'}:
            abort(404)
        body = (data / 'stage1' / name).read_text(encoding='utf-8')
        body = body.replace('href="/', 'href="/archive/')
        return render_template('archive.html', body=body)

    @app.route('/portal', methods=['GET', 'POST'])
    @player
    def portal():
        gate(3)
        fixtures = json.loads((data / 'portal/fixtures.json').read_text(encoding='utf-8'))
        if request.method == 'POST':
            throttle(f"review:{g.user['id']}", 15)
            pair = [request.form.get('transaction'), request.form.get('audit')]
            expected = json.loads((data / 'portal/private.json').read_text())['evidence_pair']
            if pair == expected:
                mutate_player(lambda p, row: p.update(reviewed=True))
                flash('Evidence corroborated. Submit the flag to unlock the cipher files.', 'success')
                return redirect(url_for('portal'))
            flash('That pair does not establish the authorization mismatch.', 'error')
        return render_template('portal.html', fixtures=fixtures, progress=g.user['progress'], flag=stages[2]['flag'] if g.user['progress']['reviewed'] else None)

    @app.get('/portal/audit')
    @player
    def audit_data():
        gate(3)
        records = json.loads((data / 'portal/fixtures.json').read_text())['audit']
        reference = request.args.get('reference')
        return [r for r in records if not reference or r['reference'] == reference]

    @app.get('/downloads/<name>')
    @player
    def download(name):
        if name in ('elias.enc.txt', 'training-memo.txt'):
            gate(4)
            if not g.user['progress']['reviewed']:
                abort(403, 'Complete the portal evidence review first.')
            return send_file(data / 'portal' / name, as_attachment=True, conditional=False)
        if name == 'northstar_evidence.img.gz':
            gate(5)
            return send_file(data / name, as_attachment=True, mimetype='application/gzip', conditional=False)
        abort(404)

    @app.route('/evidence', methods=['GET', 'POST'])
    @player
    def evidence():
        gate(6)
        paths = sorted(p.relative_to(data / 'linux').as_posix() for p in (data / 'linux').rglob('*') if p.is_file())
        selected = request.args.get('file', 'logs/maintenance.log')
        if selected not in paths:
            abort(404)
        raw = (data / 'linux' / selected).read_bytes()
        flag = stages[5]['flag'] if g.user['progress']['verified'] else None
        if request.method == 'POST':
            throttle(f"verify:{g.user['id']}", 5)
            answer = {k: request.form.get(k, '').strip() for k in ('release_id','route_id','service','event_id')}
            expected = json.loads((data / 'verifier/answer.json').read_text())['answer']
            if hmac.compare_digest(json.dumps(answer, sort_keys=True).encode(), json.dumps(expected, sort_keys=True).encode()):
                mutate_player(lambda p, row: p.update(verified=True))
                flash('Recovery route verified. Submit your final flag.', 'success')
                return redirect(url_for('evidence'))
            flash('The evidence does not match the trusted recovery record.', 'error')
        return render_template('evidence.html', paths=paths, selected=selected, content=raw.decode('utf-8'), checksum=hashlib.sha256(raw).hexdigest(), flag=flag)

    @app.get('/evidence/download')
    @player
    def evidence_download():
        gate(6)
        name = request.args.get('file', '')
        allowed_paths = {p.relative_to(data / 'linux').as_posix() for p in (data / 'linux').rglob('*') if p.is_file()}
        if name not in allowed_paths:
            abort(404)
        return send_file(data / 'linux' / name, as_attachment=True, conditional=False)

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            throttle('admin-login', 10)
            if hmac.compare_digest(request.form.get('password', '').encode(), app.config['ADMIN_PASSWORD'].encode()):
                session.clear()
                session['admin'] = admin_signature
                session.permanent = True
                return redirect(url_for('admin_home'))
            flash('Organizer password not recognized.', 'error')
            return render_template('auth.html', mode='admin'), 403
        return render_template('auth.html', mode='admin')

    @app.get('/admin')
    @admin
    def admin_home():
        with store.engine.connect() as conn:
            rows = conn.execute(select(users).order_by(users.c.created)).mappings().all()
            log = conn.execute(select(events).order_by(events.c.at.desc()).limit(50)).mappings().all()
        return render_template('admin.html', players=rows, log=log)

    @app.post('/admin/players/<int:uid>/<operation>')
    @admin
    def admin_player(uid, operation):
        user = store.user(uid)
        if not user or operation not in ('reset', 'toggle'):
            abort(404)
        if request.form.get('confirm') != user['name']:
            abort(400, 'Type the exact player name to confirm this action.')
        with store.transaction() as conn:
            values = {'epoch': users.c.epoch + 1}
            if operation == 'reset':
                values['progress'] = blank_progress()
            else:
                values['active'] = 0 if user['active'] else 1
            conn.execute(users.update().where(users.c.id == uid).values(**values))
        store.audit('organizer', f'{operation}:{user["name"]}')
        flash('Player updated. Their existing session has been invalidated.', 'success')
        return redirect(url_for('admin_home'))

    @app.get('/admin/export')
    @admin
    def export():
        with store.engine.connect() as conn:
            rows = conn.execute(select(users.c.name, users.c.progress, users.c.active, users.c.created)).mappings().all()
        report = [{**dict(u), 'score': score(u['progress'])} for u in rows]
        return send_file(io.BytesIO(json.dumps(report, indent=2).encode()), mimetype='application/json', as_attachment=True, download_name='northstar-progress.json')

    return app


app = create_app()
