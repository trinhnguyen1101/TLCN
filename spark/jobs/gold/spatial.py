"""Cached regular-cell intersections in a spherical equal-area projection.

Area model: authalic sphere R=6371008.8m, cylindrical equal-area. Densify
edges in lon/lat before projecting (0.025 degree maximum segment).
This is an area weighting model, not an observation-accuracy measure.
"""
import math
from shapely import segmentize
from shapely.geometry import box
from shapely.ops import transform

METHOD = "spherical-cea-intersection-v1"
RADIUS = 6371008.8


def area(geometry):
    def project(x,y,z=None):
        try:
            return ([RADIUS*math.radians(v) for v in x],
                    [RADIUS*math.sin(math.radians(v)) for v in y])
        except TypeError:
            return RADIUS*math.radians(x),RADIUS*math.sin(math.radians(y))
    return transform(project,segmentize(geometry,0.025)).area


def weights(geometry,points,di,dj):
    if di <= 0 or dj <= 0 or not geometry.is_valid or geometry.is_empty:
        raise ValueError("Invalid geometry/grid")
    total=area(geometry)
    result=[]
    for point_id,lat,lon in points:
        cell=box(lon-di/2,max(-90,lat-dj/2),lon+di/2,min(90,lat+dj/2))
        if geometry.intersects(cell):
            overlap=area(geometry.intersection(cell))
            if overlap>0:
                result.append((int(point_id),overlap,total,overlap/total))
    if sum(row[3] for row in result)>1.00001:
        raise ValueError("Overlapping grid cells")
    return result
