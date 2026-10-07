"""Repository-scoped GitHub transport. Credentials stay in memory and never enter output."""
import argparse,json,os,subprocess,urllib.request,urllib.parse
from pathlib import Path
REPO='SangMyeong5426/skala-solar-aiops'
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        result=super().redirect_request(req,fp,code,msg,headers,newurl)
        if result and urllib.parse.urlparse(req.full_url).netloc!=urllib.parse.urlparse(newurl).netloc:result.remove_header('Authorization')
        return result
def token():
    value=os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
    if value:return value
    result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True)
    credentials=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not credentials.get('password'):raise RuntimeError('GitHub authentication unavailable')
    return credentials['password']
def api(endpoint,method='GET',body=None,upload=None,download=None):
    if not endpoint.startswith('/repos/'+REPO+'/') and endpoint!='/repos/'+REPO:raise ValueError('Only this repository is supported')
    base='https://uploads.github.com' if upload else 'https://api.github.com'
    headers={'Authorization':'Bearer '+token(),'Accept':'application/octet-stream' if download else 'application/vnd.github+json','User-Agent':'solar-submission','X-GitHub-Api-Version':'2022-11-28'}
    data=None
    if upload:data=Path(upload).read_bytes();headers['Content-Type']='application/zip'
    elif body is not None:data=json.dumps(body).encode();headers['Content-Type']='application/json'
    req=urllib.request.Request(base+endpoint,data=data,headers=headers,method=method)
    with urllib.request.build_opener(SafeRedirect()).open(req,timeout=180) as response:
        if download:
            target=Path(download);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(response.read());return dict(downloaded=str(target),bytes=target.stat().st_size)
        raw=response.read();return json.loads(raw) if raw else {}
def main():
    p=argparse.ArgumentParser();p.add_argument('endpoint');p.add_argument('--method',default='GET');p.add_argument('--body-file');p.add_argument('--upload');p.add_argument('--download');p.add_argument('--out');a=p.parse_args()
    body=json.loads(Path(a.body_file).read_text(encoding='utf-8')) if a.body_file else None
    d=api(a.endpoint,a.method,body,a.upload,a.download)
    if a.out:Path(a.out).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');print('Saved response:',a.out)
    else:print(json.dumps(d,ensure_ascii=False))
if __name__=='__main__':main()
