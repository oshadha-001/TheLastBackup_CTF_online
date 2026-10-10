"""Generate immutable, private challenge data at build time, never on requests."""
import gzip
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from evidence_source import build as generate

ROOT = Path(__file__).resolve().parent


def build():
    target = ROOT / 'private_data'
    target.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='northstar-build-') as temporary:
        release = Path(temporary)
        generate(release, '/portal')
        for folder in ('stage1', 'portal', 'linux', 'verifier'):
            shutil.copytree(release / folder, target / folder, dirs_exist_ok=True)
        image = (release / 'handouts/northstar_evidence.img').read_bytes()
        compressed = gzip.compress(image, compresslevel=9, mtime=0)
        assert len(compressed) < 4_000_000, 'Evidence exceeds function response limit'
        (target / 'northstar_evidence.img.gz').write_bytes(compressed)
        challenges = json.loads((release / 'organizer/challenges.json').read_text(encoding='utf-8'))
        descriptions = [
            'Maya Nair disappeared from the directory. Compare the preserved event register with three archived notices. Match both the case and the meeting time.',
            'The original event image carries Maya\u2019s hidden message. Examine its red-channel least-significant bits. Preserve the original PNG; screenshots will not work.',
            'Follow approval reference APR-0217. Compare the role policy, transactions and audit events, then submit the pair that proves an unauthorized approval.',
            'Use the training memo to decrypt Elias\u2019s warning. Keep the recovered image filename and SHA-256 for the next stage.',
            'Download and decompress the FAT16 evidence image. Check its SHA-256 against the warning, recover the deleted handover, and correlate the missing seventeen minutes.',
            'Use the browser evidence explorer to examine the preserved Linux files. Authenticate a manifest with the hash recovered in Stage 5, verify its route, and submit the four final identifiers. This online adaptation does not provide a live SSH shell.',
        ]
        for i, stage in enumerate(challenges):
            stage['id'] = i + 1
            stage['title'] = stage['name'].split(' · ', 1)[-1]
            stage['description'] = descriptions[i]
            stage['difficulty'] = ['Easy', 'Easy', 'Moderate', 'Moderate', 'Moderate–Hard', 'Hard'][i]
        (target / 'challenges.json').write_text(json.dumps(challenges, indent=2), encoding='utf-8')
        register = {'image_sha256': hashlib.sha256(image).hexdigest(), 'image_bytes': len(image), 'compressed_bytes': len(compressed)}
        (target / 'release.json').write_text(json.dumps(register, indent=2), encoding='utf-8')
    print(f'Built six stages; compressed evidence download {len(compressed):,} bytes.')


if __name__ == '__main__':
    build()
