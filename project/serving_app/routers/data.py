"""CSV를 검증한 뒤 저장하고 최근 업로드의 상태를 조회한다."""
import csv
from datetime import date
import io
import math
import os
import tempfile
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, Form
from serving_app import runtime as rt

from data.features import SEQ_LEN
from data.storage import UPLOAD_DIR, latest_upload
from serving_app.monitoring.drift_detector import WINDOW_SIZE
from serving_app.schemas import MAX_GENERATION_KWH, MAX_FORECAST_MJ

router = APIRouter(prefix="/data")
REQUIRED_COLUMNS = {"Date", "Close", "Volume"}
MIN_ROWS = SEQ_LEN + WINDOW_SIZE


def validate_csv(text: str,plant_id: str = rt.DEFAULT_PLANT) -> list[dict]:
    """저장 전과 상태 조회에 같은 검증을 적용한다. 원본 행은 고치지 않는다."""
    capacity=rt.plant(plant_id).get('capacity_kw')
    if not capacity:raise ValueError('설비 용량을 확인하지 못해 업로드할 수 없습니다.')
    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        headers = reader.fieldnames or []
        if not REQUIRED_COLUMNS.issubset(headers):
            raise ValueError(f"CSV에 {sorted(REQUIRED_COLUMNS)} 컬럼이 모두 있어야 합니다.")
        if len(headers) != len(set(headers)):
            raise ValueError("CSV 컬럼 이름이 중복되었습니다.")
        rows = []
        previous = None
        for number, row in enumerate(reader, start=2):
            if number>20001:raise ValueError('업로드는 최대 20,000행입니다.')
            if 'plant_id' in row and row['plant_id']!=plant_id:raise ValueError('파일의 plant_id가 요청과 다릅니다.')
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{number}행: 컬럼 수가 헤더와 다릅니다.")
            try:
                day = date.fromisoformat(row['Date'])
                if day.isoformat() != row['Date']:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError(f"{number}행: Date는 YYYY-MM-DD 형식의 유효한 날짜여야 합니다.") from None
            if previous is not None and (day - previous).days != 1:
                raise ValueError(f"{number}행: 날짜는 중복이나 빠진 날 없이 하루씩 이어진 오름차순이어야 합니다.")
            previous = day
            parsed = {"Date": day.isoformat()}
            for column in ('Close', 'Volume'):
                try:
                    value = float(row[column])
                except (ValueError, TypeError):
                    raise ValueError(f"{number}행: {column}은 빈 값이 아닌 숫자여야 합니다.") from None
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"{number}행: {column}은 유한한 0 이상의 숫자여야 합니다.")
                limit = capacity*24 if column == 'Close' else MAX_FORECAST_MJ
                if value > limit:
                    unit = 'kWh' if column == 'Close' else 'MJ/m²'
                    raise ValueError(f"{number}행: {column}은 {limit:g}{unit} 이하여야 합니다.")
                parsed[column] = value
            expected=row.get('Expected','').strip()
            if expected:
                try:value=float(expected)
                except ValueError:raise ValueError('Expected는 관측 기반 유한한 0 이상의 기대 발전량이어야 합니다.') from None
                if not math.isfinite(value) or value<0:raise ValueError('Expected 범위 오류')
                parsed['Expected']=value
            rows.append(parsed)
        if len(rows) < MIN_ROWS:
            raise ValueError(f"최소 {MIN_ROWS}행 이상의 데이터가 필요합니다.")
        return rows
    except csv.Error as exc:
        raise ValueError("CSV 형식이 올바르지 않습니다.") from exc


@router.post("/upload", responses={400: {"description": "CSV 인코딩·열·행 수·값·날짜 검증 실패"}})
async def upload(file: UploadFile = File(...),plant_id: str = Form(rt.DEFAULT_PLANT),kind: str = Form('generation_forecast_daily')):
    try:rt.plant(plant_id)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None
    if kind!='generation_forecast_daily':raise HTTPException(400,'지원하지 않는 자료 종류입니다.')
    raw = await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(413,'최대 업로드 크기는 5MB입니다.')
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "UTF-8로 인코딩된 CSV 파일만 업로드할 수 있습니다.") from None
    try:
        rows = validate_csv(text,plant_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    directory=os.path.join(UPLOAD_DIR,plant_id)
    os.makedirs(directory, exist_ok=True)
    filename = f"haic_{uuid.uuid4().hex}.csv"
    dest = os.path.join(directory, filename)
    # 완전히 쓴 CSV만 latest_upload에 보이도록 같은 디렉터리에서 원자적으로 교체한다.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=directory, suffix=".tmp", delete=False) as output:
            temporary = output.name
            output.write(text)
        os.replace(temporary, dest)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"filename": filename, "rows": len(rows),'plant_id':plant_id,'sha256':rt.sha(dest),'monitoring':'worker_scans_every_30_seconds'}


@router.get("/status", responses={409: {"description": "기존 업로드 파일 검증 실패, 재업로드 필요"}})
def status(plant_id: str = rt.DEFAULT_PLANT):
    try:rt.plant(plant_id)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None
    try:
        path = latest_upload(UPLOAD_DIR,plant_id=plant_id)
    except FileNotFoundError:
        return {"exists": False}
    try:
        with open(path, encoding="utf-8-sig") as source:
            rows = validate_csv(source.read(),plant_id)
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(409, f"최근 업로드 파일이 유효하지 않습니다. 올바른 CSV를 다시 업로드하세요: {exc}") from exc
    closes = [row['Close'] for row in rows]
    return {
        "exists": True,
        'plant_id':plant_id,'sha256':rt.sha(path),
        "filename": os.path.basename(path),
        "rows": len(rows),
        "start_date": rows[0]['Date'],
        "end_date": rows[-1]['Date'],
        "min_close": min(closes),
        "max_close": max(closes),
    }
