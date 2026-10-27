"""Read-only spot check of city-proxy mapping against existing Silver polygons."""

import sys
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DataQualityError, create_spark
from supabase_bronze_to_silver import province_lookup, normal_name
from shapely import wkb
from shapely.geometry import Point
import psycopg
from psycopg.rows import dict_row


def main():
    spark = create_spark("supabase-province-proxy-check")
    try:
        url = urlsplit(os.environ["AWS_CONNECTION_STRING"][5:])
        query = parse_qs(url.query)
        with psycopg.connect(host=url.hostname, port=url.port, dbname=url.path.lstrip("/"),
                             user=query["user"][0], password=query["password"][0], sslmode="require",
                             options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
            points = conn.execute("SELECT location_id::text, location_key, province_name, "
                                  "latitude, longitude FROM public.api_ninjas_locations "
                                  "WHERE is_active ORDER BY location_key").fetchall()
        provinces = {normal_name(row.name_vi): row for row in
                     spark.table("nessie.silver.admin_unit").filter("is_current AND parent_code IS NULL").collect()}
        boundaries = {row.admin_unit_version_id: wkb.loads(bytes(row.boundary_wkb)) for row in
                      spark.table("nessie.silver.admin_boundary").collect()
                      if row.admin_unit_version_id in {p.admin_unit_version_id for p in provinces.values()}}
        for loc in points:
            province = provinces[normal_name(loc["province_name"])]
            shape = boundaries[province.admin_unit_version_id]
            point = Point(loc["longitude"], loc["latitude"])
            if not shape.covers(point):
                print("outside_proxy=" + loc["location_key"] + " distance_deg=" +
                      str(round(shape.distance(point), 6)) + " province=" + province.name_vi)
        mapped = province_lookup(spark, points)
        assert len(mapped) == len(points)
        khanh_hoa = next(loc for loc in points if loc["location_key"] == "khanh-hoa")
        mapping = mapped[khanh_hoa["location_id"]]
        assert mapping[2] == "province_name_boundary_tolerance_250m"
        assert 0 < mapping[4] <= 250
        print("khanh_hoa_distance_m=" + str(round(mapping[4], 1)))
        far_away = dict(khanh_hoa, location_id="far-away", longitude=106.0, latitude=11.0)
        try:
            province_lookup(spark, [far_away])
        except DataQualityError:
            pass
        else:
            raise AssertionError("A distant point was accepted")
        print("supabase_province_proxy_check=ok count=" + str(len(points)))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
