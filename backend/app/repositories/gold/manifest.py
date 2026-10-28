"""Read v1 and dictionary-encoded v2 manifests; no Spark dependency."""

def decode(manifest):
    version=manifest.get('version')
    if version==1:return manifest
    if version!=2:raise ValueError('Unsupported timeline version')
    result=dict(manifest,version=1,segments=[])
    catalog=manifest['series_catalog']
    for segment in manifest['segments']:
        item=dict(segment)
        reference=item.pop('series_ref',None)
        if reference is not None:item['series']=catalog[reference]
        result['segments'].append(item)
    return result
