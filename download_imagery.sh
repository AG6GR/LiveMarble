#!/bin/sh

mkdir -p img
python3 slider_download.py latest --zoom 2 goes-16 -o img/goes-16.jpg
python3 slider_download.py latest --zoom 2 goes-17 -o img/goes-17.jpg
python3 slider_download.py latest --zoom 2 himawari -o img/himawari.jpg
python3 slider_download.py latest meteosat-9 -o img/meteosat-9.jpg
python3 slider_download.py latest meteosat-11 -o img/meteosat-11.jpg
