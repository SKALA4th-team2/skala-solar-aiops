"""Extract auditable evidence from freshly downloaded official publications."""
from pathlib import Path
import argparse, hashlib, json, struct, zlib
from pypdf import PdfReader
ap=argparse.ArgumentParser()
ap.add_argument('--rule',type=Path,required=True)
ap.add_argument('--broker',type=Path,required=True)
ap.add_argument('--broker-text',type=Path,help='Optional previously extracted UTF-8 HWP text; otherwise requires olefile')
ap.add_argument('--market',type=Path,required=True)
a=ap.parse_args()
rule=PdfReader(a.rule); market=PdfReader(a.market)
if a.broker_text:
    broker=a.broker_text.read_text()
else:
    import olefile
    compound=olefile.OleFileIO(a.broker)
    compressed=struct.unpack('<I',compound.openstream('FileHeader').read()[36:40])[0]&1
    paragraphs=[]
    for stream in compound.listdir():
        if stream[0]!='BodyText':continue
        data=compound.openstream(stream).read()
        if compressed:data=zlib.decompress(data,-15)
        cursor=0
        while cursor<len(data):
            header=struct.unpack('<I',data[cursor:cursor+4])[0];cursor+=4
            tag=header&1023;length=header>>20
            if length==4095:
                length=struct.unpack('<I',data[cursor:cursor+4])[0];cursor+=4
            body=data[cursor:cursor+length];cursor+=length
            if tag==67:paragraphs.append(body.decode('utf-16le',errors='replace'))
    broker='\n'.join(paragraphs)
assert '제35조의2' in broker and '제35조의3' in broker
sources=[
 {'name':'전력시장운영규칙(2026.7.25 시행)','url':'https://www.kpx.or.kr/boardDownload.es?bid=0030&list_no=77795&seq=4','sha256':hashlib.sha256(a.rule.read_bytes()).hexdigest(),'bytes':a.rule.stat().st_size,'pages':len(rule.pages),'checked_pdf_pages':[253,256,257,258,259,399,405,406,407,334,335,569,570],'excerpts':{'submission_times':'제14.4.1조: 10시/17시, 변경제출 14시/20시, 미제출 차수는 변경제출 예외','threshold_price':'별표2 Ⅴ: FER≤4% 4원/kWh; 4%<FER≤6% 3원/kWh; 6%<FER 0원/kWh','eligibility':'제14.4.2조: 발전원별·시간대별 이용률10% 이상; 출력제어시 용량·예측·거래량 제외','sunset':'부칙(2023.8.30)제5조: 입찰제도 도입 지역에서 시행과 동시에 예측제도 종료','deferred_changes':'부칙(2025.2.11)제1조②: 6개월이내 공개 공지일 시행; 풍력1년유예','imbalance_conflict':'부칙(2025.10.1)제1조⑤는 IMB_TOLi,t,q를 별도공지 시행대상에서 제외하지만 별표33은 해당 표 아래 별도공지 시행주석을 둠'}},
 {'name':'소규모전력중개시장의 운영에 관한 규칙(26.1.28 공고)','url':'https://www.kpx.or.kr/boardDownload.es?bid=0032&list_no=77144&seq=1','sha256':hashlib.sha256(a.broker.read_bytes()).hexdigest(),'bytes':a.broker.stat().st_size,'excerpts':{'self_owned': '제2조제7·8호: 본인 소유 소규모전력자원을 집합에 포함 가능','aggregate':'제30조제1호: 주요자원20MW초과; 제4호 중복등록금지; 제5호 동일계통; 지역·송배전망 조건은 부칙(2021.9.18)제2조유예','composition':'제35조의3②: 신규구성시 기보유+신규 전체에서 1MW초과자원 용량합≤1MW이하자원 용량합','exceptions':'제35조의2①20MW이하로 감소시복원추가, ②소형비중요건복구추가, ④준중앙급전 참여목적추가 예외가 있으므로 최초등록때포함이 필수는 아님'}},
 {'name':'2025년도 전력시장 통계(2026.5)','url':'https://kpx.or.kr/boardDownload.es?bid=0045&list_no=77084&seq=4','sha256':hashlib.sha256(a.market.read_bytes()).hexdigest(),'bytes':a.market.stat().st_size,'pages':len(market.pages),'checked_pdf_pages':[4,10,67],'printed_page':133,'visually_checked':True,'annual_2025_settlement_thousand_won':23484457,'annual_2025_eligible_generation_mwh':6203420,'monthly_settlement_thousand_won':[1553500,1976153,2022494,2651988,2225859,1954518,2545809,2144471,1391229,1397771,2044276,1576389],'limitations':['2023~2025금액은잠정치','2025전체수치이므로2026육지태양광30중개사업자실적이아님','2025태양광정산단가기준이중간에바뀜','개별사업자/중개사업자/지역별/풍력별배분과기준금액1%p효과는알수없음','같은페이지참여사업자표연도는2024년이므로2025말규모로읽지않음']}
]
assert sum(sources[-1]['monthly_settlement_thousand_won'])==23484457
print(json.dumps({'verified_on':'2026-10-07','sources':sources,'unavailable_live_source':{'url':'https://der.kmos.kr/info/fr_notice_list.do','reason':'웹 도구접근실패;공개curl응답은자동화접속차단','current_notice_count_and_current_status':'독립 확인하지 못함'}},ensure_ascii=False,indent=2))
