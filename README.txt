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

The district shapefile is not well formed causing issues in conversion :
 - features 6, 47 : are multipolygon in a polygon file
 - features 11, 67, 70, 100 : polygons with very strange inner ring
 - features 25 : polygon with a small banana loop
 - several very close but not shared point between polygons

This program deal those case as follow :
 - only convert the first (and only one usefull) polygon in a multipolygon
 - ignore inner ring
 - banana loop is converted/simplified into an unconnected way
 - rounding points to 5 decimals

The output will have the following issues :
 - too many parallel ways that need to be merged and shared between admin
 - one useless and unconnected way

The small and unconnected way will raise an error (ring not closed) but
it's ok, all relations are correctly created.

