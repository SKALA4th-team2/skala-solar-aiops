# 전력신사업 플랫폼(der.kmos.kr) 공지 저장본(213건)을 읽는 도구.
# 원본: solar/rule/der_nor_all.json (원 조사 저장본), merged/verify/gap5/live_nor_post.json (2026-10-07 재조회본)
import json,re,html,sys
SRC={'saved':'(작업 폴더)/solar/rule/der_nor_all.json',
     'live':'(작업 폴더)/merged/verify/gap5/live_nor_post.json'}
which=sys.argv[1]
d=json.load(open(SRC[which],encoding='utf-8'))
items=d['normalNoticeList'] if isinstance(d,dict) else d
def txt(c):
    t=re.sub(r'<br\s*/?>|</p>','\n',c or ''); t=re.sub(r'<[^>]+>','',t); t=html.unescape(t)
    return re.sub(r'\n\s*\n+','\n',t).strip()
mode=sys.argv[2]
if mode=='count':
    print(which,'건수',len(items)); print('최신 5건:')
    for it in items[:5]: print(' ',it['reg_date'],it.get('sys_type_nm'),'|',it['sj'])
elif mode=='date':
    for it in items:
        if it['reg_date'] in sys.argv[3:]:
            print('=====',it['rn'],it['reg_date'],it.get('sys_type_nm'),'|',it['sj'],'| files',it.get('file_num'))
            print(txt(it['ctnt'])[:5000])
elif mode=='grep':
    pat=re.compile(sys.argv[3])
    for it in items:
        t=txt(it['ctnt'])
        if pat.search(it['sj']) or pat.search(t):
            print('=====',it['rn'],it['reg_date'],it.get('sys_type_nm'),'|',it['sj'])
            for m in pat.finditer(t):
                print('   ...',t[max(0,m.start()-200):m.end()+300].replace('\n',' / '))
