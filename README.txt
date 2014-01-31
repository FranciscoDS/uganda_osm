You will need at least :
  - Python 2.7.3
  - gdal 1.7.3

This version will create an admin area .OSM file for Uganda.
The output file will contains error so it MUST NOT BE IMPORTED into OSM.

The postgres dependency have been removed, so the program will only give
you an .osm file to be viewed (no conflation, so file can only be used
for viewing purpose).

There is a config file 'uganda_config.py' it's already set to be verbose.
The log file will be named 'uganda.log'.


Syntax :
--------

  - python uganda_build.py Uganda_districts2010.shp
or
  - python uganda_build.py Uganda_Complete.osm


The program will create an '_out.osm' file, in the first case the output
will be named 'Uganda_districts2010_out.osm'.

When giving an .osm input file, the file must be clean, it's intended that
the file have been edited/corrected by hand, so that the program will
only need to do simplification, split on node limits and grouping ways
into admins with inner/outer role.


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

