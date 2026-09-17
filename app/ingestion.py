"""Local upload persistence shared by the UI and ingestion tests."""
from pathlib import Path
import shutil
import uuid

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}

def save_uploads(files, root, video=False):
    files=list(files)
    if not files or (video and len(files)!=1):
        raise ValueError('Choose one video or one or more images.')
    names=[str(f.name).replace('\\','/').split('/')[-1] for f in files]
    allowed=VIDEO_EXTENSIONS if video else IMAGE_EXTENSIONS
    if any(Path(n).suffix.lower() not in allowed for n in names):
        raise ValueError('Unsupported file extension.')
    if len({n.casefold() for n in names}) != len(names):
        raise ValueError('Image filenames must be unique.')
    folder=Path(root)/'uploads'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    for file,name in zip(files,names):
        file.seek(0)
        with (folder/name).open('xb') as out:
            shutil.copyfileobj(file,out,length=1024*1024)
    return folder/names[0] if video else folder

def frame_decisions(root, selection):
    import pandas as pd
    quality=pd.read_csv(Path(selection['report_directory'])/'image_quality.csv')
    quality['selected']=quality['selected'].astype(str).str.lower().eq('true')
    timestamps=Path(root)/'video_ingestion/frame_timestamps.csv'
    if timestamps.exists():
        quality=quality.merge(pd.read_csv(timestamps)[['filename','timestamp_s']],on='filename',how='left',validate='one_to_one')
    else:
        quality['timestamp_s']=float('nan')
    quality['decision']=quality.selected.map({True:'Selected',False:'Rejected'})
    return quality
