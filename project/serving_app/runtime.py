"""Local durable state shared by one API process and one training worker."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

DEFAULT_PLANT = 'hadong-sewage'
CONTRACT = os.getenv('SOLAR_MODEL_CONTRACT','solar_next_day_jma_msm_day1_v1')
PROJECT = Path(__file__).resolve().parents[1]


def root():
    path = Path(os.getenv('SOLAR_STATE_DIR', str(PROJECT/'data/runtime'))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temp,path)


def catalog():
    path=root()/'catalog.json'
    return read(path) if path.exists() else {'plants':{},'portfolios':{}}


def plant(plant_id=DEFAULT_PLANT):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,39}',plant_id): raise KeyError('Unknown plant')
    entry=catalog()['plants'].get(plant_id)
    if entry is None:
        if plant_id==DEFAULT_PLANT and not (root()/'catalog.json').exists():
            return dict(plant_id=plant_id,name='하동하수처리장',capacity_kw=55.,legacy=True)
        raise KeyError('Unknown plant')
    return entry


def plant_dir(plant_id):
    plant(plant_id)
    return root()/'models'/plant_id


def current(plant_id):
    path=plant_dir(plant_id)/'current.json'
    if not path.exists(): raise FileNotFoundError('No approved model for this plant')
    return read(path)


def version_dir(plant_id,version):
    if not str(version).isdigit(): raise ValueError('Invalid model version')
    return plant_dir(plant_id)/'versions'/str(version)


def model_name(plant_id): return ('solar-hourly-' if CONTRACT=='solar_hourly_24_jma_day2_v1' else 'solar-daily-')+plant_id


@contextmanager
def lock(name='operations'):
    """OS-released lock: no stale PID lock and no overlapping training processes."""
    path=root()/(name+'.lock')
    with path.open('a+b') as fp:
        fp.seek(0,2)
        if fp.tell()==0:fp.write(b'0');fp.flush()
        fp.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(fp.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,BlockingIOError) as exc:raise RuntimeError('Another worker or deployment operation is running') from exc
        try:yield
        finally:
            fp.seek(0)
            if os.name=='nt':msvcrt.locking(fp.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(fp,fcntl.LOCK_UN)


@contextmanager
def db():
    connection=sqlite3.connect(root()/'jobs.db',timeout=30)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS jobs(
      id TEXT PRIMARY KEY, plant_id TEXT NOT NULL, kind TEXT NOT NULL, end_date TEXT NOT NULL,
      status TEXT NOT NULL, payload TEXT NOT NULL, result TEXT, attempts INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(plant_id,kind,end_date));
    CREATE TABLE IF NOT EXISTS monitoring(plant_id TEXT PRIMARY KEY,end_date TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,plant_id TEXT,kind TEXT,payload TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS heartbeat(name TEXT PRIMARY KEY,updated_at TEXT NOT NULL,pid INTEGER);
    CREATE TABLE IF NOT EXISTS windows(plant_id TEXT PRIMARY KEY,end_date TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS predictions(
      id TEXT PRIMARY KEY,plant_id TEXT NOT NULL,model_version TEXT NOT NULL,kind TEXT NOT NULL,
      origin TEXT NOT NULL,input_sha256 TEXT NOT NULL,request TEXT NOT NULL,response TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS predictions_by_plant ON predictions(plant_id,created_at DESC);
    ''')
    try:yield connection;connection.commit()
    except Exception:connection.rollback();raise
    finally:connection.close()


def event(plant_id,kind,payload):
    import logging
    logging.getLogger('aiops').info('plant=%s event=%s %s',plant_id,kind,json.dumps(payload,ensure_ascii=False))
    with db() as conn:conn.execute('INSERT INTO events(plant_id,kind,payload,created_at) VALUES(?,?,?,?)',(plant_id,kind,json.dumps(payload,ensure_ascii=False),now()))

def configure_logging():
    import logging
    directory=Path(os.getenv('SOLAR_LOG_DIR',str(PROJECT/'logs')));directory.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('aiops');logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler=logging.FileHandler(directory/'aiops-hourly.log',encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'));logger.addHandler(handler)
    return directory

def record_prediction(plant_id,model_version,request,response,kind='forecast'):
    record_id=uuid.uuid4().hex;created=now()
    stored=dict(response,prediction_id=record_id,recorded_at=created)
    origin=response.get('origin') or response['timestamps'][0]
    with db() as conn:
        conn.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?)',(record_id,plant_id,str(model_version),kind,origin,digest(request),json.dumps(request,allow_nan=False),json.dumps(stored,allow_nan=False),created))
    return stored


def enqueue(plant_id,rows,base_version,reason='drift'):
    end=rows[-1]['date'];payload=dict(rows=rows,base_version=str(base_version),reason=reason,data_sha256=digest(rows))
    job_id=uuid.uuid4().hex
    with db() as conn:
        conn.execute('INSERT OR IGNORE INTO jobs(id,plant_id,kind,end_date,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                     (job_id,plant_id,'fine_tune',end,'queued',json.dumps(payload),now(),now()))
        row=dict(conn.execute('SELECT * FROM jobs WHERE plant_id=? AND kind=? AND end_date=?',(plant_id,'fine_tune',end)).fetchone())
    return job_view(row)


def job_view(row):
    row=dict(row);row.pop('payload',None)
    if row.get('result'):row['result']=json.loads(row['result'])
    return row


def get_job(job_id):
    with db() as conn:
        row=conn.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None:raise KeyError('Unknown job')
        return job_view(row)
