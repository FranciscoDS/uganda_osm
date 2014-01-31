#!/usr/bin/python

"""
Get and parse an OSM XML.
"""

import re

# Regexp for extracting data in xml
re_osmid = re.compile(r'''\sid\s*=\s*(?P<quote>["'])(?P<osmid>[-0-9]+)(?P=quote)''')
re_lon = re.compile(r'''\slon\s*=\s*(?P<quote>["'])(?P<lon>[-0-9.E]+)(?P=quote)''')
re_lat = re.compile(r'''\slat\s*=\s*(?P<quote>["'])(?P<lat>[-0-9.E]+)(?P=quote)''')
re_tags = re.compile(r'''<tag\s+(?P<fieldA>[kv])\s*=\s*(?P<quoteA>["'])(?P<dataA>.*?)(?P=quoteA)\s+(?P<fieldB>[kv])\s*=\s*(?P<quoteB>["'])(?P<dataB>.*?)(?P=quoteB)''')
re_ndref = re.compile(r'''<nd\s+ref\s*=\s*(?P<quote>["'])(?P<ndref>[-0-9]+)(?P=quote)''')
re_member = re.compile(r'<member\s[^>]*')
re_type = re.compile(r'''\stype\s*=\s*(?P<quote>["'])(?P<type>node|way|relation)(?P=quote)''')
re_ref = re.compile(r'''\sref\s*=\s*(?P<quote>["'])(?P<ref>[-0-9]+)(?P=quote)''')
re_role = re.compile(r'''\srole\s*=\s*(?P<quote>["'])(?P<role>.*?)(?P=quote)''')
regexp = re.compile(r'<(?P<typobj>node|way|relation)([^<]*/>|.*?</(?P=typobj)>)', re.DOTALL)

# All data extracted from xml
extracted_data = { 'node' : {}, 'way' : {}, 'relation' : {} }

def parse_xml(xml):
    idxtypeobj = regexp.groupindex['typobj']
    for found in regexp.finditer(xml):
        # New object, extract attributes data
        typobj = found.group(idxtypeobj)
        startpos, endpos = found.span(0)
        objdata = { 'tags' : {}, 'nodes' : [], 'members' : [] }
        m = re_osmid.search(xml, startpos, endpos)
        if m:
            idobj = m.groupdict()['osmid']

        m = re_lon.search(xml, startpos, endpos)
        if m:
            objdata['lon'] = float(m.groupdict()['lon'])

        m = re_lat.search(xml, startpos, endpos)
        if m:
            objdata['lat'] = float(m.groupdict()['lat'])

        for m in re_tags.finditer(xml, startpos, endpos):
            d = m.groupdict()
            if d['fieldA'] == 'k':
                objdata['tags'][d['dataA']] = d['dataB']
            else:
                objdata['tags'][d['dataB']] = d['dataA']

        for m in re_ndref.finditer(xml, startpos, endpos):
            objdata['nodes'].append(m.groupdict()['ndref'])

        for m in re_member.finditer(xml, startpos, endpos):
            startmemb, endmemb = m.span(0)
            member = [ '' ] * 3
            data = re_type.search(xml, startmemb, endmemb)
            if data:
                 member[0] = data.groupdict()['type']
            data = re_ref.search(xml, startmemb, endmemb)
            if data:
                 member[1] = data.groupdict()['ref']
            data = re_role.search(xml, startmemb, endmemb)
            if data:
                 member[2] = data.groupdict()['role']
            objdata['members'].append(member)

        extracted_data[typobj][idobj] = objdata


def getNbRelation():
    return len(extracted_data['relation'])

def getIterRelation():
    return extracted_data['relation'].keys()

def getRelation(relationid):
    return extracted_data['relation'][relationid]

def getGeometryWay(wayid):
    line = []
    for nodeid in extracted_data['way'][wayid]['nodes']:
        coord = ( extracted_data['node'][nodeid]['lon'],
                  extracted_data['node'][nodeid]['lat'] )
        line.append(coord)
    return line
