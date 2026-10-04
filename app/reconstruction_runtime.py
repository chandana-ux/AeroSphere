"""Shared local COLMAP discovery, capability checks and atomic status storage."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

CODE = Path(__file__).resolve().parents[1]


def worker_alive(pid):
    """Check liveness without signalling a Windows worker (os.kill would terminate it)."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def find_colmap(explicit=None):
    configured = explicit or os.environ.get('AEROSPHERE_COLMAP')
    if configured:
        path = Path(configured).expanduser()
        if path.is_dir():
            for name in ('bin/colmap.exe', 'colmap.exe', 'COLMAP.bat'):
                if (path / name).is_file():
                    return path / name
        return path if path.is_file() else None
    candidates = [shutil.which('colmap'), shutil.which('COLMAP.bat'),
                  CODE / 'tools/colmap/bin/colmap.exe', CODE / 'tools/colmap/COLMAP.bat']
    if os.name == 'nt':
        for base in (Path.home() / 'Downloads', Path(os.environ.get('ProgramFiles', 'C:/Program Files'))):
            candidates.extend(sorted(base.glob('*[Cc][Oo][Ll][Mm][Aa][Pp]*/bin/colmap.exe')))
            candidates.extend(sorted(base.glob('*[Cc][Oo][Ll][Mm][Aa][Pp]*/COLMAP.bat')))
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


class DependencyError(RuntimeError):
    pass


def sparse_model_files(folder):
    """Return a complete COLMAP model file set, preferring binary as COLMAP does."""
    folder = Path(folder)
    for suffix in ('bin', 'txt'):
        files = [folder / f'{name}.{suffix}' for name in ('cameras', 'images', 'points3D')]
        if all(path.is_file() and path.stat().st_size for path in files):
            return files
    raise RuntimeError(f'No valid sparse model at {folder}: missing or empty cameras, images or points3D files. Dense processing stopped; inspect mapping.log.')


def validate_sparse_depths(folder, cameras):
    """Reject geometry that cannot supply per-view depths at MVS float precision."""
    import numpy as np
    from scipy.spatial.transform import Rotation

    if len(cameras) < 2:
        raise RuntimeError(f'Invalid sparse model at {folder}: fewer than two registered images')
    poses = {}
    supported = set()
    for camera in cameras:
        rotation = Rotation.from_quat([camera[k] for k in ('qx', 'qy', 'qz', 'qw')]).as_matrix()
        poses[camera['image_id']] = (rotation[2].astype(np.float32), np.float32(camera['tz']))
    for line in (Path(folder) / 'points3D.txt').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        xyz = np.array(fields[1:4], dtype=np.float32)
        if not np.isfinite(xyz).all():
            raise RuntimeError(f'Invalid sparse model at {folder}: nonfinite points')
        for image_id in map(int, fields[8::2]):
            row, tz = poses[image_id]
            depth = row @ xyz + tz
            # Reject cancellation noise, not a scene-scale depth cutoff.
            roundoff = 8 * np.finfo(np.float32).eps * (np.abs(row * xyz).sum() + abs(tz))
            if np.isfinite(depth) and depth > roundoff:
                supported.add(image_id)
    unsupported = [c['filename'] for c in cameras if c['image_id'] not in supported]
    if unsupported:
        raise RuntimeError(f'Invalid sparse model at {folder}: {len(unsupported)} registered images have no numerically reliable positive-depth sparse tracks (including {unsupported[0]}). Geometry is empty or degenerate; dense processing stopped.')


class Colmap:
    def __init__(self, path=None):
        launcher = find_colmap(path)
        if launcher is None:
            raise DependencyError('COLMAP command-line application missing. Extract the Windows release into tools/colmap or set AEROSPHERE_COLMAP to COLMAP.bat or colmap.exe. pycolmap does not install the CLI.')
        self.executable = launcher.resolve()
        self.env = os.environ.copy()
        self.env['QT_QPA_PLATFORM'] = 'offscreen'
        if launcher.suffix.lower() in ('.bat', '.cmd'):
            self.executable = launcher.parent / 'bin/colmap.exe'
        if not self.executable.is_file():
            raise DependencyError(f'COLMAP executable missing behind launcher: {self.executable}')
        install = self.executable.parent.parent
        self.env['PATH'] = str(self.executable.parent) + os.pathsep + self.env.get('PATH', '')
        if (install / 'plugins').is_dir():
            self.env['QT_PLUGIN_PATH'] = str(install / 'plugins')
        self.help = {}
        self.version = self.probe('-h')

    def probe(self, command):
        if command not in self.help:
            try:
                result = subprocess.run([str(self.executable), command] + ([] if command == '-h' else ['-h']),
                    env=self.env, capture_output=True, text=True, errors='replace', timeout=30,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise DependencyError(f'Cannot start COLMAP: {exc}') from exc
            output = result.stdout + result.stderr
            if result.returncode or (command != '-h' and not re.search(r'--\w', output)):
                raise DependencyError(f'COLMAP command {command} is unavailable: {output[-1500:]}')
            self.help[command] = output
        return self.help[command]

    def options(self, name, options):
        available = set(re.findall(r'--([\w.]+)', self.probe(name)))
        optional = {'log_target', 'log_color', 'Mapper.ba_use_gpu', 'Mapper.random_seed',
                    'PatchMatchStereo.num_threads'}
        result = []
        for key, value in zip(options[::2], options[1::2]):
            raw = str(key).removeprefix('--')
            resolved = raw
            if raw not in available:
                for old, new in (('FeatureExtraction.', 'SiftExtraction.'), ('FeatureMatching.', 'SiftMatching.')):
                    alternative = raw.replace(old, new)
                    if alternative in available:
                        resolved = alternative
                        break
                else:
                    if raw in optional:
                        continue
                    raise DependencyError(f'Installed COLMAP {name} does not support --{raw}; see saved command help.')
            result.extend(['--' + resolved, str(value)])
        return result
