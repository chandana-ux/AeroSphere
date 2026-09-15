"""Optional CPU COCO object detection. Predictions are not verified scene facts."""
import argparse
import json
from pathlib import Path


def detect(image_path,project,allow_download=False,threshold=0.5):
    project=Path(project);image_path=Path(image_path)
    cache=project/'output/models/torch'
    expected=cache/'checkpoints/ssdlite320_mobilenet_v3_large_coco-a79551df.pth'
    if not expected.exists() and not allow_download:
        return {'status':'optional/unavailable','reason':'Pretrained weights are not cached; the core pipeline remains available.'}
    try:
        import torch
        from torchvision.models.detection import ssdlite320_mobilenet_v3_large,SSDLite320_MobileNet_V3_Large_Weights
        from PIL import Image,ImageDraw
        torch.set_num_threads(4);torch.hub.set_dir(str(cache))
        weights=SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
        model=ssdlite320_mobilenet_v3_large(weights=weights).eval().cpu()
        with Image.open(image_path) as original:
            im=original.convert('RGB'); im.thumbnail((1280,1280))
        with torch.inference_mode():pred=model([weights.transforms()(im)])[0]
        detections=[];draw=ImageDraw.Draw(im)
        for box,label,score in zip(pred['boxes'],pred['labels'],pred['scores']):
            if float(score)<threshold:continue
            bounds=box.tolist();name=weights.meta['categories'][int(label)]
            detections.append(dict(label=name,model_score=float(score),box_xyxy_resized=bounds))
            draw.rectangle(bounds,outline='red',width=3);draw.text((bounds[0],bounds[1]),f'{name} {float(score):.2f}',fill='red')
        out=project/'results/semantics';out.mkdir(parents=True,exist_ok=True)
        annotated=out/(image_path.stem+'_detections.jpg');im.save(annotated)
        result=dict(status='available',image=str(image_path),model='TorchVision SSDLite320 MobileNetV3 Large COCO',
                    threshold=threshold,device='CPU',detections=detections,annotated_image=str(annotated),
                    limitations='Generic COCO predictions, not trained/validated on this aerial dataset. Scores are uncalibrated model outputs. Does not support buildings, roads, vegetation or debris as dedicated classes. No 3D object projection.')
        (out/(image_path.stem+'.json')).write_text(json.dumps(result,indent=2))
        return result
    except Exception as exc:
        return {'status':'optional/unavailable','reason':f'{type(exc).__name__}: {exc}'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image',type=Path);p.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--allow-download',action='store_true')
    a=p.parse_args();print(json.dumps(detect(a.image,a.project,a.allow_download),indent=2))
