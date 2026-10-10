"""Run a separate local preview. All secrets/state live OUTSIDE the upload folder."""
import os
import secrets
import sys
from pathlib import Path
from dotenv import load_dotenv
from waitress import serve

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT.parent / 'Local-Only'
PRIVATE.mkdir(exist_ok=True)
config = PRIVATE / '.env'
if not config.exists():
    password = secrets.token_urlsafe(24)
    db = (PRIVATE / 'progress.sqlite').as_posix()
    config.write_text(f'SECRET_KEY={secrets.token_hex(32)}\nADMIN_PASSWORD={password}\nDATABASE_URL=sqlite:///{db}\n', encoding='utf-8')
    (PRIVATE / 'LOCAL-ACCESS.txt').write_text(f'Local preview: http://localhost:8002\nOrganizer: http://localhost:8002/admin\nOrganizer password: {password}\nThese are LOCAL credentials, not the Vercel environment settings.\n', encoding='utf-8')
load_dotenv(config)
sys.path.insert(0, str(ROOT))
if not (ROOT / 'private_data/challenges.json').exists():
    from build import build
    build()
from app import app
print('Preview: http://localhost:8002 | Organizer: /admin', flush=True)
print('Local credentials are in the sibling Local-Only/LOCAL-ACCESS.txt file.', flush=True)
serve(app, host='127.0.0.1', port=int(os.environ.get('LOCAL_PORT', '8002')))
