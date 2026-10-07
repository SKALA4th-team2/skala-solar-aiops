"""Download public portal CSVs without login/keys; evidence is stored only in output-dir."""
import argparse, csv, hashlib, json, re, urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
records={}
for id in ['15030079','15003687','15147894','15095366','15043404','15043405','15043406','15043408']:
 url=f'https://www.data.go.kr/data/{id}/fileData.do'
 try:
  html=urllib.request.urlopen(url,timeout=30).read().decode('utf-8')
  ss=re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S)
  d=json.loads(ss[0]);target=d['distribution'][0]['contentUrl']
  body=urllib.request.urlopen(target,timeout=30).read(); dest=a.output_dir/f'{id}.csv';dest.write_bytes(body)
  records[id]={'landing_url':url,'download_url':target,'sha256':hashlib.sha256(body).hexdigest(),'dateModified':d.get('dateModified'),'bytes':len(body)}
 except Exception as e:records[id]={'landing_url':url,'error':str(e)}
(a.output_dir/'sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(records,ensure_ascii=False,indent=2))
