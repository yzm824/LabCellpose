"""Experimental multichannel Cellpose runner. No lab-specific field/channel constants."""
from pathlib import Path, PurePosixPath
import argparse, base64, csv, hashlib, html, importlib.metadata, io, json, os, platform
import re, sys, time, zipfile, xml.etree.ElementTree as ET

VERSION = '1.2'
SKILL_ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = '0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''): h.update(b)
    return h.hexdigest()

def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def natural(value):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', str(value))]

def resolve(base, path):
    p = Path(path).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()

def read_source(path, member=None):
    if member is None: return Path(path).read_bytes()
    p = PurePosixPath(member)
    if p.is_absolute() or '..' in p.parts: raise ValueError('Unsafe ZIP member name')
    with zipfile.ZipFile(path) as z:
        info = z.getinfo(member)
        if info.file_size > 512 << 20: raise ValueError('One image exceeds prototype 512 MiB limit')
        return z.read(member)

def read_stack(raw):
    import numpy as np
    import tifffile
    with tifffile.TiffFile(io.BytesIO(raw)) as tf:
        arrays = []
        axes = tf.series[0].axes
        for p in tf.pages:
            if p.samplesperpixel != 1 or len(p.shape) != 2:
                raise ValueError('Only 2D grayscale TIFF pages are supported; RGB/packed axes rejected')
            a = p.asarray()
            if a.dtype not in [np.dtype('uint8'), np.dtype('uint16')]:
                raise ValueError(f'Unsupported dtype {a.dtype}; preserve raw data and adapt explicitly')
            if arrays and (a.shape != arrays[0].shape or a.dtype != arrays[0].dtype):
                raise ValueError('TIFF channels have different dimensions/dtypes')
            arrays.append(a)
        if not arrays: raise ValueError('Empty TIFF')
    return np.stack(arrays), axes

def leica_metadata(raw):
    root = ET.fromstring(raw)
    desc = list(root.iter('ChannelDescription'))
    if not desc: return {'status':'unrecognized_xml'}
    dims = list(root.iter('DimensionDescription'))
    if any(int(e.get('DimID','0')) not in (1,2) and int(e.get('NumberOfElements','1')) > 1 for e in dims):
        raise ValueError('XML declares nontrivial Z/T/other axes; not a 2D channel stack')
    settings = list(root.iter('ATLCameraSettingDefinition'))
    if any(int(e.get('Sections','1')) != 1 or int(e.get('CycleCount','1')) != 1 for e in settings):
        raise ValueError('XML declares Z or time series')
    entries = []
    for e in root.iter('WideFieldChannelInfo'):
        cam = e.find('.//IndividualCameraInfo')
        if cam is not None:
            entries.append((e,cam))
    if len(entries) < len(desc): raise ValueError('Incomplete saved-channel acquisition metadata')
    channels = []
    for d,(e,c) in zip(desc,entries):
        if d.get('LUTName') != c.get('LUT'): raise ValueError('Ambiguous XML channel order')
        channels.append(dict(lut=d.get('LUTName'), preset=e.get('UserDefName'),
            modality=e.get('ContrastingMethodName'), exposure_seconds=float(c.get('ExposureTime')),
            excitation_nm=float(c.get('ExcitationWavelength','0')), emission_nm=float(c.get('EmissionWavelength','0')),
            gain=c.get('Gain'), recorded_max=float(d.get('Max')), marker_identity=None))
    spacing={}
    for d in dims:
        if d.get('DimID') in ('1','2') and d.get('Unit')=='m':
            spacing[d.get('DimID')]=float(d.get('Length'))/int(d.get('NumberOfElements'))*1e6
    return dict(status='leica_2d_saved_channels',channels=channels,
        pixel_size_um=[spacing['1'],spacing['2']] if set(spacing)=={'1','2'} else None,
        axis_evidence='Saved channel descriptions and XY-only dimensions; one section/cycle',
        auxiliary_camera_entries_ignored=len(entries)-len(desc))

def locate_metadata(path, member):
    if member:
        candidate=str(PurePosixPath(member).parent / 'MetaData' / (PurePosixPath(member).stem+'.xml'))
        with zipfile.ZipFile(path) as z:
            return (z.read(candidate),candidate) if candidate in z.namelist() else (None,None)
    candidate=Path(path).parent/'MetaData'/(Path(path).stem+'.xml')
    return (candidate.read_bytes(),str(candidate)) if candidate.exists() else (None,None)

def inspect_input(path, out):
    import numpy as np
    path=Path(path).resolve()
    if Path(out).exists(): raise ValueError('Inventory output already exists')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            files=[(path,n) for n in sorted(z.namelist(),key=natural) if n.lower().endswith(('.tif','.tiff')) and '__MACOSX' not in n]
    elif path.is_dir(): files=[(p,None) for p in sorted(path.rglob('*'),key=natural) if p.suffix.lower() in ('.tif','.tiff')]
    else: files=[(path,None)]
    records=[]
    for p,member in files:
        record=dict(path=str(p),member=member,status='unsupported')
        try:
            a,axes=read_stack(read_source(p,member))
            record.update(shape=list(a.shape),dtype=str(a.dtype),tiff_axes=axes)
            raw,where=locate_metadata(p,member);record['metadata_location']=where
            meta=leica_metadata(raw) if raw else {'status':'missing'}
            if meta.get('channels') and len(meta['channels'])!=len(a):
                raise ValueError('TIFF/XML channel count mismatch')
        except (ValueError,ET.ParseError,OSError,KeyError,zipfile.BadZipFile) as e:
            record['error']=f'{type(e).__name__}: {e}'
            records.append(record)
            continue
        stats=[]
        for i,plane in enumerate(a):
            limit=meta.get('channels',[{}]*len(a))[i].get('recorded_max') if meta.get('channels') else None
            stats.append(dict(page=i,median=float(np.median(plane)),p999=float(np.percentile(plane,99.9)),
                max=int(plane.max()),recorded_limit=limit,at_recorded_limit=int(np.count_nonzero(plane>=limit)) if limit is not None else None))
        record.update(status='inspected',metadata=meta,channel_statistics=stats)
        records.append(record)
    counts={status:sum(r['status']==status for r in records) for status in ['inspected','unsupported']}
    dump(out,dict(input=str(path),tiffs=len(records),counts=counts,records=records))
    print(json.dumps({'inventory':str(out),'tiffs':len(records),'counts':counts}))

def validate_config(c):
    if c.get('schema_version')!=1 or c.get('plane_axis')!='channel' or not c.get('axis_evidence'):
        raise ValueError('Explicit channel-axis declaration and evidence required')
    channels=c['channels']; ids=[x['id'] for x in channels]
    if len(set(ids))!=len(ids) or not ids: raise ValueError('Channel IDs must be unique')
    if sorted(x['page'] for x in channels)!=list(range(len(channels))): raise ValueError('Declare every page exactly once')
    for x in channels:
        if not re.fullmatch(r'[A-Za-z0-9_-]+',x['id']): raise ValueError('Unsafe channel ID')
        if x.get('measure') and x.get('kind')!='fluorescence': raise ValueError('Only declared fluorescence channels may be measured')
    measured=[x['id'] for x in channels if x.get('measure')]
    seg=c['segmentation_channels']
    if not measured or not seg or len(set(seg))!=len(seg) or not set(seg)<=set(ids): raise ValueError('Invalid channel roles')
    b=c['background']
    if b['mask_channel'] not in seg or b['foreground_channel'] not in measured: raise ValueError('Invalid background reference')
    if b['mad_multiplier']<=0 or not isinstance(b['dilation_iterations'],int) or b['dilation_iterations']<0: raise ValueError('Invalid foreground parameters')
    if not 0<=b['min_fraction']<1 or b['min_pixels']<1 or c['edge_width_px']<=0: raise ValueError('Invalid region/background settings')
    if c['parameters'].get('do_3D') is not False: raise ValueError('3D is outside prototype scope')
    field_ids=[f['id'] for f in c['fields']]
    if not field_ids or len(set(field_ids))!=len(field_ids) or any(not re.fullmatch(r'[A-Za-z0-9_-]+',i) for i in field_ids): raise ValueError('Fields need unique safe IDs')
    for r in c.get('ratios',[]):
        if r['numerator'] not in measured or r['denominator'] not in measured: raise ValueError('Ratios require measured fluorescence channels')

def load_fields(c, base):
    data={}; records=[]
    for f in c['fields']:
        p=resolve(base,f['path']);raw=read_source(p,f.get('member'));a,axes=read_stack(raw)
        if a.shape[0]!=len(c['channels']): raise ValueError(f"{f['id']}: declared channels do not match TIFF pages")
        xml,where=locate_metadata(p,f.get('member'))
        if f.get('metadata_member'): xml=read_source(p,f['metadata_member']);where=f['metadata_member']
        elif f.get('metadata_path'): where=str(resolve(base,f['metadata_path']));xml=Path(where).read_bytes()
        meta=leica_metadata(xml) if xml else {'status':'missing'}
        if meta.get('channels') and len(meta['channels'])!=len(c['channels']): raise ValueError('TIFF/XML channel count mismatch')
        exposures={};limits={};chmeta={}
        for ch in c['channels']:
            cid=ch['id'];mc=meta['channels'][ch['page']] if meta.get('channels') else {}
            if mc.get('modality')=='TL-PH' and ch.get('measure'): raise ValueError(f'{cid}: phase contrast is not fluorescence')
            exposures[cid]=f.get('exposure_seconds',{}).get(cid,mc.get('exposure_seconds'))
            limits[cid]=ch.get('saturation_value',mc.get('recorded_max'))
            if limits[cid] is not None and not 0<limits[cid]<=__import__('numpy').iinfo(a.dtype).max: raise ValueError('Invalid saturation limit')
            chmeta[cid]=mc
        data[f['id']]={'planes':{x['id']:a[x['page']] for x in c['channels']},'metadata':meta,'exposures':exposures,
            'limits':limits,'pixel_size_um':f.get('pixel_size_um',meta.get('pixel_size_um')),'channel_metadata':chmeta}
        records.append(dict(field=f['id'],path=str(p),member=f.get('member'),input_sha256=digest(raw),shape=list(a.shape),dtype=str(a.dtype),tiff_axes=axes,
            metadata_location=where,metadata_sha256=digest(xml) if xml else None,metadata=meta,exposures=exposures,limits=limits))
    return data,records

def contours(mask):
    import numpy as np
    from skimage.measure import find_contours,approximate_polygon
    paths=[]
    for p in find_contours(np.pad(mask.astype('uint8'),1),.5):
        xy=approximate_polygon(p,tolerance=.45)-.5
        paths.append('M'+'L'.join(f'{x:.1f},{y:.1f}' for y,x in xy)+'Z')
    return ''.join(paths)

def make_background(planes,masks,c):
    import numpy as np
    from scipy import ndimage as ndi
    b=c['background'];a=planes[b['foreground_channel']].astype(float)
    med=float(np.median(a));mad=float(np.median(np.abs(a-med)))
    cutoff=med+b['mad_multiplier']*1.4826*mad
    exclude=(masks[b['mask_channel']]>0)|(a>cutoff)
    if b['dilation_iterations']>0: exclude=ndi.binary_dilation(exclude,iterations=b['dilation_iterations'])
    bg=~exclude;count=int(bg.sum());valid=count>=max(b['min_pixels'],b['min_fraction']*bg.size)
    values={cid:float(np.median(p[bg])) if count else None for cid,p in planes.items()}
    return bg,values,dict(method='anchor-mask-mad-v1',pixels=count,fraction=count/bg.size,valid=valid,foreground_cutoff=cutoff,medians=values)

def measure_field(fid,planes,labels,channel,background,bg_valid,c,limits):
    import numpy as np
    from scipy import ndimage as ndi
    objects=[];rows=[];h,w=labels.shape
    for ident,sl in enumerate(ndi.find_objects(labels),1):
        if sl is None: continue
        y0,y1=sl[0].start,sl[0].stop;x0,x1=sl[1].start,sl[1].stop
        whole=labels[sl]==ident
        distances=ndi.distance_transform_edt(np.pad(whole,1))[1:-1,1:-1]
        edge=whole&(distances<=c['edge_width_px']);interior=whole&~edge
        assert not np.any(edge&interior) and int(edge.sum()+interior.sum())==int(whole.sum())
        o=dict(id=ident,bbox=[x0,y0,x1,y1],edgeTouch=x0==0 or y0==0 or x1==w or y1==h,regions={})
        for key,mask in [('whole',whole),('edge',edge),('interior',interior)]:
            area=int(mask.sum());r=dict(area=area,path=contours(mask),offset=[x0,y0],channels={}) if area else None
            for ch in c['channels']:
                if not ch.get('measure'): continue
                cid=ch['id'];a=planes[cid][sl][mask];b=background[cid]
                mean=float(a.mean()) if area else None;total=int(a.sum(dtype=np.uint64)) if area else None
                corrected=mean-b if area and bg_valid else None
                corrected_sum=total-area*b if area and bg_valid else None
                sat=int(np.count_nonzero(a>=limits[cid])) if area and limits[cid] is not None else None
                m=dict(mean=mean,background=b,corrected=corrected,sum=total,correctedSum=corrected_sum,saturated=sat)
                if r: r['channels'][cid]=m
                rows.append(dict(field=fid,segmentation_channel=channel,object_id=ident,region=key,measurement_channel=cid,
                    area_pixels=area if area else None,raw_mean=mean,background_median=b,corrected_mean=corrected,
                    raw_sum=total,corrected_sum=corrected_sum,saturated_pixels=sat,saturation_limit=limits[cid],
                    touches_image_edge=o['edgeTouch'],background_valid=bg_valid,expert_validated=False))
            o['regions'][key]=r
        objects.append(o)
    return objects,rows

def display_image(a,lo,hi,mode):
    import numpy as np
    from PIL import Image
    if mode=='auto':
        scale=max((hi-lo)/15,1)
        gray=np.clip(np.arcsinh(np.maximum(a.astype(float)-lo,0)/scale)/np.arcsinh(max(hi-lo,1)/scale),0,1)
    else: gray=np.clip((a.astype(float)-lo)/max(hi-lo,1),0,1)
    im=Image.fromarray(np.round(gray*255).astype('uint8'));im.thumbnail((640,640),Image.Resampling.LANCZOS)
    s=io.BytesIO();im.save(s,format='JPEG',quality=82)
    return 'data:image/jpeg;base64,'+base64.b64encode(s.getvalue()).decode()

def write_csv(path,rows,fieldnames=None):
    if fieldnames is None: fieldnames=list(rows[0])
    with Path(path).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(rows)

def build_viewer(c,data,out,runinfo):
    from render_review import render
    render(c,data,Path(out/'measurements.csv').read_bytes().decode('utf-8'),runinfo,out/'index.html')

def run(args):
    import numpy as np
    from scipy import ndimage as ndi
    import tifffile
    started=time.time();config_path=Path(args.config).resolve();c=json.loads(config_path.read_text());validate_config(c)
    out=Path(args.out).resolve();weights=Path(args.weights).resolve()
    if out.exists(): raise ValueError('Output directory exists; use a NEW directory (no implicit resume or overwrites)')
    if args.weights_sha256!=MODEL_SHA256: raise ValueError('Prototype model is pinned to cpsam_v2; another checkpoint requires a separately validated method revision')
    if not weights.is_file() or file_sha(weights)!=args.weights_sha256: raise ValueError('Model weights missing or SHA256 mismatch')
    expected={'cellpose':'4.2.1.1','torch':'2.14.0','numpy':'2.5.3','scipy':'1.18.1','scikit-image':'0.26.0','tifffile':'2026.9.20','pillow':'12.3.0'}
    versions={k:importlib.metadata.version(k) for k in expected}
    if versions!=expected: raise ValueError(f'Runtime differs from prototype lock: {versions}')
    data,inputs=load_fields(c,config_path.parent)
    out.mkdir(parents=True);(out/'masks').mkdir();(out/'background_masks').mkdir()
    saved_config=json.loads(json.dumps(c))
    for field in saved_config['fields']:
        for key in ['path','metadata_path']:
            if field.get(key):field[key]=str(resolve(config_path.parent,field[key]))
    dump(out/'config.json',saved_config)
    dump(out/'submitted_config.json',c)
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    os.environ.setdefault('CELLPOSE_LOCAL_MODELS_PATH',str(weights.parent))
    os.environ.setdefault('MPLCONFIGDIR',str(out/'.cache/mpl'))
    manifest=dict(version=VERSION,status='running',config_sha256=file_sha(config_path),code_sha256=file_sha(__file__),
        support_code_sha256={p.name:file_sha(p) for p in Path(__file__).parent.glob('*.py')},
        template_sha256={p.name:file_sha(p) for p in (SKILL_ROOT/'assets').iterdir() if p.is_file()},model_sha256=args.weights_sha256,
        model_name='cpsam_v2',model_path=str(weights),versions=versions,python=platform.python_version(),inputs=inputs,
        background_method='anchor-mask-mad-v1',seed=24,precision='float32',masks=[],notes=c.get('notes',[]))
    dump(out/'run_manifest.json',manifest)
    try:
        import torch
        from cellpose import models
        device=args.device
        if device=='auto': device='cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        torch.set_num_threads(6);torch.manual_seed(24);np.random.seed(24)
        manifest['device']=device;manifest['threads']=6;dump(out/'run_manifest.json',manifest)
        model=models.CellposeModel(gpu=device!='cpu',device=torch.device(device),pretrained_model=str(weights),use_bfloat16=False)
        print(json.dumps({'event':'model_ready','device':device}),flush=True)
        viewer={};all_rows=[];field_rows=[];validation={'fields':{},'objects':0,'measurement_rows':0,'max_sampled_raw_mean_error':0.0}
        fixed={ch['id']:(min(float(np.percentile(f['planes'][ch['id']],10)) for f in data.values()),max(float(np.percentile(f['planes'][ch['id']],99.9)) for f in data.values())) for ch in c['channels']}
        changed_exposure={ch['id']:sorted({f['exposures'][ch['id']] for f in data.values() if f['exposures'][ch['id']] is not None}) for ch in c['channels']}
        for fid,f in data.items():
            planes=f['planes'];shape=next(iter(planes.values())).shape;masks={}
            for cid in c['segmentation_channels']:
                torch.manual_seed(24);np.random.seed(24);t=time.time()
                lab=np.asarray(model.eval(planes[cid],**c['parameters'])[0])
                if lab.shape!=shape or not np.issubdtype(lab.dtype,np.integer) or lab.min()<0: raise ValueError('Invalid Cellpose label map')
                lab=lab.astype('uint32');masks[cid]=lab
                dst=out/'masks'/f'{fid}_{cid}.tif';tifffile.imwrite(dst,lab,photometric='minisblack')
                record=dict(field=fid,channel=cid,objects=int(np.count_nonzero(np.unique(lab))),seconds=time.time()-t,sha256=file_sha(dst))
                manifest['masks'].append(record);dump(out/'run_manifest.json',manifest);print(json.dumps(record),flush=True)
            bg,bgs,bgm=make_background(planes,masks,c);tifffile.imwrite(out/'background_masks'/f'{fid}.tif',bg.astype('uint8'),photometric='minisblack')
            vf=dict(shape=list(shape),images={},fixedImages={},displaySettings={},objects={},background=bgm,
                backgroundPath=contours(bg),exposures=f['exposures'],pixelSizeUm=f['pixel_size_um'],warnings=[])
            if not bgm['valid']: vf['warnings'].append('Insufficient background pixels; corrected values unavailable.')
            for ch in c['channels']:
                cid=ch['id'];a=planes[cid];lo,hi=[float(x) for x in np.percentile(a,[10,99.9])]
                vf['images'][cid]=display_image(a,lo,hi,'auto');flo,fhi=fixed[cid];vf['fixedImages'][cid]=display_image(a,flo,fhi,'fixed')
                vf['displaySettings'][cid]={'auto':{'lower_raw':lo,'upper_raw':hi},'fixed':{'lower_raw':flo,'upper_raw':fhi}}
                if ch.get('measure') and len(changed_exposure[cid])>1: vf['warnings'].append(f'{ch["label"]}: exposure differs between fields; raw intensity is not normalized.')
            fieldcheck={}
            for cid,lab in masks.items():
                obs,rows=measure_field(fid,planes,lab,cid,bgs,bgm['valid'],c,f['limits']);vf['objects'][cid]=obs
                for row in rows: row['exposure_seconds']=f['exposures'][row['measurement_channel']]
                all_rows.extend(rows);validation['objects']+=len(obs)
                # Independent raw-pixel check from saved native labels for several objects per field/input.
                saved=tifffile.imread(out/'masks'/f'{fid}_{cid}.tif')
                for o in obs[:3]:
                    for ch in c['channels']:
                        if ch.get('measure'):
                            err=abs(float(planes[ch['id']][saved==o['id']].mean())-o['regions']['whole']['channels'][ch['id']]['mean'])
                            validation['max_sampled_raw_mean_error']=max(validation['max_sampled_raw_mean_error'],err)
                            if err>1e-9: raise AssertionError('Raw measurement check failed')
                for ch in c['channels']:
                    if not ch.get('measure'): continue
                    for region in ['whole','edge','interior']:
                        rr=[o['regions'][region] for o in obs if o['regions'][region] is not None]
                        values=[r['channels'][ch['id']]['corrected'] for r in rr if r['channels'][ch['id']]['corrected'] is not None]
                        sat=[r['channels'][ch['id']]['saturated'] for r in rr]
                        field_rows.append(dict(field=fid,segmentation_channel=cid,measurement_channel=ch['id'],region=region,
                            candidates=len(obs),available_rois=len(rr),corrected_rois=len(values),median_corrected=float(np.median(values)) if values else None,
                            negative_corrected_rois=sum(v<0 for v in values),rois_with_saturation=sum(s>0 for s in sat if s is not None) if all(s is not None for s in sat) else None,
                            exposure_seconds=f['exposures'][ch['id']],background_fraction=bgm['fraction']))
                fieldcheck[cid]={'candidates':len(obs),'region_partition_verified':True}
            viewer[fid]=vf;validation['fields'][fid]=fieldcheck
        cols=['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','background_median','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge','background_valid','expert_validated','exposure_seconds']
        write_csv(out/'measurements.csv',all_rows,cols);write_csv(out/'field_summary.csv',field_rows)
        expected_rows=validation['objects']*3*sum(bool(ch.get('measure')) for ch in c['channels'])
        assert len(all_rows)==expected_rows
        validation.update(measurement_rows=len(all_rows),expected_rows=expected_rows,passed=True,
            exposure_changes={k:v for k,v in changed_exposure.items() if len(v)>1},expert_ground_truth=False)
        dump(out/'viewer_data.json',{'config':c,'fields':viewer})
        build_viewer(c,viewer,out,{'version':VERSION,'device':device,'exposureChanges':validation['exposure_changes']})
        dump(out/'validation.json',validation)
        manifest.update(status='complete',seconds=time.time()-started,validation=validation,
            outputs_sha256={n:file_sha(out/n) for n in ['index.html','measurements.csv','field_summary.csv','viewer_data.json','validation.json']})
        dump(out/'run_manifest.json',manifest)
        print(json.dumps({'event':'complete','out':str(out),'objects':validation['objects'],'rows':len(all_rows),'seconds':manifest['seconds']}),flush=True)
    except BaseException as e:
        manifest.update(status='failed',error=f'{type(e).__name__}: {e}')
        dump(out/'run_manifest.json',manifest)
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    s.add_parser('doctor')
    i=s.add_parser('inspect');i.add_argument('--input',required=True);i.add_argument('--out',required=True)
    r=s.add_parser('run');r.add_argument('--config',required=True);r.add_argument('--out',required=True);r.add_argument('--weights',required=True);r.add_argument('--weights-sha256',required=True);r.add_argument('--device',choices=['auto','cpu','mps','cuda'],default='auto')
    a=p.parse_args()
    if a.command=='doctor':
        print(json.dumps({'python':platform.python_version(),'versions':{k:importlib.metadata.version(k) for k in ['cellpose','torch','numpy','scipy','scikit-image','tifffile','pillow']}}))
    elif a.command=='inspect': inspect_input(a.input,a.out)
    else: run(a)

if __name__=='__main__': main()
