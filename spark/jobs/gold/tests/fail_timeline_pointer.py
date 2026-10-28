"""Test-only crash after immutable timeline insert, before atomic pointer commit."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import publication
from run import execute,parse_args
args=parse_args()
if not args.schema.startswith('gold_test'):raise ValueError('Failure injection requires test namespace')
def fail(*args,**kwargs):raise RuntimeError('Injected failure after timeline registry, before timeline pointer')
publication.point=fail
execute(args)
