#!/usr/bin/python
# -*- coding: utf-8 -*-

#
# Licensed under the GNU General Public License Version 2 or later
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# Copyright (C) 2012-2013
#    Francisco Dos Santos <f.dos.santos@free.fr>

import sys
import re
import os
import datetime
from osgeo import gdal, ogr, osr
from shapeu import ShapeUtil
from ringue import FindClosedRings
import logo
import uganda_config

# GDAL 1.9.0 can do the ISO8859-1 to UTF-8 recoding for us
# but will do it ourself to be backward compatible
gdal.SetConfigOption('SHAPE_ENCODING', '')


#
# Definitions
#
regexp = re.compile("([- ()/])")   # Separators in name
preposition = (
    "De", "Do", "Da", "Dos", "Das",
    "E", "A", "O", "Os", "D'", "Ao", u'\xC0'   # A with grave accent (probably useless, this is words to keep in lowercase)
)


#
# Functions
#

def convertname(name):
    """
    Convert and normalize name from ISO8859 string to UTF8 string.

    Earch word in the name are capitalized except for some portuguese
    preposition.
    """

    name = name.decode("ISO8859")
    tokens = regexp.split(name)   # List of word, separator, ...

    # Finish the split job, we need a list of pair elements (for loop below)
    # depends on if the string end with a separator or not, there is one
    # element we can discard or there is one element missing
    if tokens[-1]:
        tokens.append("")   # ends with word and no separator
    else:
        del tokens[-1]      # last word empty, ends with a separator

    # First letter in upper case except some known words after first word
    for i in xrange(0, len(tokens), 2):
        tok = tokens[i].capitalize()
        if i > 0:
            if tok in preposition:
                tok = tok.lower()
        tokens[i] = tok

        # Special case: eat the space following a d' preposition
        if tok == "d'" and tokens[i+1] == " ":
            tokens[i+1] = ""

    # Return string in UTF8
    name = ''.join(tokens)
    return name.encode("UTF8")


def read_UGANDA(filename, shapeu):
    """
    Read the shapefile and build the geometry.

    We expect only 1 layer of type polygon, coordinates are reprojected
    to WGS84.
    """

    shapefile = ogr.Open(filename)
    layer = shapefile.GetLayer(0)
    layerDef = layer.GetLayerDefn()

    # Verify field and geometry type
    for possiblefields in [ ("DNAME_2010", "SUBREGION"), ("region", "place") ]:
        for field in possiblefields:
            if layerDef.GetFieldIndex(field) == -1:
                break
        else:
            break
    else:
        raise logo.ERROR("Important field missing, where is the admin area name ?")
    if layerDef.GetGeomType() != ogr.wkbPolygon:
        raise logo.ERROR("Not a POLYGON file")

    # Reproject on the fly
    srcSpatialRef = layer.GetSpatialRef()
    dstSpatialRef = osr.SpatialReference()
    dstSpatialRef.SetWellKnownGeogCS('WGS84')
    transform = osr.CoordinateTransformation(srcSpatialRef, dstSpatialRef)

    # Read each polygon and build the connection arrays (point, segment, line)
    logo.starting("Geometry read", layer.GetFeatureCount())
    for featnum in xrange(layer.GetFeatureCount()):
        logo.progress(featnum)
        feature = layer.GetFeature(featnum)
        geometry  = feature.GetGeometryRef()
        newgeometry = geometry.Clone()
        newgeometry.Transform(transform)

        # MultiPolygon: only deal with first polygon
        # Polygon: Outer Ring (1) followed by Inner Rings (n-1)
        # we create all segments for outer ring only, drop
        # inner rings (very exotic ...)
        if newgeometry.GetGeometryType() == ogr.wkbMultiPolygon:
            logo.DEBUG("Feature %d with %d polygons" % (featnum,
                       newgeometry.GetGeometryCount()))
            ring = newgeometry.GetGeometryRef(0).GetGeometryRef(0)
        else:
            logo.DEBUG("Feature %d with %d rings" % (featnum,
                       newgeometry.GetGeometryCount()))
            ring = newgeometry.GetGeometryRef(0)
        lon1, lat1 = ring.GetPoint_2D(0)
        for pnt in xrange(1, ring.GetPointCount()):
            lon2, lat2 = ring.GetPoint_2D(pnt)
            shapeu.makeSegment(lon1, lat1, lon2, lat2)
            lon1, lat1 = lon2, lat2
    logo.ending()


def admin_UGANDA(filename, shapeu, admins):
    """
    Reread the shapefile and build each administrative entity.

    Geometry described by a set of lines, attributes converted to UTF8.
    """

    shapefile = ogr.Open(filename)
    layer = shapefile.GetLayer(0)
    layerDef = layer.GetLayerDefn()

    # Reproject on the fly
    srcSpatialRef = layer.GetSpatialRef()
    dstSpatialRef = osr.SpatialReference()
    dstSpatialRef.SetWellKnownGeogCS('WGS84')
    transform = osr.CoordinateTransformation(srcSpatialRef, dstSpatialRef)

    # Extract attributes from district or merged file
    if layerDef.GetFieldIndex("SUBREGION") == -1:
        fieldregion = "region"
        fielddistrict = "place"
    else:
        fieldregion = "SUBREGION"
        fielddistrict = "DNAME_2010"

    # Change here the admin area level !!!
    LevelSubRegion = 6
    LevelDistrict = 7

    # Reread each polygon and create the right administrative area
    logo.starting("Attributes read", layer.GetFeatureCount())
    for featnum in xrange(layer.GetFeatureCount()):
        logo.progress(featnum)
        feature = layer.GetFeature(featnum)
        geometry  = feature.GetGeometryRef()
        newgeometry = geometry.Clone()
        newgeometry.Transform(transform)
        subregion = feature.GetField(fieldregion)
        district  = feature.GetField(fielddistrict)
        logo.DEBUG("Feature %d SUBREGION='%s' DISTRICT='%s'" % (
                   featnum, subregion, district))

        # Subregion / District
        if district is None:
            # Merged file and polygon is region
            key_admin1 = None
            key_admin2 = "SR_" + subregion.upper()
            if key_admin2 not in admins:
                admins[key_admin2] = { "name" : convertname(subregion),
                                       "level" : LevelSubRegion,
                                       "inner" : set(),
                                       "outer" : set(),
                                     }
        elif subregion is None:
            # Merged file and polygon is district
            key_admin1 = None
            key_admin2 = "DI_" + district.upper()
            if key_admin2 not in admins:
                admins[key_admin2] = { "name" : convertname(district),
                                       "level" : LevelDistrict,
                                       "inner" : set(),
                                       "outer" : set(),
                                     }
        else:
            # District only file, automagicaly build region from district
            key_admin1 = "SR_" + subregion.upper()
            key_admin2 = "DI_" + district.upper()
            if key_admin1 not in admins:
                admins[key_admin1] = { "name" : convertname(subregion),
                                       "level" : LevelSubRegion,
                                       "inner" : set(),
                                       "outer" : set(),
                                     }
            if key_admin2 not in admins:
                admins[key_admin2] = { "name" : convertname(district),
                                       "level" : LevelDistrict,
                                       "inner" : set(),
                                       "outer" : set(),
                                     }

        # Build sets of lineid, deal only outer, inner rings
        # are useless and wrong
        lineset = set()
        if newgeometry.GetGeometryType() == ogr.wkbMultiPolygon:
            ring = newgeometry.GetGeometryRef(0).GetGeometryRef(0)
        else:
            ring = newgeometry.GetGeometryRef(0)
        pntinring = []
        for pnt in xrange(ring.GetPointCount()):
            lon, lat = ring.GetPoint_2D(pnt)
            pointid = shapeu.getPoint(lon, lat)
            if pointid is not None:
                pntinring.append(pointid)

        if pntinring[0] != pntinring[-1]:
            # Simplification have broken the ring,
            # starting point was in the middle of a simplified line
            pntinring.append(pntinring[0])

        for pnt in xrange(1, len(pntinring)):
            if pntinring[pnt-1] ==  pntinring[pnt]:
                # If 2 coordinates after rounding give the same point id
                # (safety measure, normaly doesn't happen)
                continue
            segment = shapeu.getSegment(pntinring[pnt-1], pntinring[pnt])
            lineset.add(shapeu.getLine(segment))

        # Update each administrative level
        admins[key_admin2]["outer"].update(lineset)
        if key_admin1 is not None:
            admins[key_admin1]["outer"].symmetric_difference_update(lineset)
    logo.ending()


def verify_admin(shapeu, admins):
    """
    Check that all administrative area are closed.

    Also search for inner ring and update 'admins'.
    """

    logo.starting("Verify admin area", len(admins))
    for adm in admins:
        logo.progress()
        logo.DEBUG("Area level=%(level)d '%(name)s'" % admins[adm])

        # Administrative areas read from the shapefile are also checked
        # and dispatched into outer/inner ring, even if technically only
        # the upper and reconstructed admin level need it (the shapefile
        # already knows what's outer and inner, but we avoid a special
        # case and it cannot fail unless something was really wrong).
        closedrings = FindClosedRings(shapeu, admins[adm]["outer"])
        if closedrings.getLineDiscarded():
            logo.ERROR("Area '%s' ring not closed\n"
                       % (admins[adm]["name"]) )
            for line in closedrings.getLineDiscarded():
                coords = shapeu.getLineCoords(line)
                logo.DEBUG("Line in ring with %d points still open %s -> %s"
                           % (len(coords), coords[0], coords[-1]) )

        # Moving lineids from outer to inner and compute envelope
        for outer, inner in closedrings.iterPolygons():
            for ring in inner:
                lineids = closedrings.getLineRing(ring)
                admins[adm]["outer"].difference_update(lineids)
                admins[adm]["inner"].update(lineids)

    logo.ending()


def write_uganda(fileout, shapeu, admins):
    """
    Import with an unique id all nodes, ways, relations.
    """

    logo.starting("Saving nodes, ways, relations",
                  shapeu.nbrPoints() + shapeu.nbrLines() + len(admins))

    out = open(fileout+".osm", "w")
    tmstamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<osm version="0.6" generator="test">\n')

    # Points -> Nodes
    logo.DEBUG("Write nodes")
    for pointid, coord in shapeu.iterPoints():
        logo.progress()
        out.write('  <node id="-%d" lat="%.7f" lon="%.7f" version="0" timestamp="%s"/>\n'
                  % (pointid+1, coord[1], coord[0], tmstamp))

    # Lines -> Ways
    logo.DEBUG("Write ways")
    waylevel = {}
    for adm in admins:
        for lineid in admins[adm]["outer"]:
            level = min(waylevel.get(lineid, 8), admins[adm]["level"])
            waylevel[lineid] = level
    for lineid, pntids in shapeu.iterLines():
        logo.progress()
        out.write('  <way id="-%d" version="0" timestamp="%s">\n' % (lineid, tmstamp))
        for pointid in pntids:
            out.write('    <nd ref="-%d"/>\n' % (pointid+1))
        out.write('    <tag k="boundary" v="administrative"/>\n')
        out.write('    <tag k="admin_level" v="%s"/>\n' % waylevel[lineid])
        out.write('  </way>\n')

    # Admins -> Relations
    logo.DEBUG("Write relations")
    for (num,adm) in enumerate(admins):
        logo.progress()
        out.write('  <relation id="-%d" version="0" timestamp="%s">\n' % (num+1, tmstamp))
        for role in ("outer", "inner"):
            for lineid in admins[adm][role]:
                out.write('    <member type="way" ref="-%d" role="%s"/>\n' % (lineid, role))
        out.write('    <tag k="type" v="boundary"/>\n')
        out.write('    <tag k="boundary" v="administrative"/>\n')
        out.write('    <tag k="admin_level" v="%d"/>\n' % admins[adm]["level"])
        out.write('    <tag k="name" v="%s"/>\n' % admins[adm]["name"])
        out.write('  </relation>\n')
    out.write('  </osm>\n')
    logo.ending()


def main():
    logo.init(filename = uganda_config.logfile,
              verbose = uganda_config.verbose,
              progress = uganda_config.progress)
    if len(sys.argv) < 2:
        raise logo.ERROR("Missing input Shapefile")

    shapeu = ShapeUtil(uganda_config.cachesize)
    for i in xrange(1, len(sys.argv)):
        logo.INFO("Reading geometries '%s'" % sys.argv[i])
        read_UGANDA(sys.argv[i], shapeu)

    logo.INFO("Simplify geometries")
    shapeu.buildSimplifiedLines()

    logo.INFO("Building administrative area")
    admins = {}
    for i in xrange(1, len(sys.argv)):
        admin_UGANDA(sys.argv[i], shapeu, admins)
    logo.INFO("Verifying administrative area")
    verify_admin(shapeu, admins)

    logo.INFO("Writing output file")
    write_uganda(os.path.splitext(sys.argv[1])[0], shapeu, admins)
    logo.close()


if __name__ == '__main__':
    main()
