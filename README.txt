You will need at least :
  - Python 2.7.3
  - gdal 1.7.3
  - postgresql 9.1.3
  - postgis 1.5.3
  - psycopg2 2.4.5

The converted OSM file will be saved in a local postgresql+postgis database.
You'll have to set up a database and a user account.
Tables will be created with an osmosis schema.

The postgres dependency will eventually be dropped, it's not needed if you
only want an .osm file (only useful if you want to make conflation later).

There is a config file 'uganda_config.py' it's already set to be verbose.


Syntax :
--------

  - python uganda_build.py Uganda_districts2010.shp


The program is designed to append to database, if you want to clean it up
before running drop a table (everything will be recreated) :

  - psql -d osmosis
    - drop table uganda_relations;


Bug :
-----

Probably ;-)

This program can't cope with some features in the Uganda_district file :
 - features 6, 47 : seems to be multipolygon in a polygon file
 - features 11, 25, 67, 70, 100 : programs goes into an infinite loop
 - automatic aggregate of the district into subregion (infinite loop)

Those features have been skipped for now.

