"""Prepare the evaluated solar baselines; never seed stock-price example models."""
from pathlib import Path
import runpy
import sys
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':
    runpy.run_path(str(ROOT/'tools/aiops/bootstrap.py'),run_name='__main__')
