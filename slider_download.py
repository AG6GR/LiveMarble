import numpy as np
import imageio.v3 as iio
from datetime import datetime
import urllib.request
import urllib.parse
import json
import bisect
import concurrent.futures

class SliderDownloader:
    def __init__(self):
        self.fetch_products()

    def fetch_products(self):
        with urllib.request.urlopen("https://rammb-slider.cira.colostate.edu/js/define-products.js") as f:
            text = f.read().decode('utf-8')
            self.products = json.loads(text[text.index('{'):-2])

    def fetch_latest_time_list(self, satellite):
        with urllib.request.urlopen(f"https://rammb-slider.cira.colostate.edu/data/json/{satellite}/full_disk/geocolor/latest_times.json") as f:
            return json.loads(f.read().decode('utf-8'))['timestamps_int']

    def fetch_latest_timestamp(self, satellite, align=5):
        timestamps = self.fetch_latest_time_list(satellite)
        for timestamp in timestamps:
            if datetime.strptime(str(timestamp), "%Y%m%d%H%M%S").minute % align == 0:
                return timestamp
        return None

    def fetch_nearest_timestamp(self, satellite, target_timestr):
        if not self.is_geostationary(satellite):
            return
        target_dt = datetime.strptime(str(target_timestr), "%Y%m%d%H%M%S")

        with urllib.request.urlopen(f"https://rammb-slider.cira.colostate.edu/data/json/{satellite}/full_disk/geocolor/{target_dt:%Y%m%d}_by_hour.json") as f:
            text = f.read().decode('utf-8')
            timestamps_by_hour = json.loads(text)['timestamps_int']
            timestamps = []
            for hour, times in timestamps_by_hour.items():
                timestamps.extend(times)
            timestamps.sort()
            target_time = int(target_timestr[:-2] + "00")
            if target_time in timestamps:
                return target_time
            else:
                index = bisect.bisect_right(timestamps, target_time)
                if index == len(timestamps):
                    return timestamps[-1]
                else:
                    return timestamps[index]

    # Find the latest timestamp (without seconds) that all of the given satellites have imagery available
    def get_matching_timestamp(self, satellites):
        matching_timestamps = set()
        for satellite in satellites:
            if len(matching_timestamps) == 0:
                matching_timestamps.update([str(x)[:-2] for x in self.fetch_latest_time_list(satellite)])
            else:
                matching_timestamps.intersection_update([str(x)[:-2] for x in self.fetch_latest_time_list(satellite)])
        return sorted(matching_timestamps)[-1] + "00"

    def get_satellite_names(self):
        return list(self.products["satellites"].keys())

    def is_geostationary(self, satellite):
        return "full_disk" in self.products["satellites"][satellite]["sectors"]

    def print_satellite_info(self):
        for name, info in self.products["satellites"].items():
            print(f'{info["satellite_title"]} ({name})')
            if "full_disk" in info["sectors"]:
                print(f'\tLongitude: {info["sectors"]["full_disk"]["lat_lon_query"]["lon0"]}')
                print(f'\tAltitude: {info["sectors"]["full_disk"]["lat_lon_query"]["sat_alt"]}')
                print(f'\tMax zoom level: {info["sectors"]["full_disk"]["max_zoom_level"]}')
                print(f'\tTile size: {info["sectors"]["full_disk"]["tile_size"]}')
                print(f'\tMinutes between images: {info["sectors"]["full_disk"]["defaults"]["minutes_between_images"]}')
                latest_timestamp = self.fetch_latest_timestamp(name)
                print(f'\tLatest timestamp available: {latest_timestamp} ({(datetime.utcnow() - datetime.strptime(str(latest_timestamp), "%Y%m%d%H%M%S")).total_seconds() / 60:.04} minutes ago)')

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
        
        def download_single(row, col, url):
            out_image[row * tile_size:(row + 1) * tile_size, col * tile_size:(col + 1) * tile_size, :] = iio.imread(url, mode="RGB")

        tiles = []
        for row in range(2 ** zoomlevel):
            for col in range(2 ** zoomlevel):
                tiles.append((row, col, f"https://rammb-slider.cira.colostate.edu/data/imagery/{timestamp.year:02}/{timestamp.month:02}/{timestamp.day:02}/{satellite}---full_disk/geocolor/{timestamp_str}/{zoomlevel:02}/{row:03}_{col:03}.png"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            completed = 0
            future_to_url = {executor.submit(download_single, tile[0], tile[1], tile[2]): tile[0] for tile in tiles}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    data = future.result()
                except Exception as exc:
                    print(f'{url} generated an exception: {exc}')
                else:
                    completed += 1
                    print(f'{completed}/{len(tiles)} ({float(completed) / len(tiles) * 100:.04}%) finished')
        
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
    parser_download.add_argument('timestamp', help="Time in YYYYMMDDHHMM to download, first available image after this time will be used")
    
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
            timestamp = downloader.fetch_nearest_timestamp(satellite, args.timestamp)
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
            timestamp = downloader.fetch_latest_timestamp(satellite, align=args.align)
            downloader.download_image(timestamp, satellite, zoomlevel=args.zoom, out_filename=args.out)
    else:
        downloader.print_satellite_info()