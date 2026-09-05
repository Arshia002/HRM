#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, shutil, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
NAME=f'HRM-{VERSION}-Linux-Web-Test'
OUT=ROOT/'build-output'/'linux-web'
STAGE=OUT/NAME
FILES=['VERSION','LICENSE.txt','web','deploy/linux-web-test','src/sazmanhr','data/seed/sazmanhr-seed.sqlite']

def reject(path:Path):
    low=path.name.lower()
    if path.suffix.lower() in {'.xls','.xlsx','.ppt','.pptx','.enc','.key'}: return True
    if low in {'.env','first_login.txt','secrets.key','hrm.sqlite'}: return True
    if '__pycache__' in path.parts: return True
    return False

def main():
    shutil.rmtree(OUT,ignore_errors=True); STAGE.mkdir(parents=True)
    copied=[]
    for rel in FILES:
        src=ROOT/rel; dst=STAGE/rel
        if src.is_dir():
            for p in sorted(src.rglob('*')):
                if not p.is_file() or reject(p): continue
                r=p.relative_to(ROOT); target=STAGE/r; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target); copied.append(r.as_posix())
        else:
            dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst); copied.append(rel)
    manifest={'product':'HRM','version':VERSION,'purpose':'linux-web-test-not-for-production','files':[]}
    for rel in sorted(copied):
        p=STAGE/rel; raw=p.read_bytes(); manifest['files'].append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    (STAGE/'WEB-TEST-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    zip_path=OUT/f'{NAME}.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(STAGE.rglob('*')):
            if p.is_file(): z.write(p,Path(NAME)/p.relative_to(STAGE))
    digest=hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha=zip_path.with_suffix(zip_path.suffix+'.sha256'); sha.write_text(f'{digest}  {zip_path.name}\n',encoding='ascii')
    print(f'PASS: built {zip_path.name} ({len(manifest["files"])} payload files)')
    print(digest)
    return 0
if __name__=='__main__': raise SystemExit(main())
