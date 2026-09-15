"""Sequential, bounded video ingestion. No GPS or telemetry is invented."""
import argparse
import csv
import json
import math
import time
from pathlib import Path
import cv2


def extract_video(source, output, interval=2.0, max_frames=300, max_dimension=1280, max_decode_frames=500000):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise ValueError(f'Video does not exist: {source}')
    if interval<=0 or not math.isfinite(interval) or max_frames<1 or max_dimension<64 or max_decode_frames<1:
        raise ValueError('Invalid interval, frame limit, or image dimension')
    if output==source.parent or source.parent in output.parents:
        raise ValueError('Choose a generated output directory outside the raw video directory')
    if output.exists():
        raise ValueError('Output directory already exists; use a fresh job directory')
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        raise ValueError('Video could not be opened: invalid file, unsupported codec, or empty container')
    output.mkdir(parents=True)
    frames=output/'frames'; frames.mkdir()
    fps=float(cap.get(cv2.CAP_PROP_FPS))
    fps=fps if math.isfinite(fps) and fps>0 else None
    count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    codec=int(cap.get(cv2.CAP_PROP_FOURCC))
    codec=''.join(chr((codec >> (8*i)) & 255) for i in range(4)).strip('\x00') or None
    report=dict(source=str(source),input_type='video',fps=fps,reported_frame_count=count if count>0 else None,
                reported_duration_s=count/fps if count>0 and fps else None,codec=codec,
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                gps_status='GPS/telemetry unavailable',timestamp_policy='Decoder presentation time where advancing; otherwise frame_index / reported FPS (estimated).',
                sampling_interval_s=interval,max_frames=max_frames,max_decode_frames=max_decode_frames,
                status='processing',decoded_frames=0,extracted_frames=0,stop_reason='',rows_file='frame_timestamps.csv')
    start=time.perf_counter(); rows=[]; next_time=0.0; last_time=-1.0
    try:
        for index in range(max_decode_frames):
            ok,frame=cap.read()
            if not ok:
                report['stop_reason']='end_of_stream_or_decode_failure'
                break
            report['decoded_frames']+=1
            pts=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            if math.isfinite(pts) and pts>=0 and (index==0 or pts>last_time):
                timestamp=pts; basis='decoder_pts'
            elif fps:
                timestamp=index/fps; basis='estimated_from_fps'
                if timestamp<last_time:
                    raise ValueError('Non-monotonic timestamps: cannot safely sample this stream')
            else:
                raise ValueError('No usable advancing timestamps or FPS; time-based sampling is unavailable')
            last_time=timestamp
            if timestamp+1e-8 < next_time:
                continue
            h,w=frame.shape[:2]; scale=min(1,max_dimension/max(h,w))
            if scale<1:
                frame=cv2.resize(frame,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
            name=f'frame_{index:09d}.jpg'
            ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,95])
            if not ok:
                raise ValueError(f'Failed to encode decoded frame {index}')
            encoded.tofile(frames/name)
            rows.append(dict(filename=name,source_frame_index=index,timestamp_s=timestamp,timestamp_basis=basis,width=frame.shape[1],height=frame.shape[0]))
            next_time=timestamp+interval
            if len(rows)>=max_frames:
                report['stop_reason']='sample_limit_reached'; break
        else:
            report['stop_reason']='decode_limit_reached'
        if not rows:
            raise ValueError('Video contains no decodable frames')
        incomplete=(count>0 and report['decoded_frames']<count-1)
        report['status']='partial' if incomplete or report['stop_reason'].endswith('limit_reached') else 'completed'
        report['warning']='A cap or decode stop may have truncated the video; inspect counts.' if report['status']=='partial' else ''
    except Exception as exc:
        report.update(status='failed',error=str(exc))
        raise
    finally:
        cap.release()
        report.update(extracted_frames=len(rows),processing_seconds=time.perf_counter()-start)
        with (output/'frame_timestamps.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['filename','source_frame_index','timestamp_s','timestamp_basis','width','height'])
            writer.writeheader();writer.writerows(rows)
        (output/'video_metadata.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--interval',type=float,default=2);p.add_argument('--max-frames',type=int,default=300)
    a=p.parse_args()
    print(json.dumps(extract_video(a.video,a.output,a.interval,a.max_frames),indent=2))
