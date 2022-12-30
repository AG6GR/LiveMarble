import numpy as np
import imageio.v3 as iio
from datetime import datetime
import urllib.request
import urllib.parse
import json
import bisect
import concurrent.futures

#https://rammb-slider.cira.colostate.edu/data/json/goes-17/full_disk/geocolor/20221229_by_hour.json
#https://rammb-slider.cira.colostate.edu/data/json/goes-17/full_disk/geocolor/available_dates.json
#https://rammb-slider.cira.colostate.edu/data/json/goes-17/full_disk/geocolor/latest_times.json
#https://rammb-slider.cira.colostate.edu/data/imagery/2022/12/30/goes-16---full_disk/geocolor/20221230045020/04/008_004.png

class SliderDownloader:
    def __init__(self):
        self.fetch_products()

    def fetch_products(self):
        with urllib.request.urlopen("https://rammb-slider.cira.colostate.edu/js/define-products.js") as f:
            text = f.read().decode('utf-8')
            self.products = json.loads(text[text.index('{'):-2])

    def fetch_latest_timestamp(self, satellite, align=5):
        with urllib.request.urlopen(f"https://rammb-slider.cira.colostate.edu/data/json/{satellite}/full_disk/geocolor/latest_times.json") as f:
            timestamps = json.loads(f.read().decode('utf-8'))['timestamps_int']
            for timestamp in timestamps:
                if datetime.strptime(str(timestamp), "%Y%m%d%H%M%S").minute % align == 0:
                    return timestamp
        return None

    def fetch_nearest_timestamp(self, satellite, datestr, target_timestr):
        if not self.is_geostationary(satellite):
            return

        with urllib.request.urlopen(f"https://rammb-slider.cira.colostate.edu/data/json/{satellite}/full_disk/geocolor/{datestr}_by_hour.json") as f:
            text = f.read().decode('utf-8')
            timestamps = sorted(json.loads(text)['timestamps_int'][target_timestr[:2]])
            target_time = int(datestr + target_timestr + "00")
            if target_time in timestamps:
                return target_time
            else:
                return timestamps[bisect.bisect_right(timestamps, target_time)]

    def get_satellite_names(self):
        return list(self.products["satellites"].keys())

    def is_geostationary(self, satellite):
        return "full_disk" in self.products["satellites"][satellite]["sectors"]

    def print_satellite_info(self):
        for name, info in self.products["satellites"].items():
            print(f'{info["satellite_title"]} ({name})')
            if "full_disk" in info["sectors"]:
                print(f'\tMax zoom level: {info["sectors"]["full_disk"]["max_zoom_level"]}')
                print(f'\tTile size: {info["sectors"]["full_disk"]["tile_size"]}')
                print(f'\tMinutes between images: {info["sectors"]["full_disk"]["defaults"]["minutes_between_images"]}')

    # Max zoomlevel seems to be 4
    def download_image(self, timestamp_str, satellite="goes-16", zoomlevel=3, out_filename=None):
        if not self.is_geostationary(satellite):
            return

        timestamp = datetime.strptime(str(timestamp_str), "%Y%m%d%H%M%S")
        tile_size = self.products["satellites"][satellite]["sectors"]["full_disk"]["tile_size"]
    
        # Clamp zoomlevel to max available
        zoomlevel = min(zoomlevel, self.products["satellites"][satellite]["sectors"]["full_disk"]["max_zoom_level"])

        num_tiles = 2 ** zoomlevel
        out_image = np.empty((num_tiles * tile_size, num_tiles * tile_size, 3), dtype=np.uint8)
        
        def download_single(entry):
            row = entry[0]
            col = entry[1]
            url = f"https://rammb-slider.cira.colostate.edu/data/imagery/{timestamp.year}/{timestamp.month}/{timestamp.day}/{satellite}---full_disk/geocolor/{timestamp_str}/{zoomlevel:02}/{row:03}_{col:03}.png"
            print(url)
            out_image[row * tile_size:(row + 1) * tile_size, col * tile_size:(col + 1) * tile_size, :] = iio.imread(url, mode="RGB")

        entries = []
        for row in range(2 ** zoomlevel):
            for col in range(2 ** zoomlevel):
                entries.append((row, col))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            completed = 0
            future_to_entry = {executor.submit(download_single, entry): entry for entry in entries}
            for future in concurrent.futures.as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    data = future.result()
                except Exception as exc:
                    print(f'{entry} generated an exception: {exc}')
                else:
                    completed += 1
                    print(f'{completed}/{len(entries)} ({float(completed) / len(entries) * 100:.04}%) finished')
        
        if out_filename is None:
            iio.imwrite(f"{satellite}_{timestamp_str}.jpg", out_image, optimize=True)
        else:
            iio.imwrite(out_filename, out_image, optimize=True)

if __name__ == "__main__":
    downloader = SliderDownloader()

    import argparse
    parser = argparse.ArgumentParser(description="Download full disk image from RAMMB SLIDER")
    subparsers = parser.add_subparsers(dest="subcommand")

    parser_download = subparsers.add_parser('download', help='Download a specific image')
    parser_download.add_argument('--out', '-o', help="Output file name")
    parser_download.add_argument('--zoom', type=int, default=3, help="Zoom level to use")
    parser_download.add_argument('satellite', choices=downloader.get_satellite_names() + ["all"], help='Name of satellite to download image from')
    parser_download.add_argument('date', help="Date to download in YYYYMMDD format")
    parser_download.add_argument('time', help="Time in HHMM to download, first available image after this time will be used")
    
    parser_latest = subparsers.add_parser('latest', help='Download latest available image')
    parser_latest.add_argument('--out', '-o', help="Output file name")
    parser_latest.add_argument('--zoom', type=int, default=3, help="Zoom level to use")
    parser_latest.add_argument('--align', type=int, default=30, help="Choose times aligned with given number of minutes")
    parser_latest.add_argument('satellite', choices=downloader.get_satellite_names() + ["all"], help='Name of satellite to download image from')

    parser_info = subparsers.add_parser('info', help='Print satellite info')

    args = parser.parse_args()

    if args.subcommand == "download":
        satellites = []
        if args.satellite == "all":
            satellites = downloader.get_satellite_names()
        else:
            satellites.append(args.satellite)
    
        for satellite in satellites:
            if not downloader.is_geostationary(satellite):
                continue
            timestamp = downloader.fetch_nearest_timestamp(satellite, args.date, args.time)
            downloader.download_image(timestamp, satellite, zoomlevel=args.zoom, out_filename=args.out)
    elif args.subcommand == "latest":
        satellites = []
        if args.satellite == "all":
            satellites = downloader.get_satellite_names()
        else:
            satellites.append(args.satellite)
    
        for satellite in satellites:
            if not downloader.is_geostationary(satellite):
                continue
            timestamp = downloader.fetch_latest_timestamp(satellite)
            downloader.download_image(timestamp, satellite, zoomlevel=args.zoom, out_filename=args.out)
    else:
        downloader.print_satellite_info()