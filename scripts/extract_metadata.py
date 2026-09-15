"""Read aerial image EXIF without modifying source images."""
import argparse
import csv
import json
import math
from pathlib import Path
from PIL import Image


def text(value):
    if isinstance(value, bytes):
        return value.decode('ascii', errors='replace').strip('\x00')
    return str(value).strip('\x00') if value is not None else ''


def coordinate(value, reference, latitude):
    if value is None:
        return None
    ref = text(reference).upper()
    allowed = ('N', 'S') if latitude else ('E', 'W')
    if ref not in allowed or len(value) != 3:
        raise ValueError('Invalid GPS coordinate/reference')
    d, m, s = map(float, value)
    result = d + m / 60 + s / 3600
    if not all(math.isfinite(x) for x in (d, m, s)) or d < 0 or not 0 <= m < 60 or not 0 <= s < 60 or result > (90 if latitude else 180):
        raise ValueError('GPS coordinate outside valid range')
    return -result if ref in ('S', 'W') else result


def extract(path, root):
    row = dict(filename=path.relative_to(root).as_posix(), width=None, height=None,
               camera_make='', camera_model='', captured_at='', latitude=None,
               longitude=None, altitude_raw_m=None, altitude_m=None, altitude_reference='', gps_datum='',
               status='ok', error='')
    try:
        with Image.open(path) as im:
            row.update(width=im.width, height=im.height)
            exif = im.getexif()
            detail = exif.get_ifd(34665) if 34665 in exif else {}
            row.update(camera_make=text(exif.get(271)), camera_model=text(exif.get(272)),
                       captured_at=text(detail.get(36867, exif.get(306))))
            gps = exif.get_ifd(34853) if 34853 in exif else {}
            row['latitude'] = coordinate(gps.get(2), gps.get(1), True)
            row['longitude'] = coordinate(gps.get(4), gps.get(3), False)
            row['gps_datum'] = text(gps.get(18))
            if 6 in gps:
                ref = gps.get(5)
                if isinstance(ref, bytes):
                    ref = int.from_bytes(ref, 'big')
                altitude = float(gps[6])
                if math.isfinite(altitude) and altitude >= 0:
                    row['altitude_raw_m'] = altitude
                if ref in (0, 1) and math.isfinite(altitude) and altitude >= 0:
                    row['altitude_m'] = -altitude if ref == 1 else altitude
                    row['altitude_reference'] = 'EXIF below sea level' if ref else 'EXIF above sea level'
                else:
                    row['altitude_reference'] = 'missing or invalid reference/value'
            if row['latitude'] is None or row['longitude'] is None:
                row['status'] = 'missing_gps'
    except Exception as exc:
        row.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return row


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=project / 'input' / 'aukerman')
    parser.add_argument('--output', type=Path, default=project / 'metadata' / 'image_metadata.csv')
    args = parser.parse_args()
    source = args.input.resolve()
    destination = args.output.resolve()
    if destination == source or source in destination.parents:
        parser.error('Output must be outside the raw input directory')
    images = sorted(p for p in source.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.tif', '.tiff') and p.is_file())
    if not images:
        parser.error(f'No images found in {source}')
    rows = [extract(p, source) for p in images]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(input_directory=str(source), input_images=len(rows),
                   images_with_gps=sum(r['latitude'] is not None and r['longitude'] is not None for r in rows),
                   images_with_altitude=sum(r['altitude_m'] is not None for r in rows),
                   images_with_raw_altitude=sum(r['altitude_raw_m'] is not None for r in rows),
                   errors=sum(r['status'] == 'error' for r in rows),
                   notes=['EXIF positions are not validated RTK positions.',
                          'Altitude reference is reported as encoded; its vertical datum is not independently verified.',
                          'Capture timestamps have no assumed timezone.',
                          'Image sequence only: this run does not test video extraction.'])
    destination.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'CSV: {destination}')
    if summary['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
