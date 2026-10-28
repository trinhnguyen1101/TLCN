from datetime import timedelta
import calendar
import hashlib
import json
from pyspark.sql import functions as F
from shapely import wkb
from shapely.ops import unary_union
from runtime import stable_id
from spatial import area, weights, METHOD
from aqi.engine import VN,HOUR
from aqi.reference import METHOD_VERSION,REFERENCE_SHA256,REFERENCE_URL,BREAKPOINTS,INDICES


def build_geography(build):
    admins=build.read("admin_unit").filter("is_current").collect()
    roots=[r for r in admins if r.parent_admin_unit_version_id is None]
    geography=build.contract['geography']
    expected=geography['expected_root_count']
    if expected!=34 or len(roots)!=expected or len({r.admin_code for r in roots})!=expected:
        raise ValueError("Reporting snapshot requires exactly 34 unique root provinces")
    bycode={r.admin_code:r for r in admins}
    links=geography['archipelago_parent_codes']
    for child,parent in links.items():
        if child not in bycode or bycode[child].parent_code!=parent:
            raise ValueError("Invalid archipelago hierarchy")
    ids=[r.admin_unit_version_id for r in roots]+[bycode[c].admin_unit_version_id for c in links]
    boundaries=build.read("admin_boundary").filter(F.col("admin_unit_version_id").isin(ids))
    success=build.read("ingestion_run").filter("status='succeeded'").select(F.col("run_id").alias("ingestion_run_id"))
    records=boundaries.join(success,"ingestion_run_id","inner").collect()
    groups={}
    for r in records:
        if r.srid!=4326:
            raise ValueError("Geography must use EPSG:4326")
        geometry=wkb.loads(bytes(r.boundary_wkb))
        if not geometry.is_valid or geometry.is_empty:
            raise ValueError("Invalid Silver boundary")
        groups.setdefault(r.admin_unit_version_id,[]).append(geometry)
    geometries={key:unary_union(shapes) for key,shapes in groups.items()}
    for key in ids:
        if key not in geometries:
            raise ValueError("Missing reporting geometry: "+key)
    # Union is deliberate: if the parent already includes its islands, do not add area twice.
    for child,parent in links.items():
        pid,cid=bycode[parent].admin_unit_version_id,bycode[child].admin_unit_version_id
        geometries[pid]=unary_union([geometries[pid],geometries[cid]])
    rid=build.release_id
    adminrows=[]
    for row in roots+[bycode[c] for c in links]:
        geometry=geometries[row.admin_unit_version_id]
        adminrows.append(dict(release_id=rid,admin_unit_version_id=row.admin_unit_version_id,
                              admin_code=row.admin_code,name_vi=row.name_vi,
                              parent_admin_unit_version_id=row.parent_admin_unit_version_id,
                              admin_level=row.admin_level,snapshot_date=row.snapshot_date,
                              boundary_hash=hashlib.sha256(geometry.wkb).hexdigest()))
    build.write("dim_admin_unit",adminrows)
    locations=[]
    components=[]
    build.regions=[]
    for row in roots:
        parent_id=row.admin_unit_version_id
        geometry=geometries[parent_id]
        islands=[bycode[c] for c,p in links.items() if p==row.admin_code]
        mainland=geometry.difference(unary_union([geometries[i.admin_unit_version_id] for i in islands])) if islands else geometry
        pieces=[("mainland",row.name_vi,mainland)]+[("archipelago",i.name_vi,geometries[i.admin_unit_version_id]) for i in islands]
        for kind,name,piece in pieces:
            digest=hashlib.sha256(piece.wkb).hexdigest()
            components.append(dict(release_id=rid,geo_component_id=stable_id("component-v1",parent_id,kind,digest),
                                   parent_admin_unit_version_id=parent_id,component_kind=kind,component_name=name,
                                   geometry_hash=digest,area_m2=area(piece),boundary_wkb=bytes(piece.wkb),
                                   geography_policy_version=geography['policy_version']))
        location_id=stable_id("province-location-v1",parent_id,hashlib.sha256(geometry.wkb).hexdigest())
        locations.append(dict(release_id=rid,location_id=location_id,admin_unit_version_id=parent_id,
                              name=row.name_vi,admin_code=row.admin_code,location_kind="province",
                              spatial_representation="area_estimate",mapping_status="verified_snapshot"))
        build.regions.append((location_id,geometry))
    build.write("dim_geo_component",components)
    build.write("dim_location",locations)
    return locations


def build_time_method(build):
    rid=build.release_id
    hours=[]
    # Include halo in spine so lineage/windows can refer to prior day.
    h=build.start-11*HOUR
    while h<build.end:
        local=h.astimezone(VN)
        hours.append(dict(release_id=rid,hour_start_utc=h,hour_end_utc=h+HOUR,
                          date_utc=h.date(),date_vn=local.date(),hour_vn=local.hour))
        h+=HOUR
    build.write("dim_hour",hours)
    dates=sorted({h["date_vn"] for h in hours}|{h["date_utc"] for h in hours})
    build.write("dim_date",[dict(release_id=rid,calendar_date=d,calendar_year=d.year,
                calendar_month=d.month,calendar_quarter=(d.month-1)//3+1,
                days_in_month=calendar.monthrange(d.year,d.month)[1]) for d in dates])
    policies=dict(nowcast="PDF p4: normalized for w>0.5, unnormalized sum 0.5^i*ci for w=0.5",
                  rounding="decimal half up; do not round concentrations/weight",terminal=">=last cutoff:500; O3 8h >400 ineligible",
                  daily="project policy:24/24 hourly means; O3 all24 full rolling8h windows",
                  hourly="PM>=2/3 recent slots; requires eligible PM for overall",
                  station_reference="requires explicit instrument/reference eligibility in Silver adapter",
                  examples="PDF NO2 118.7 example prints60; exact59.35 rounds59; formula takes precedence")
    build.write("dim_aqi_method",[dict(release_id=rid,method_version=METHOD_VERSION,reference_url=REFERENCE_URL,
                reference_sha256=REFERENCE_SHA256,calendar_timezone="Asia/Ho_Chi_Minh",policies_json=json.dumps(policies,ensure_ascii=False))])
    refs=[]
    for p,points in BREAKPOINTS.items():
        pollutant="o3" if p=="o3_8h" else p
        bases=["max8h"] if p=="o3_8h" else (["nowcast12h","mean24h"] if p.startswith("pm") else ["mean1h","max1h"])
        for basis in bases:
            for i,(c,index) in enumerate(zip(points,INDICES)):
                refs.append(dict(release_id=rid,method_version=METHOD_VERSION,pollutant=pollutant,
                                 averaging_basis=basis,breakpoint_order=i,concentration_breakpoint=float(c),index_breakpoint=index))
    build.write("ref_aqi_breakpoint",refs)


def build_spatial(build):
    rid=build.release_id
    grids=build.read("cams_grid").collect()
    points=build.read("cams_grid_point").collect()
    all_keys=[]
    for grid in grids:
        if grid.srid!=4326 or grid.grid_type!="regular_ll":
            raise ValueError("Only validated regular lon/lat grid supported")
        gp=[(p.grid_point_id,p.latitude,p.longitude) for p in points if p.grid_id==grid.grid_id]
        expected=grid.row_count*grid.column_count
        if sorted(p[0] for p in gp)!=list(range(expected)) or len({(p[1],p[2]) for p in gp})!=expected:
            raise ValueError("Grid indices/coordinates incomplete")
        for location,geometry in build.regions:
            boundary_hash=hashlib.sha256(geometry.wkb).hexdigest()
            key=stable_id("spatial-cache-v1",grid.grid_id,boundary_hash,METHOD,
                          grid.longitude_increment,grid.latitude_increment)
            all_keys.append(key)
            existing=build.spark.table(build.prefix+"bridge_cams_region_weight").filter(F.col("cache_key")==key)
            if existing.limit(1).count():
                continue
            rows=[]
            for point_id,overlap,total,fraction in weights(geometry,gp,grid.longitude_increment,grid.latitude_increment):
                rows.append(dict(cache_key=key,grid_id=grid.grid_id,grid_point_id=point_id,location_id=location,
                                 boundary_hash=boundary_hash,method_version=METHOD,intersection_area_m2=overlap,
                                 region_area_m2=total,area_fraction=fraction,latitude_increment=grid.latitude_increment,
                                 longitude_increment=grid.longitude_increment))
            if rows:
                frame=build.frame("bridge_cams_region_weight",rows)
                frame.coalesce(1).writeTo(build.prefix+"bridge_cams_region_weight").append()
    build.bridge=(build.spark.table(build.prefix+"bridge_cams_region_weight")
                  .filter(F.col("cache_key").isin(all_keys)))
    if build.bridge.groupBy("grid_id","grid_point_id","location_id").count().filter("count>1").count():
        raise ValueError("Spatial cache duplicate key")
    build.outputs.append("bridge_cams_region_weight")
