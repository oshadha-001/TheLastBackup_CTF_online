import gzip
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import select
from app import create_app, ROOT
from storage import users
from ctf.cipher import transform
from tools.solve import extract_png, recover_fat, timeline

PASSWORD = 'test-password-12345'


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'SECRET_KEY': 's'*64, 'ADMIN_PASSWORD': 'organizer-test-12345', 'DATABASE_URL': 'sqlite:///' + (tmp_path/'test.sqlite').as_posix(), 'ONLINE': False})


def csrf(client, path='/login'):
    client.get(path)
    with client.session_transaction() as s:
        return s['csrf']


def post(client, path, data=None):
    with client.session_transaction() as s:
        token = s['csrf']
    return client.post(path, data={'csrf': token, **(data or {})}, follow_redirects=True)


def register(app, name='analyst'):
    client = app.test_client()
    csrf(client, '/register')
    response = post(client, '/register', {'name': name, 'password': PASSWORD})
    assert response.status_code == 200
    return client


def uid(client):
    with client.session_transaction() as s:
        return s['uid']


def set_progress(app, client, solves, **extra):
    store = app.extensions['store']
    store.mutate(uid(client), lambda p, row: p.update(solves=solves, **extra))


def organizer(app):
    c = app.test_client()
    csrf(c, '/admin/login')
    assert post(c, '/admin/login', {'password': app.config['ADMIN_PASSWORD']}).status_code == 200
    return c


def test_entrypoint_and_missing_configuration():
    app = create_app({'SECRET_KEY': '', 'ADMIN_PASSWORD': '', 'DATABASE_URL': ''})
    r = app.test_client().get('/')
    assert r.status_code == 503
    assert b'SECRET_KEY' in r.data
    assert app.test_client().get('/assets/style.css').status_code == 200


def test_online_rejects_sqlite(tmp_path):
    app = create_app({'ONLINE': True, 'SECRET_KEY': 's'*64, 'ADMIN_PASSWORD': PASSWORD, 'DATABASE_URL': 'sqlite:///'+str(tmp_path/'x.db')})
    assert app.test_client().get('/').status_code == 503


def test_postgresql_connection_requires_tls_without_network():
    from storage import Store
    store = Store('postgresql://test:test@example.invalid/northstar?sslmode=disable')
    assert store.postgres
    assert store.engine.url.drivername == 'postgresql+psycopg'
    assert store.engine.url.query['sslmode'] == 'require'
    store.engine.dispose()


def test_rotated_admin_password_invalidates_session(app):
    old = organizer(app)
    cookie = old.get_cookie('northstar_online')
    new_settings = dict(app.config)
    new_settings['ADMIN_PASSWORD'] = 'a-new-organizer-secret-123'
    changed = create_app(new_settings)
    c = changed.test_client()
    c.set_cookie('northstar_online', cookie.value)
    assert c.get('/admin').status_code == 302


def test_public_pages_and_headers(app):
    c = app.test_client()
    for path in ('/', '/login', '/register', '/scoreboard', '/admin/login', '/health', '/assets/style.css'):
        r = c.get(path)
        assert r.status_code == 200, (path,r.status_code)
    r = c.get('/')
    assert r.headers['Cache-Control'] == 'private, no-store'
    assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']


@pytest.mark.parametrize('path', ['/challenges','/portal','/evidence','/downloads/northstar_evidence.img.gz','/archive/'])
def test_anonymous_redirects(app, path):
    assert app.test_client().get(path).location.endswith('/login')


def test_registration_validation_and_password_storage(app):
    c = app.test_client(); csrf(c,'/register')
    for name,password in [('x',PASSWORD),('admin',PASSWORD),('bad<script>',PASSWORD),('analyst','short')]:
        assert post(c,'/register',{'name':name,'password':password}).status_code == 400
    c = register(app)
    row = app.extensions['store'].user(uid(c))
    assert row['password_hash'] != PASSWORD
    other=app.test_client(); csrf(other,'/register')
    assert post(other,'/register',{'name':'analyst','password':PASSWORD}).status_code == 400


def test_csrf_and_logout_require_post(app):
    c=register(app)
    assert c.post('/challenges/1/flag', data={'flag': app.extensions['stages'][0]['flag']}).status_code == 400
    assert c.get('/logout').status_code == 405
    assert post(c,'/logout').status_code == 200
    assert c.get('/challenges').status_code == 302


def test_prerequisites_and_hidden_answers(app):
    c=register(app)
    for path in ('/challenges/2','/archive/event-original.png','/portal','/downloads/elias.enc.txt','/downloads/northstar_evidence.img.gz','/evidence'):
        assert c.get(path).status_code == 403, path
    html=c.get('/challenges').data
    for stage in app.extensions['stages']:
        assert stage['flag'].encode() not in html
        for h in stage['hints']:
            assert h['content'].encode() not in html


def test_all_six_stages_and_paid_hints(app,tmp_path):
    c=register(app)
    stages=app.extensions['stages']
    assert stages[0]['flag'].encode() in c.get('/archive/notice-062.html').data
    for sid,s in enumerate(stages,1):
        assert c.get(f'/challenges/{sid}').status_code == 200
        if sid==2:
            image=tmp_path/'event.png'; image.write_bytes(c.get('/archive/event-original.png').data)
            assert s['flag'] in extract_png(image) and '/portal' in extract_png(image)
        if sid==3:
            assert b'policy' not in c.get('/portal/audit').data
            assert b'Elias left' not in post(c,'/portal',{'transaction':'TX-211','audit':'AUD-211'}).data
            assert s['flag'].encode() in post(c,'/portal',{'transaction':'TX-217','audit':'AUD-217'}).data
        if sid==4:
            cipher=c.get('/downloads/elias.enc.txt'); assert cipher.status_code==200
            plaintext=transform(cipher.data.decode(),decrypt=True)
            assert s['flag'] in plaintext
        if sid==5:
            response=c.get('/downloads/northstar_evidence.img.gz')
            assert response.status_code==200 and len(response.data)<4_000_000
            raw=gzip.decompress(response.data)
            assert len(raw)==64*1024*1024
            assert hashlib.sha256(raw).hexdigest() in plaintext
            img=tmp_path/'evidence.img';img.write_bytes(raw)
            files=recover_fat(img)
            assert s['flag'] in files['_ANDOVER.TXT']
            assert timeline(files)['service']=='mn-sync'
        if sid==6:
            assert b'not a live shell' in c.get('/evidence').data
            assert s['flag'].encode() in post(c,'/evidence',{'release_id':'R17','route_id':'EXIT-04','service':'mn-sync','event_id':'EVT-024'}).data
        for h in range(2):
            assert post(c,f'/challenges/{sid}/hint/{h}').status_code==200
            assert post(c,f'/challenges/{sid}/hint/{h}').status_code==200
        assert post(c,f'/challenges/{sid}/flag',{'flag':s['flag'].lower()}).status_code==200
        assert sid not in app.extensions['store'].user(uid(c))['progress']['solves']
        assert post(c,f'/challenges/{sid}/flag',{'flag':s['flag']}).status_code==200
        assert post(c,f'/challenges/{sid}/flag',{'flag':s['flag']}).status_code==200
    p=app.extensions['store'].user(uid(c))['progress']
    assert p['solves']==list(range(1,7)) and len(p['hints'])==12
    assert b'955' in c.get('/scoreboard').data
    assert b'CASE CLOSED' in c.get('/challenges').data


def test_account_isolation_and_restart_persistence(app):
    a=register(app,'first'); b=register(app,'second')
    flag=app.extensions['stages'][0]['flag']
    post(a,'/challenges/1/flag',{'flag':flag})
    assert b.get('/challenges/2').status_code==403
    new=create_app(dict(app.config))
    c=new.test_client();csrf(c)
    assert post(c,'/login',{'name':'first','password':PASSWORD}).status_code==200
    assert c.get('/challenges/2').status_code==200


def test_paid_hints_and_solves_are_atomic(app):
    player=register(app)
    user_id=uid(player)
    def action(_):
        def mutate(p,row):
            if 1 not in p['solves']:p['solves']=p['solves']+[1]
            if '1:0' not in p['hints']:p['hints']=p['hints']+['1:0']
        app.extensions['store'].mutate(user_id,mutate)
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(action,range(12)))
    p=app.extensions['store'].user(user_id)['progress']
    assert p['solves']==[1] and p['hints']==['1:0']


def test_rate_limit_atomic_and_persistent(app):
    c=register(app); store=app.extensions['store']
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.limit('concurrency',5),range(12)))
    assert sum(results)==5
    other=create_app(dict(app.config)); other.test_client().get('/')
    assert not other.extensions['store'].limit('concurrency',5)


def test_verifier_rate_limit(app):
    c=register(app);set_progress(app,c,[1,2,3,4,5])
    for _ in range(5): assert post(c,'/evidence',{'route_id':'wrong'}).status_code==200
    assert post(c,'/evidence',{'route_id':'wrong'}).status_code==429


def test_admin_reset_disable_export(app):
    p=register(app);id=uid(p);set_progress(app,p,[1,2,3],reviewed=True)
    assert p.get('/admin').status_code==302
    a=organizer(app)
    assert b'analyst' in a.get('/admin/export').data
    assert b'password_hash' not in a.get('/admin/export').data
    assert post(a,f'/admin/players/{id}/reset',{'confirm':'wrong'}).status_code==400
    assert post(a,f'/admin/players/{id}/reset',{'confirm':'analyst'}).status_code==200
    assert app.extensions['store'].user(id)['progress']['solves']==[]
    assert p.get('/challenges').status_code==302
    post(a,f'/admin/players/{id}/toggle',{'confirm':'analyst'})
    csrf(p)
    assert post(p,'/login',{'name':'analyst','password':PASSWORD}).status_code==403


@pytest.mark.parametrize('path',['/.env','/private_data/challenges.json','/public/private_data/challenges.json','/evidence?file=../../app.py','/evidence/download?file=../../app.py','/downloads/answer.json','/archive/answer.json'])
def test_private_paths_and_traversal(app,path):
    c=register(app);set_progress(app,c,[1,2,3,4,5])
    assert c.get(path).status_code==404


def test_progress_cannot_be_forged_through_cookie(app):
    c=register(app)
    with c.session_transaction() as s:
        s['progress']={'solves':[1,2,3,4,5,6]}
        s['reviewed']=True
        s['admin']='yes'
    assert c.get('/evidence').status_code==403
    assert c.get('/admin').status_code==302


def test_download_bytes_and_explorer_selection(app):
    c=register(app);set_progress(app,c,[1,2,3,4,5])
    name='manifests/R17.sha256'
    r=c.get('/evidence/download?file='+name)
    assert r.data==(ROOT/'private_data/linux'/name).read_bytes()
    assert hashlib.sha256(r.data).hexdigest().encode() in c.get('/evidence?file='+name).data


def test_registration_can_be_closed(app):
    app.config['REGISTRATION_OPEN']=False
    assert app.test_client().get('/register').status_code==403


def test_vercel_metadata_and_public_assets():
    import tomllib
    cfg=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert cfg['tool']['vercel']['entrypoint']=='app:app'
    assert cfg['tool']['vercel']['scripts']['build']=='python build.py'
    for p in (ROOT/'public').rglob('*'):
        if p.is_file():
            assert b'FLAG{' not in p.read_bytes()
    assert not re.search(r'https?://(?:localhost|127\.0\.0\.1)', ''.join(p.read_text(encoding='utf-8') for p in (ROOT/'templates').glob('*.html')))
