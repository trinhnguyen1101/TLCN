"""Minimal Trino statement protocol client, bounded queries; no data fallback."""
import json
import time
from urllib.error import URLError,HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from app.repositories.base import DataSourceUnavailable


class TrinoClient:
    def __init__(self,uri,user='gold_api',timeout=30):
        self.uri=uri.rstrip('/')
        self.user=user
        self.timeout=timeout

    def query(self,sql):
        self.last_stats={}
        self.last_query_id=None
        deadline=time.monotonic()+self.timeout
        url=self.uri+'/v1/statement'
        data=sql.encode()
        columns=None
        result=[]
        try:
            while url:
                if time.monotonic()>=deadline:
                    raise DataSourceUnavailable('Trino query deadline exceeded')
                if urlsplit(url).netloc!=urlsplit(self.uri).netloc:
                    raise DataSourceUnavailable('Unexpected Trino nextUri host')
                request=Request(url,data=data,headers={'X-Trino-User':self.user,'X-Trino-Time-Zone':'UTC'})
                with urlopen(request,timeout=max(0.1,min(10,deadline-time.monotonic()))) as response:
                    page=json.load(response)
                self.last_stats=page.get('stats',self.last_stats)
                self.last_query_id=page.get('id',self.last_query_id)
                if page.get('error'):
                    raise DataSourceUnavailable('Trino query failed: '+page['error'].get('errorName','unknown'))
                if page.get('columns'):
                    columns=[c['name'] for c in page['columns']]
                if page.get('data'):
                    result.extend(dict(zip(columns,[v.replace(' UTC','Z').replace(' ','T',1) if isinstance(v,str) and v.endswith(' UTC') else v for v in row])) for row in page['data'])
                    if len(result)>200000:
                        raise DataSourceUnavailable('Gold query exceeded bounded result size')
                url=page.get('nextUri')
                data=None
            return result
        except (URLError,HTTPError,OSError,ValueError) as exc:
            raise DataSourceUnavailable('Gold Trino service unavailable') from exc
