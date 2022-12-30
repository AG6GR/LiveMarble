#!/usr/bin/env python3
# Automation to download imagery for live page

from datetime import datetime, timezone
from pathlib import Path
from slider_download import SliderDownloader

# Map of satellites to download and what zoom level to use
satellites = {
    'goes-16' : 2,
    'goes-17' : 2,
    'himawari' : 2,
    'meteosat-9' : 3,
    'meteosat-11' : 3
}

Path("img").mkdir(exist_ok=True)

downloader = SliderDownloader()
timestamp = downloader.get_matching_timestamp(satellites.keys())

for satellite, zoomlevel in satellites.items():
    print(satellite)
    sat_timestamp = downloader.fetch_nearest_timestamp(satellite, timestamp)
    downloader.download_image(sat_timestamp, satellite, zoomlevel=zoomlevel, out_filename=f"img/{satellite}.jpg")

timestamp_dt = datetime.strptime(str(timestamp), "%Y%m%d%H%M%S")
timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
with open("last_update.js", "w") as last_update_file:
    last_update_file.write(f"export const last_update = new Date('{timestamp_dt.isoformat()}')\n")
