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
import psycopg2
from cStringIO import StringIO
from osgeo import gdal, ogr, osr
from shapeu import ShapeUtil
from ringue import FindClosedRings
import logo
import uganda_config

# GDAL 1.9.0 can do the ISO8859-1 to UTF-8 recoding for us
# but will do it ourself to be backward compatible
gdal.SetConfigOption('SHAPE_ENCODING', '')

# Use SQL operator IN with set() like tuple (reuse tuple adaptation)
psycopg2.extensions.register_adapter(set, lambda x:
                                           psycopg2.extensions.adapt(tuple(x)))


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
    for field in ( "DNAME_2010", "SUBREGION" ):
        if layerDef.GetFieldIndex(field) == -1:
            raise logo.ERROR("Field '%s' not found" % field)
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

    # Reread each polygon and create the right administrative area
    logo.starting("Attributes read", layer.GetFeatureCount())
    for featnum in xrange(layer.GetFeatureCount()):
        logo.progress(featnum)
        feature = layer.GetFeature(featnum)
        geometry  = feature.GetGeometryRef()
        newgeometry = geometry.Clone()
        newgeometry.Transform(transform)
        subregion = convertname(feature.GetField("SUBREGION"))
        district  = convertname(feature.GetField("DNAME_2010"))
        logo.DEBUG("Feature %d SUBREGION='%s' DISTRICT='%s'" % (
                   featnum, subregion, district))

        # Subregion
        #key_admin1 = "SR_" + subregion
        #if key_admin1 not in admins:
        #    admins[key_admin1] = { "name" : subregion,
        #                             "level" : 6,
        #                             "inner" : set(),
        #                             "outer" : set(),
        #                       }

        # District
        key_admin2 = "DI_" + district
        if key_admin2 not in admins:
            admins[key_admin2] = { "name" : district,
                                 "level" : 7,
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
        #admins[key_admin1]["outer"].symmetric_difference_update(lineset)
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


def create_uganda_table(db):
    """ Recreate uganda tables. """

    cursor = db.cursor()

    # Create node tables
    logo.DEBUG("Create Node tables")
    cursor.execute("""DROP TABLE IF EXISTS uganda_nodes""")
    cursor.execute("""CREATE TABLE uganda_nodes (
                        uganda_id bigint NOT NULL,
                        osmid bigint,
                        version int,
                        action character(1)
                      )""")
    cursor.execute("""SELECT AddGeometryColumn('uganda_nodes', 'geom',
                                               4326, 'POINT', 2)
                   """)
    cursor.execute("""DROP TABLE IF EXISTS uganda_node_tags""")
    cursor.execute("""CREATE TABLE uganda_node_tags (
                        uganda_id bigint NOT NULL,
                        k text NOT NULL,
                        v text NOT NULL
                      )""")

    # Create way tables
    logo.DEBUG("Create Way tables")
    cursor.execute("""DROP TABLE IF EXISTS uganda_ways""")
    cursor.execute("""CREATE TABLE uganda_ways (
                        uganda_id bigint NOT NULL,
                        osmid bigint,
                        version int,
                        action character(1)
                      )""")
    cursor.execute("""DROP TABLE IF EXISTS uganda_way_nodes""")
    cursor.execute("""CREATE TABLE uganda_way_nodes (
                        uganda_id bigint NOT NULL,
                        node_id bigint NOT NULL,
                        sequence_id int NOT NULL
                      )""")
    cursor.execute("""DROP TABLE IF EXISTS uganda_way_tags""")
    cursor.execute("""CREATE TABLE uganda_way_tags (
                        uganda_id bigint NOT NULL,
                        k text NOT NULL,
                        v text NOT NULL
                      )""")

    # Create relation tables
    logo.DEBUG("Create Relation tables")
    cursor.execute("""DROP TABLE IF EXISTS uganda_relations""")
    cursor.execute("""CREATE TABLE uganda_relations (
                        uganda_id bigint NOT NULL,
                        osmid int,
                        version int,
                        action character(1)
                      )""")
    cursor.execute("""DROP TABLE IF EXISTS uganda_relation_members""")
    cursor.execute("""CREATE TABLE uganda_relation_members (
                        uganda_id bigint NOT NULL,
                        member_id bigint NOT NULL,
                        member_type character(1) NOT NULL,
                        member_role text NOT NULL,
                        sequence_id int NOT NULL
                      )""")
    cursor.execute("""DROP TABLE IF EXISTS uganda_relation_tags""")
    cursor.execute("""CREATE TABLE uganda_relation_tags (
                        uganda_id bigint NOT NULL,
                        k text NOT NULL,
                        v text NOT NULL
                      )""")

    # Primary key for node, way, relation
    logo.DEBUG("Create primary key")
    cursor.execute("""ALTER TABLE uganda_nodes
                      ADD CONSTRAINT pk_uganda_nodes
                        PRIMARY KEY (uganda_id)
                       """)
    cursor.execute("""ALTER TABLE uganda_ways
                      ADD CONSTRAINT pk_uganda_ways
                        PRIMARY KEY (uganda_id)
                   """)
    cursor.execute("""ALTER TABLE uganda_relations
                      ADD CONSTRAINT pk_uganda_relations
                        PRIMARY KEY (uganda_id)
                   """)

    # Primary key for nodes in way, members in relation
    cursor.execute("""ALTER TABLE uganda_way_nodes
                      ADD CONSTRAINT pk_uganda_way_nodes
                        PRIMARY KEY (uganda_id, sequence_id)
                   """)
    cursor.execute("""ALTER TABLE uganda_relation_members
                      ADD CONSTRAINT pk_uganda_relation_members
                        PRIMARY KEY (uganda_id, sequence_id)
                   """)

    # Create spatial index
    logo.DEBUG("Create index")
    cursor.execute("""CREATE INDEX idx_uganda_node_geom
                      ON uganda_nodes USING gist (geom)
                   """)

    # Create index for tags
    cursor.execute("""CREATE INDEX idx_uganda_node_tags
                      ON uganda_node_tags USING btree (uganda_id)
                   """)
    cursor.execute("""CREATE INDEX idx_uganda_way_tags
                      ON uganda_way_tags USING btree (uganda_id)
                   """)
    cursor.execute("""CREATE INDEX idx_uganda_relation_tags
                      ON uganda_relation_tags USING btree (uganda_id)
                   """)

    # Auto-incrementing sequence for uganda_id
    logo.DEBUG("Create sequence")
    cursor.execute("""DROP SEQUENCE IF EXISTS seq_uganda_id""")
    cursor.execute("""CREATE SEQUENCE seq_uganda_id INCREMENT BY -1""")

    db.commit()


def create_temp_table(db):
    """
    Create temporary table to assign uganda_id to line, point, admin.
    """

    cursor = db.cursor()

    # Table converting id into unique id
    logo.DEBUG("Create Temporary tables")
    cursor.execute("""CREATE TEMPORARY TABLE uganda_points (
                        point_id int NOT NULL,
                        uganda_id bigint NOT NULL
                          DEFAULT nextval('seq_uganda_id'),
                        PRIMARY KEY (point_id)
                          )""")
    cursor.execute("""SELECT AddGeometryColumn('uganda_points', 'geom',
                                               4326, 'POINT', 2)
                   """)
    cursor.execute("""CREATE TEMPORARY TABLE uganda_lines (
                        line_id int NOT NULL,
                        uganda_id bigint NOT NULL
                          DEFAULT nextval('seq_uganda_id'),
                        PRIMARY KEY (line_id)
                          )""")
    cursor.execute("""CREATE TEMPORARY TABLE uganda_admins (
                        admin_id int NOT NULL,
                        uganda_id bigint NOT NULL
                          DEFAULT nextval('seq_uganda_id'),
                        name text NOT NULL,
                        level int NOT NULL,
                        PRIMARY KEY (admin_id)
                      )""")

    # Table for bulk copy content in lines/admins
    cursor.execute("""CREATE TEMPORARY TABLE uganda_linepts (
                        line_id int NOT NULL,
                        sequence_id int NOT NULL,
                        point_id int NOT NULL,
                        PRIMARY KEY (line_id, sequence_id)
                      )""")
    cursor.execute("""CREATE TEMPORARY TABLE uganda_adminlines (
                        admin_id int NOT NULL,
                        line_id int NOT NULL,
                        role text NOT NULL,
                        sequence_id int NOT NULL,
                        PRIMARY KEY (admin_id, sequence_id)
                      )""")

    db.commit()


def import_uganda(db, shapeu, admins):
    """
    Import with an unique id all nodes, ways, relations.
    """

    cursor = db.cursor()
    logo.starting("Saving nodes, ways, relations",
                  shapeu.nbrPoints() + shapeu.nbrLines() + len(admins))

    # Points -> Nodes
    # - bulk copy to a temp table to get a new unique id
    # - do only one big insert with new ids to the finale table
    logo.DEBUG("Write nodes to database")
    buffcopy = StringIO()
    for pointid, coord in shapeu.iterPoints():
        logo.progress()
        pointEwkt = "SRID=4326;POINT(%.7f %.7f)" % (coord[0], coord[1])
        buffcopy.write("%d\t%s\n" % (pointid, pointEwkt))
    buffcopy.seek(0)
    cursor.copy_from(buffcopy, 'uganda_points', columns=('point_id', 'geom'))
    cursor.execute("""INSERT INTO uganda_nodes (uganda_id, geom)
                      SELECT uganda_id, geom FROM uganda_points
                   """)
    db.commit()
    buffcopy.close()

    # Lines -> Ways
    # - bulk copy to a temp table to get a new unique id
    # - bulk copy points in lines in a temp table
    # - insert all ways with new ids as administrative level 8
    logo.DEBUG("Write ways to database")
    buffcopy1 = StringIO()
    buffcopy2 = StringIO()
    for lineid, pntids in shapeu.iterLines():
        logo.progress()
        buffcopy1.write("%d\n" % lineid)
        for orderpntid in enumerate(pntids):
            buffcopy2.write("%d\t" % lineid)
            buffcopy2.write("%d\t%d\n" % orderpntid)
    buffcopy1.seek(0)
    cursor.copy_from(buffcopy1, 'uganda_lines', columns=('line_id',))
    cursor.execute("""INSERT INTO uganda_ways (uganda_id)
                      SELECT uganda_id FROM uganda_lines
                   """)
    buffcopy2.seek(0)
    cursor.copy_from(buffcopy2, 'uganda_linepts')
    cursor.execute("""INSERT INTO uganda_way_nodes
                      SELECT A.uganda_id, B.uganda_id, C.sequence_id
                      FROM uganda_lines A, uganda_points B, uganda_linepts C
                      WHERE A.line_id = C.line_id
                      AND C.point_id = B.point_id
                   """)
    cursor.execute("""INSERT INTO uganda_way_tags
                      SELECT uganda_id, 'boundary', 'administrative'
                      FROM uganda_lines
                   """)
    cursor.execute("""INSERT INTO uganda_way_tags
                      SELECT uganda_id, 'admin_level', 8
                      FROM uganda_lines
                   """)
    db.commit()
    buffcopy1.close()
    buffcopy2.close()

    # Admins -> Relations
    # - bulk copy to a temp table to get a new unique id
    # - bulk copy lines in admins in a temp table
    # - correct outer ways administrative level
    # - insert all tags for administrative area
    logo.DEBUG("Write relations to database")
    buffcopy1 = StringIO()
    buffcopy2 = StringIO()
    for (num,adm) in enumerate(admins):
        logo.progress()
        buffcopy1.write("%d\t" % num)
        buffcopy1.write("%(name)s\t%(level)d\n" % admins[adm])
        sequenceid = 0
        for role in ("outer", "inner"):
            for lineid in admins[adm][role]:
                buffcopy2.write("%d\t%d\t%s\t%d\n" % (
                                num, lineid, role, sequenceid))
                sequenceid += 1
        if admins[adm]['level'] < 8:
            cursor.execute("""UPDATE uganda_way_tags SET v = %(level)s
                              FROM uganda_lines A
                              WHERE uganda_way_tags.uganda_id = A.uganda_id
                              AND A.line_id IN %(outer)s
                              AND k = 'admin_level'
                              AND v::int > %(level)s
                           """, admins[adm])
    db.commit()
    buffcopy1.seek(0)
    cursor.copy_from(buffcopy1, 'uganda_admins', columns=('admin_id', 'name',
                                                        'level'))
    cursor.execute("""INSERT INTO uganda_relations (uganda_id)
                      SELECT uganda_id FROM uganda_admins
                   """)
    buffcopy2.seek(0)
    cursor.copy_from(buffcopy2, 'uganda_adminlines')
    cursor.execute("""INSERT INTO uganda_relation_members
                      SELECT A.uganda_id, B.uganda_id, 'W', C.role, C.sequence_id
                      FROM uganda_admins A, uganda_lines B, uganda_adminlines C
                      WHERE A.admin_id = C.admin_id
                      AND C.line_id = B.line_id
                   """)
    cursor.execute("""INSERT INTO uganda_relation_tags
                      SELECT uganda_id, 'type', 'boundary'
                      FROM uganda_admins
                   """)
    cursor.execute("""INSERT INTO uganda_relation_tags
                      SELECT uganda_id, 'boundary', 'administrative'
                      FROM uganda_admins
                   """)
    cursor.execute("""INSERT INTO uganda_relation_tags
                      SELECT uganda_id, 'admin_level', level::text
                      FROM uganda_admins
                   """)
    cursor.execute("""INSERT INTO uganda_relation_tags
                      SELECT uganda_id, 'name', name
                      FROM uganda_admins
                   """)
    db.commit()
    buffcopy1.close()
    buffcopy2.close()
    logo.ending()


def vacuum_analyze_db(db):
    """ Update DB statistics. """

    logo.DEBUG("Vacuum Analyze")
    isolation_level = db.isolation_level
    db.set_isolation_level(0)
    cursor = db.cursor()
    cursor.execute("VACUUM ANALYZE")
    db.set_isolation_level(isolation_level)


def check_db_uganda(db):
    """ Check for special uganda tables. """

    logo.DEBUG("Checking for UGANDA tables ...")
    cursor = db.cursor()
    try:
        cursor.execute("""SELECT max(uganda_id) FROM uganda_nodes
                          UNION
                          SELECT max(uganda_id) FROM uganda_ways
                          UNION
                          SELECT max(uganda_id) FROM uganda_relations
                          UNION
                          SELECT last_value FROM seq_uganda_id
                       """)
        cursor.fetchall()  # ignore result, just check if table exists
    except psycopg2.ProgrammingError:
        db.rollback()
        logo.DEBUG("... no UGANDA tables")
        return False
    db.commit()
    logo.DEBUG("... UGANDA tables exists")
    return True


def main():
    logo.init(filename = uganda_config.logfile,
              verbose = uganda_config.verbose,
              progress = uganda_config.progress)
    if len(sys.argv) < 2:
        raise logo.ERROR("Missing input Shapefile")

    logo.DEBUG("Connect to DB(%s)" % uganda_config.dbname)
    db = psycopg2.connect(uganda_config.dbname)
    if not check_db_uganda(db):
        logo.INFO("Creating PostgreSQL tables")
        create_uganda_table(db)
    create_temp_table(db)

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

    logo.INFO("Importing into database")
    import_uganda(db, shapeu, admins)
    vacuum_analyze_db(db)
    logo.close()


if __name__ == '__main__':
    main()
