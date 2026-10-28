"""Resolve versioned local source policies only when their full hash matches a release."""
import hashlib
import json
from pathlib import Path


def source_policy(contract_hash):
    directory=Path(__file__).resolve().parents[4]/'lakehouse/gold/contracts'
    geography=json.loads((directory/'reporting-geography-v1.json').read_text())
    for path in sorted(directory.glob('*.json')):
        contract=json.loads(path.read_text())
        if 'silver_table' not in contract:continue
        contract['geography']=geography
        checksum=hashlib.sha256(json.dumps((contract,),ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
        if checksum==contract_hash:return contract
    # An old unavailable policy must not inherit a hardcoded current threshold.
    return {}
