"""Small internal-Compose Trino client for isolated stack benchmarks."""
import json
import time
from urllib.request import Request,urlopen


def query(sql,timeout=30):
    url='http://trino:8080/v1/statement';data=sql.encode();columns=None;rows=[];begin=time.monotonic()
    while url:
        if time.monotonic()-begin>timeout:
            try:urlopen(Request(url,method='DELETE',headers={'X-Trino-User':'gold_benchmark'}),timeout=2).close()
            finally:raise TimeoutError('Bounded benchmark query timed out')
        with urlopen(Request(url,data=data,headers={'X-Trino-User':'gold_benchmark','X-Trino-Time-Zone':'UTC'}),timeout=10) as response:page=json.load(response)
        if 'error' in page:raise RuntimeError(page['error'].get('message',page['error']))
        if 'columns' in page:columns=[c['name'] for c in page['columns']]
        if 'data' in page:rows.extend(dict(zip(columns,row)) for row in page['data'])
        if len(rows)>50000:raise ValueError('Benchmark response exceeds bounded rows')
        url=page.get('nextUri');data=None
    return rows
