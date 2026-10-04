"""Print local dependency and COLMAP command capabilities without reconstructing."""
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from reconstruction_runtime import Colmap, DependencyError


def check():
    result = {'python':sys.executable, 'ffmpeg':shutil.which('ffmpeg'), 'ffprobe':shutil.which('ffprobe')}
    import cv2
    result['opencv'] = cv2.__version__
    result['opencv_ffmpeg'] = 'FFMPEG:                      YES' in cv2.getBuildInformation()
    try:
        cli = Colmap()
        result.update(colmap=str(cli.executable), version=cli.version.splitlines()[0], commands={})
        for name in ('feature_extractor','exhaustive_matcher','mapper','model_converter','image_undistorter','patch_match_stereo','stereo_fusion','poisson_mesher'):
            try:
                cli.probe(name)
                result['commands'][name] = 'available'
            except DependencyError as exc:
                result['commands'][name] = str(exc)
    except DependencyError as exc:
        result['colmap_error'] = str(exc)
    return result


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    sys.exit(1 if 'colmap_error' in result else 0)
