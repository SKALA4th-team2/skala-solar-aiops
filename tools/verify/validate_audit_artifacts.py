"""Check the nine audit documents, verification syntax/results and protected input hashes.
python tools/verify/validate_audit_artifacts.py --repo . [--protected-manifest /tmp/before.json]
"""
import argparse, hashlib, json, re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--protected-manifest',type=Path);a=p.parse_args();r=a.repo.resolve()
names=['T1-plant-data.md','T2-history-outage.md','T3-weather-input.md','T4-performance-gate.md','T5-drift-demo.md','T6-scheme.md','T7-value.md','overview.md','summary.md']
errors=[];docs=r/'docs/research/merged'
for name in names:
 f=docs/name;s=f.read_text()
 if s.count('## 반박 검증에서 고친 것')!=1:errors.append(f'{name}: missing/duplicate audit section')
 if '**반박 검증 전**' in s or '**반박 검증을 받지 않은 결과다.**' in s:errors.append(f'{name}: stale status')
 table=[];fenced=False
 for n,line in enumerate(s.splitlines()+[''],1):
  if line.startswith('```'):fenced=not fenced
  if not fenced and line.startswith('|'):
   table.append((n,line))
  else:
   if len(table)>1 and re.search(r'\|\s*:?-{3}',table[1][1]):
    cells=lambda t:len(re.split(r'(?<!\\)\|',t))-2
    width=cells(table[0][1])
    for j,row in table[1:]:
     if cells(row)!=width:errors.append(f'{name}:{j}: table width {cells(row)} != {width}')
   table=[]
 for target in re.findall(r'\]\(([^)]+)\)',s):
  if 'tools/verify/' not in target or target.startswith('http'):continue
  dst=(f.parent/target).resolve()
  if not dst.is_file():errors.append(f'{name}: missing evidence {target}')
scripts=list((r/'tools/verify').glob('*.py'))
for f in scripts:
 try:compile(f.read_text(),str(f),'exec')
 except SyntaxError as e:errors.append(str(e))
results=list((r/'tools/verify').glob('*.json'))
for f in results:
 try:json.loads(f.read_text())
 except Exception as e:errors.append(f'{f.name}: {e}')
protected=0
if a.protected_manifest:
 for path,expected in json.loads(a.protected_manifest.read_text()).items():
  f=r/path;protected+=1
  if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:errors.append(f'protected changed: {path}')
print(json.dumps({'documents':len(names),'compiled_scripts':len(scripts),'parsed_json':len(results),'protected_files':protected,'errors':errors},ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
