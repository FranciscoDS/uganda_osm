import psycopg2
import sys
import datetime

def check_db_uganda(db):
    """ Check for special uganda table."""
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
        return False
    db.commit()
    return True


def osm_file(db, filename):
    reltype = { 'N' : "node", 'W' : "way",  'R' : "relation" }
    out = open(filename, 'w')
    cursor = db.cursor()
    cursorchild = db.cursor()
    tmstamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<osm version="0.6" generator="test">\n')
    cursor.execute("""SELECT uganda_id, ST_X(geom), ST_Y(geom)
                      FROM uganda_nodes
                   """)
    for nodeid, lon, lat in cursor:
        out.write('  <node id="%d" lat="%.7f" lon="%.7f" version="0" timestamp="%s"/>\n' % (nodeid, lat, lon, tmstamp))
    cursor.execute("""SELECT uganda_id FROM uganda_ways""")
    for (wayid,) in cursor:
        cursorchild.execute("""SELECT node_id FROM uganda_way_nodes
                               WHERE uganda_id = %s
                               ORDER BY sequence_id
                            """, (wayid,) )
        out.write('  <way id="%d" version="0" timestamp="%s">\n' % (wayid, tmstamp))
        for nodeid in cursorchild:
            out.write('    <nd ref="%d"/>\n' % nodeid)
        cursorchild.execute("""SELECT k, v FROM uganda_way_tags
                               WHERE uganda_id = %s
                            """, (wayid,) )
        for key, value in cursorchild:
            out.write('    <tag k="%s" v="%s"/>\n' % (key, value))
        out.write('  </way>\n')
    cursor.execute("""SELECT uganda_id FROM uganda_relations""")
    for (relid,) in cursor:
        out.write('  <relation id="%d" version="0" timestamp="%s">\n' % (relid, tmstamp))
        cursorchild.execute("""SELECT k, v FROM uganda_relation_tags
                               WHERE uganda_id = %s
                            """, (relid,) )
        for key, value in cursorchild:
            out.write('    <tag k="%s" v="%s"/>\n' % (key, value))
        cursorchild.execute("""SELECT member_id, member_type, member_role
                               FROM uganda_relation_members
                               WHERE uganda_id = %s
                               ORDER BY sequence_id
                            """, (relid,) )
        for ref, typ, role in cursorchild:
            out.write('    <member type="%s" ref="%d" role="%s"/>\n' % (reltype[typ], ref, role))
        out.write('  </relation>\n')
    out.write('  </osm>\n')


if __name__ == "__main__":
    db = psycopg2.connect("dbname=osmosis")
    if not check_db_uganda(db):
        print "Error UGANDA database"
        sys.exit(1)
    if len(sys.argv) != 2:
        print "Error Syntax"
        sys.exit(1)
    osm_file(db, sys.argv[1])

