"""Experimental multichannel Cellpose runner. No lab-specific field/channel constants."""
from pathlib import Path, PurePosixPath
import argparse, base64, csv, hashlib, html, importlib.metadata, io, json, os, platform
import math, re, stat, struct, sys, time, zipfile, zlib, xml.etree.ElementTree as ET
from contextlib import contextmanager

VERSION = '2.0'
SKILL_ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = '0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667'

# Allocation/work budgets, checked before decoding. Split larger experiments into runs.
MAX_IMAGE_BYTES = 512 << 20
MAX_METADATA_BYTES = 8 << 20
MAX_ARCHIVE_BYTES = 4 << 30
MAX_ZIP_ENTRIES = 10000
MAX_DIRECTORY_ENTRIES = 10000
MAX_FIELDS = 512
MAX_CHANNELS = 32
MAX_PLANE_PIXELS = 4096 * 4096
MAX_STACK_BYTES = 128 << 20
MAX_BATCH_BYTES = 256 << 20
MAX_INSPECT_BYTES = 2 << 30
MAX_SEGMENTATION_TASKS = 256
MAX_OBJECTS = 50000
MAX_MEASUREMENT_ROWS = 500000
# Cellpose resizes each image by 30/diameter before inference; bound the enlarged image.
CELLPOSE_REFERENCE_DIAMETER = 30.0
MAX_SCALED_PIXELS = 8192 * 8192
# Every completed run must open in the review window: the rebuilt report is served with this limit.
REVIEW_REPORT_LIMIT = 128 << 20
REVIEW_REPORT_MARGIN = 4 << 20
PREVIEW_BUDGET = 56 << 20
PREVIEW_SIDES = (1600, 1280, 1024, 896, 768, 640, 512, 384)
# Names that are also Object.prototype members in the browser viewer.
RESERVED_IDS = {'constructor', 'prototype', 'toString', 'toLocaleString', 'valueOf', 'hasOwnProperty',
                'isPrototypeOf', 'propertyIsEnumerable'}
SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
CELLPOSE_PARAMETERS = {'diameter', 'flow_threshold', 'cellprob_threshold', 'min_size', 'normalize', 'niter', 'batch_size', 'do_3D'}

class ResourceLimitError(ValueError):
    pass

def limited_read(path, limit):
    # Open without blocking (FIFOs/devices) and read only regular files.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise ValueError(f'{Path(path).name} is not a regular file')
        if info.st_size > limit:
            raise ResourceLimitError(f'File exceeds the {limit >> 20} MiB input limit; split or export a smaller input.')
        with os.fdopen(fd, 'rb', closefd=False) as stream: raw = stream.read(limit + 1)
    finally: os.close(fd)
    if len(raw) > limit: raise ResourceLimitError('Input grew beyond its byte limit; re-scan a smaller input.')
    return raw

def safe_id(value):
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None and value not in RESERVED_IDS

def scaled_pixels(shape, diameter):
    """Pixels of the image Cellpose actually segments after its 30/diameter resize."""
    scale = CELLPOSE_REFERENCE_DIAMETER / diameter if diameter else 1.0
    return shape[-2] * shape[-1] * scale * scale

def check_scaled_size(shape, diameter, name):
    if diameter and scaled_pixels(shape, diameter) > MAX_SCALED_PIXELS:
        side = round(max(shape[-2:]) * CELLPOSE_REFERENCE_DIAMETER / diameter)
        minimum = math.ceil(CELLPOSE_REFERENCE_DIAMETER * math.sqrt(shape[-2] * shape[-1] / MAX_SCALED_PIXELS))
        raise ResourceLimitError(f'{name}: a cell diameter of {diameter:g} px would enlarge the image to about {side} px per side '
                                 f'for segmentation (limit {int(math.sqrt(MAX_SCALED_PIXELS))} px). Use a diameter of at least {minimum} px or smaller images.')

@contextmanager
def open_archive(path):
    # Bound the central directory before ZipFile materializes its entry objects.
    with Path(path).open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        if size > MAX_ARCHIVE_BYTES: raise ResourceLimitError('ZIP exceeds 4 GiB; split the archive.')
        stream.seek(max(0, size - 65557)); tail = stream.read(65557)
        at = tail.rfind(b'PK\x05\x06')
        if at < 0 or len(tail) - at < 22: raise ValueError('Invalid ZIP end record')
        _, disk, start_disk, disk_count, count, directory_size, offset, comment = struct.unpack_from('<4s4H2IH', tail, at)
        if len(tail) - at != 22 + comment: raise ValueError('Invalid ZIP comment length')
        if disk or start_disk or disk_count != count: raise ValueError('Multi-volume ZIP files are not supported')
        if count == 65535 or directory_size == 0xffffffff or offset == 0xffffffff or b'PK\x06\x07' in tail[max(0, at-20):at]:
            raise ResourceLimitError('ZIP64 input is not supported; export a smaller ZIP or select a smaller image folder.')
        if count > MAX_ZIP_ENTRIES or directory_size > (8 << 20):
            raise ResourceLimitError('ZIP contains too many entries; split the archive.')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            if len(archive.infolist()) > MAX_ZIP_ENTRIES: raise ResourceLimitError('ZIP contains too many entries')
            names = archive.namelist()
            if len(names) != len(set(names)): raise ValueError('ZIP contains duplicate member names; export an unambiguous archive.')
            yield archive

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

def read_source(path, member=None, limit=MAX_IMAGE_BYTES):
    if member is None: return limited_read(path, limit)
    p = PurePosixPath(member)
    if p.is_absolute() or '..' in p.parts: raise ValueError('Unsafe ZIP member name')
    with open_archive(path) as z:
        info = z.getinfo(member)
        if info.file_size > limit: raise ResourceLimitError(f'ZIP member exceeds the {limit >> 20} MiB input limit')
        with z.open(info) as stream: raw = stream.read(limit + 1)
        if len(raw) > limit: raise ResourceLimitError('ZIP member exceeds its byte limit')
        return raw

def validate_2d_axes(axes, plane_count):
    # Unknown Q/I page axes still need explicit channel confirmation in the config.
    if plane_count > 1 and any(axis in axes for axis in ('Z', 'T')):
        raise ValueError('TIFF declares Z/time axes; export registered 2D channel pages first.')

def read_stack(raw, remaining_bytes=None):
    import numpy as np
    import tifffile
    if len(raw) > MAX_IMAGE_BYTES: raise ResourceLimitError('TIFF container exceeds the input byte limit')
    try:
        with tifffile.TiffFile(io.BytesIO(raw)) as tf:
            pages = []; decoded = 0
            for p in tf.pages:
                if len(pages) >= MAX_CHANNELS: raise ResourceLimitError('TIFF exceeds 32 channels; export a smaller 2D stack.')
                if p.samplesperpixel != 1 or len(p.shape) != 2:
                    raise ValueError('Only 2D grayscale TIFF pages are supported; RGB/packed axes rejected')
                if p.dtype not in [np.dtype('uint8'), np.dtype('uint16')]:
                    raise ValueError(f'Unsupported dtype {p.dtype}; preserve raw data and adapt explicitly')
                pixels = math.prod(p.shape)
                if min(p.shape) < 1 or max(p.shape) > 8192 or pixels > MAX_PLANE_PIXELS:
                    raise ResourceLimitError('TIFF exceeds the 16-megapixel plane limit; export smaller fields.')
                decoded += pixels * p.dtype.itemsize
                if decoded > MAX_STACK_BYTES: raise ResourceLimitError('TIFF exceeds 128 MiB of decoded pixels; export a smaller stack.')
                if remaining_bytes is not None and decoded > remaining_bytes:
                    raise ResourceLimitError('Batch exceeds its decoded-pixel budget; select fewer fields or split the input folder.')
                if pages and (p.shape != pages[0].shape or p.dtype != pages[0].dtype):
                    raise ValueError('TIFF channels have different dimensions/dtypes')
                pages.append(p)
            if not pages: raise ValueError('Empty TIFF: no image pages')
            axes = tf.series[0].axes
            for series in tf.series: validate_2d_axes(series.axes, len(pages))
            arrays = np.empty((len(pages), *pages[0].shape), dtype=pages[0].dtype)
            for index, page in enumerate(pages): arrays[index] = page.asarray()
        return arrays, axes
    except ValueError:
        raise
    except MemoryError as error:
        raise ResourceLimitError('Not enough memory to decode this TIFF; export a smaller stack.') from error
    except Exception as error:
        # Malformed tags reach decoder arithmetic (e.g. TileLength=0 -> ZeroDivisionError); isolate per file.
        raise ValueError(f'Invalid or truncated TIFF: {type(error).__name__}: {error}') from error

def metadata_number(element, attribute, *, integer=False, default=None, positive=False):
    value = element.get(attribute)
    if value is None or not value.strip(): return default
    try:
        number = int(value) if integer else float(value)
        if not math.isfinite(number) or (number <= 0 if positive else number < 0):
            raise ValueError()
    except (ValueError, OverflowError):
        raise ValueError(f'Invalid XML {element.tag}.{attribute}: {value!r}') from None
    return number

def leica_metadata(raw):
    if len(raw) > MAX_METADATA_BYTES: raise ResourceLimitError('XML exceeds the 8 MiB metadata limit')
    root = ET.fromstring(raw)
    desc = list(root.iter('ChannelDescription'))
    if not desc: return {'status':'unrecognized_xml'}
    dims = list(root.iter('DimensionDescription'))
    dimensions = [(e, metadata_number(e,'DimID',integer=True,default=0),
                   metadata_number(e,'NumberOfElements',integer=True,default=1,positive=True)) for e in dims]
    if any(axis not in (1,2) and count > 1 for _,axis,count in dimensions):
        raise ValueError('XML declares nontrivial Z/T/other axes; not a 2D channel stack')
    settings = list(root.iter('ATLCameraSettingDefinition'))
    if any(metadata_number(e,'Sections',integer=True,default=1,positive=True) != 1 or
           metadata_number(e,'CycleCount',integer=True,default=1,positive=True) != 1 for e in settings):
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
            modality=e.get('ContrastingMethodName'), exposure_seconds=metadata_number(c,'ExposureTime',positive=True),
            excitation_nm=metadata_number(c,'ExcitationWavelength'), emission_nm=metadata_number(c,'EmissionWavelength'),
            gain=c.get('Gain'), recorded_max=metadata_number(d,'Max',positive=True), marker_identity=None))
    spacing={}
    for d,axis,count in dimensions:
        if axis in (1,2) and d.get('Unit')=='m':
            length=metadata_number(d,'Length',positive=True)
            if length is not None and d.get('NumberOfElements'):
                spacing[str(axis)]=length/count*1e6
    return dict(status='leica_2d_saved_channels',channels=channels,
        pixel_size_um=[spacing['1'],spacing['2']] if set(spacing)=={'1','2'} else None,
        axis_evidence='Saved channel descriptions and XY-only dimensions; one section/cycle',
        auxiliary_camera_entries_ignored=len(entries)-len(desc))

def locate_metadata(path, member):
    if member:
        candidate=str(PurePosixPath(member).parent / 'MetaData' / (PurePosixPath(member).stem+'.xml'))
        with open_archive(path) as z: present = candidate in z.namelist()
        return (read_source(path,candidate,MAX_METADATA_BYTES),candidate) if present else (None,None)
    candidate=Path(path).parent/'MetaData'/(Path(path).stem+'.xml')
    return (limited_read(candidate,MAX_METADATA_BYTES),str(candidate)) if candidate.exists() else (None,None)

def read_field_sources(field, base):
    path = resolve(base, field['path'])
    raw = read_source(path, field.get('member'))
    if field.get('metadata_member'):
        where = field['metadata_member']; xml = read_source(path,where,MAX_METADATA_BYTES)
    elif field.get('metadata_path'):
        where = str(resolve(base,field['metadata_path'])); xml = limited_read(where,MAX_METADATA_BYTES)
    else: xml,where = locate_metadata(path,field.get('member'))
    if 'input_sha256' in field or 'metadata_sha256' in field:
        if digest(raw) != field.get('input_sha256') or (digest(xml) if xml is not None else None) != field.get('metadata_sha256'):
            raise ValueError('Input or metadata changed after inspection; re-scan and confirm the channel assignments.')
    return path,raw,xml,where

def inspect_input(path, out):
    import numpy as np
    path=Path(path).resolve()
    if Path(out).exists(): raise ValueError('Inventory output already exists')
    if not path.is_dir() and not path.is_file(): raise ValueError('Choose a TIFF, ZIP or folder (not a special file).')
    if path.is_file() and zipfile.is_zipfile(path):
        with open_archive(path) as z:
            files=[(path,n) for n in sorted(z.namelist(),key=natural) if n.lower().endswith(('.tif','.tiff')) and '__MACOSX' not in n]
    elif path.is_dir():
        files=[]
        for index,p in enumerate(path.rglob('*')):
            if index >= MAX_DIRECTORY_ENTRIES: raise ResourceLimitError('Folder contains too many entries; select a smaller image folder.')
            if p.is_file() and p.suffix.lower() in ('.tif','.tiff'): files.append((p,None))
        files.sort(key=lambda item:natural(item[0]))
    else: files=[(path,None)]
    if len(files) > MAX_FIELDS: raise ResourceLimitError('Input exceeds 512 fields; select a smaller folder or ZIP.')
    records=[]; inspected_bytes=0
    for p,member in files:
        record=dict(path=str(p),member=member,status='unsupported')
        try:
            image_raw=read_source(p,member)
            a,axes=read_stack(image_raw,MAX_INSPECT_BYTES-inspected_bytes)
            inspected_bytes += a.nbytes
            record.update(shape=list(a.shape),dtype=str(a.dtype),tiff_axes=axes)
            raw,where=locate_metadata(p,member);record['metadata_location']=where
            record.update(input_sha256=digest(image_raw),metadata_sha256=digest(raw) if raw is not None else None)
            meta=leica_metadata(raw) if raw else {'status':'missing'}
            if meta.get('channels') and len(meta['channels'])!=len(a):
                raise ValueError('TIFF/XML channel count mismatch')
        except ResourceLimitError as e:
            if 'Batch exceeds' in str(e): raise
            record['error']=str(e);records.append(record);continue
        except Exception as e:
            # One unreadable file must never abort the inventory of the others.
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
    if len(set(ids))!=len(ids) or not 1 <= len(ids) <= MAX_CHANNELS: raise ValueError('Declare 1–32 unique channel IDs')
    if sorted(x['page'] for x in channels)!=list(range(len(channels))): raise ValueError('Declare every page exactly once')
    for x in channels:
        if not safe_id(x['id']): raise ValueError('Unsafe channel ID: use letters, digits, - or _, starting with a letter or digit')
        if x.get('measure') and x.get('kind')!='fluorescence': raise ValueError('Only declared fluorescence channels may be measured')
    measured=[x['id'] for x in channels if x.get('measure')]
    seg=c['segmentation_channels']
    if not measured or not seg or len(set(seg))!=len(seg) or not set(seg)<=set(ids): raise ValueError('Invalid channel roles')
    b=c['background']
    if b.get('estimator','median') not in ('median','mean'): raise ValueError('Background estimator must be median or mean')
    if b['mask_channel'] not in seg or b['foreground_channel'] not in measured: raise ValueError('Invalid background reference')
    if b['mad_multiplier']<=0 or not isinstance(b['dilation_iterations'],int) or b['dilation_iterations']<0: raise ValueError('Invalid foreground parameters')
    if not 0<=b['min_fraction']<1 or b['min_pixels']<1 or c['edge_width_px']<=0: raise ValueError('Invalid region/background settings')
    if c['parameters'].get('do_3D') is not False: raise ValueError('3D is outside prototype scope')
    unknown=set(c['parameters'])-CELLPOSE_PARAMETERS
    if unknown: raise ValueError('Unsupported Cellpose parameters: '+', '.join(sorted(map(str,unknown))))
    diameter=c['parameters'].get('diameter')
    if diameter is not None and (isinstance(diameter,bool) or not isinstance(diameter,(int,float)) or not math.isfinite(diameter) or diameter<=0):
        raise ValueError('Cell diameter must be a positive number of pixels')
    field_ids=[f['id'] for f in c['fields']]
    if len(field_ids)>MAX_FIELDS or len(field_ids)*len(seg)>MAX_SEGMENTATION_TASKS:
        raise ResourceLimitError('Run exceeds 512 fields or 256 segmentation tasks; select fewer fields or inputs.')
    if c.get('input_confirmation') == 'sha256-v1':
        for field in c['fields']:
            if not re.fullmatch(r'[0-9a-f]{64}',str(field.get('input_sha256',''))) or 'metadata_sha256' not in field or (field['metadata_sha256'] is not None and not re.fullmatch(r'[0-9a-f]{64}',str(field['metadata_sha256']))):
                raise ValueError('Confirmed inputs need image and metadata digests; re-scan the inputs.')
    if not field_ids or len(set(field_ids))!=len(field_ids) or not all(safe_id(i) for i in field_ids): raise ValueError('Fields need unique safe IDs (letters, digits, - or _, starting with a letter or digit)')
    for r in c.get('ratios',[]):
        if r['numerator'] not in measured or r['denominator'] not in measured: raise ValueError('Ratios require measured fluorescence channels')

def load_fields(c, base):
    data={}; records=[]; decoded=0
    for f in c['fields']:
        name=f.get('label') or f.get('member') or Path(str(f.get('path',''))).name or f['id']
        try:
            p,raw,xml,where=read_field_sources(f,base)
            a,axes=read_stack(raw,MAX_BATCH_BYTES-decoded)
        except ResourceLimitError as e: raise ResourceLimitError(f'{name}: {e}') from e
        except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e: raise ValueError(f'{name}: {e}') from e
        decoded += a.nbytes
        check_scaled_size(a.shape,c['parameters'].get('diameter'),name)
        if a.shape[0]!=len(c['channels']): raise ValueError(f"{name}: declared channels do not match TIFF pages")
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

def image_names(field):
    """Readable image file name and containing folder of an analysed field (the same rule as the report export)."""
    source=str(field.get('member') or field.get('path') or field.get('label') or field.get('id') or '')
    parts=[x for x in source.split('/') if x]
    archive=[x for x in str(field.get('path') or '').split('/') if x][-1:] if field.get('member') else []
    return (parts[-1] if parts else str(field.get('label') or field.get('id') or ''), parts[-2] if len(parts)>1 else (archive[0] if archive else ''))

def sheet_text(value):
    """Text that a spreadsheet will not evaluate as a formula (the same rule as the report's CSV exports)."""
    text=str(value or '')
    return "'"+text if re.match(r'[\s\x00-\x1f\x7f-\x9f]*[=+@-]',text) else text

def write_field_index(out,c):
    """fields.csv: which image each field ID (used in CSV rows and mask file names) refers to."""
    rows=[]
    for f in c['fields']:
        name,folder=map(sheet_text,image_names(f))
        rows.append(dict(field=f['id'],image_name=name,image_folder=folder,source_path=sheet_text(f.get('path','')),archive_member=sheet_text(f.get('member')),
            input_sha256=f.get('input_sha256',''),masks='; '.join(f"masks/{f['id']}_{cid}.tif" for cid in c['segmentation_channels']),
            background_mask=f"background_masks/{f['id']}.tif"))
    write_csv(out/'fields.csv',rows,['field','image_name','image_folder','source_path','archive_member','input_sha256','masks','background_mask'])

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
    medians={cid:float(np.median(p[bg])) if count else None for cid,p in planes.items()}
    means={cid:float(np.mean(p[bg],dtype=np.float64)) if count else None for cid,p in planes.items()}
    estimator=b.get('estimator','median')
    if estimator not in ('median','mean'): raise ValueError('Background estimator must be median or mean')
    return bg,(means if estimator=='mean' else medians),dict(method='anchor-mask-mad-v1',estimator=estimator,pixels=count,fraction=count/bg.size,valid=valid,foreground_cutoff=cutoff,medians=medians,means=means)

def measure_field(fid,planes,labels,channel,background,bg_valid,c,limits,background_stats=None):
    import numpy as np
    from scipy import ndimage as ndi
    objects=[];rows=[];h,w=labels.shape
    estimator=c['background'].get('estimator','median')
    if estimator not in ('median','mean') or (estimator=='mean' and (not background_stats or 'means' not in background_stats or 'medians' not in background_stats)):
        raise ValueError('Mean correction requires recorded background statistics')
    if background_stats is not None and background != background_stats['means' if estimator=='mean' else 'medians']:
        raise ValueError('Selected background values do not match the estimator')
    for ident,sl in enumerate(ndi.find_objects(labels),1):
        if sl is None: continue
        y0,y1=sl[0].start,sl[0].stop;x0,x1=sl[1].start,sl[1].stop
        whole=labels[sl]==ident
        distances=ndi.distance_transform_edt(np.pad(whole,1))[1:-1,1:-1]
        edge=whole&(distances<=c['edge_width_px']);interior=whole&~edge
        assert not np.any(edge&interior) and int(edge.sum()+interior.sum())==int(whole.sum())
        o=dict(id=ident,bbox=[x0,y0,x1,y1],edgeTouch=x0==0 or y0==0 or x1==w or y1==h,regions={})
        for key,mask in [('whole',whole),('edge',edge),('interior',interior)]:
            area=int(mask.sum())
            # The inner-band outline equals the whole outline plus the interior outline (even-odd fill); the
            # viewer rebuilds it. Corrected values are recomputed in the viewer from the field background stats.
            r=dict(area=area,path=None if key=='edge' else contours(mask),offset=[x0,y0],channels={}) if area else None
            for ch in c['channels']:
                if not ch.get('measure'): continue
                cid=ch['id'];a=planes[cid][sl][mask];b=background[cid]
                mean=float(a.mean()) if area else None;total=int(a.sum(dtype=np.uint64)) if area else None
                corrected=mean-b if area and bg_valid else None
                corrected_sum=total-area*b if area and bg_valid else None
                sat=int(np.count_nonzero(a>=limits[cid])) if area and limits[cid] is not None else None
                bg_median=(background_stats or {}).get('medians',background)[cid]
                bg_mean=(background_stats or {}).get('means',{}).get(cid)
                if r: r['channels'][cid]=dict(mean=mean,sum=total,saturated=sat)
                rows.append(dict(field=fid,segmentation_channel=channel,object_id=ident,region=key,measurement_channel=cid,
                    area_pixels=area if area else None,raw_mean=mean,background_median=bg_median,background_mean=bg_mean,
                    background_estimator=estimator,background_value=b,corrected_mean=corrected,
                    raw_sum=total,corrected_sum=corrected_sum,saturated_pixels=sat,saturation_limit=limits[cid],
                    touches_image_edge=o['edgeTouch'],background_valid=bg_valid,expert_validated=False))
            o['regions'][key]=r
        objects.append(o)
    return objects,rows

def display_image(a,lo,hi,mode,side=PREVIEW_SIDES[0]):
    import numpy as np
    from PIL import Image
    if mode=='auto':
        scale=max((hi-lo)/15,1)
        gray=np.clip(np.arcsinh(np.maximum(a.astype(float)-lo,0)/scale)/np.arcsinh(max(hi-lo,1)/scale),0,1)
    else: gray=np.clip((a.astype(float)-lo)/max(hi-lo,1),0,1)
    im=Image.fromarray(np.round(gray*255).astype('uint8'));im.thumbnail((side,side),Image.Resampling.LANCZOS)
    s=io.BytesIO();im.save(s,format='JPEG',quality=82)
    return 'data:image/jpeg;base64,'+base64.b64encode(s.getvalue()).decode()

def write_csv(path,rows,fieldnames=None):
    if fieldnames is None: fieldnames=list(rows[0])
    with Path(path).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(rows)

def build_previews(data,c,fixed):
    """Display previews for every field/channel, sized so all of them fit the review budget.
    Computed before inference so an unreviewable batch is refused before any segmentation work."""
    import numpy as np
    ranges={(fid,ch['id']):[float(x) for x in np.percentile(f['planes'][ch['id']],[10,99.9])] for fid,f in data.items() for ch in c['channels']}
    largest=max(max(next(iter(f['planes'].values())).shape) for f in data.values())
    sides=[min(PREVIEW_SIDES[0],largest)]+[s for s in PREVIEW_SIDES if s<min(PREVIEW_SIDES[0],largest)]
    count=len(data)*len(c['channels'])*2;at=0
    while at<len(sides):
        side=sides[at];previews={};total=0;done=0
        for fid,f in data.items():
            pv={'images':{},'fixedImages':{},'displaySettings':{},'previewMaxSide':side}
            for ch in c['channels']:
                cid=ch['id'];a=f['planes'][cid];lo,hi=ranges[(fid,cid)];flo,fhi=fixed[cid]
                pv['images'][cid]=display_image(a,lo,hi,'auto',side);pv['fixedImages'][cid]=display_image(a,flo,fhi,'fixed',side)
                pv['displaySettings'][cid]={'auto':{'lower_raw':lo,'upper_raw':hi},'fixed':{'lower_raw':flo,'upper_raw':fhi}}
                total+=len(pv['images'][cid])+len(pv['fixedImages'][cid]);done+=2
                if total>PREVIEW_BUDGET: break
            if total>PREVIEW_BUDGET: break
            previews[fid]=pv
        if total<=PREVIEW_BUDGET: return side,previews,total
        # Preview bytes scale roughly with area: jump to the largest side that should fit.
        target=side*math.sqrt(PREVIEW_BUDGET/(total*count/max(done,1)))*0.95
        at=next((i for i in range(at+1,len(sides)) if sides[i]<=target),len(sides)-1) if at<len(sides)-1 else len(sides)
    raise ResourceLimitError(f'{len(data)} fields x {len(c["channels"])} channels are too many to review interactively even with '
                             f'{sides[-1]} px previews; select fewer fields or split the input into several runs.')

def field_report_bytes(vf,rows,cols):
    """Bytes one field adds to the rebuilt report (JSON payload HTML-escaped into the sandboxed srcdoc), excluding previews."""
    from render_review import packed
    text=io.StringIO();csv.DictWriter(text,fieldnames=cols).writerows(rows)
    payload=packed({k:v for k,v in vf.items() if k not in ('images','fixedImages')})+packed(list(csv.reader(io.StringIO(text.getvalue()))))
    return len(html.escape(payload,quote=True).encode('utf-8'))

def summarize_field(fid,seg,objects,rows,c,exposures,bgm,bgs):
    import numpy as np
    out=[]
    for ch in c['channels']:
        if not ch.get('measure'): continue
        for region in ['whole','edge','interior']:
            rr=[r for r in rows if r['measurement_channel']==ch['id'] and r['region']==region and r['area_pixels']]
            values=[r['corrected_mean'] for r in rr if r['corrected_mean'] is not None]
            sat=[r['saturated_pixels'] for r in rr]
            out.append(dict(field=fid,segmentation_channel=seg,measurement_channel=ch['id'],region=region,
                candidates=len(objects),available_rois=len(rr),corrected_rois=len(values),median_corrected=float(np.median(values)) if values else None,
                negative_corrected_rois=sum(v<0 for v in values),rois_with_saturation=sum(s>0 for s in sat if s is not None) if all(s is not None for s in sat) else None,
                exposure_seconds=exposures[ch['id']],background_fraction=bgm['fraction'],background_estimator=bgm['estimator'],background_value=bgs[ch['id']]))
    return out

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
    write_field_index(out,saved_config)
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
        cols=['field','segmentation_channel','object_id','region','measurement_channel','area_pixels','raw_mean','background_median','background_mean','background_estimator','background_value','corrected_mean','raw_sum','corrected_sum','saturated_pixels','saturation_limit','touches_image_edge','background_valid','expert_validated','exposure_seconds']
        fixed={ch['id']:(min(float(np.percentile(f['planes'][ch['id']],10)) for f in data.values()),max(float(np.percentile(f['planes'][ch['id']],99.9)) for f in data.values())) for ch in c['channels']}
        preview_side,previews,preview_bytes=build_previews(data,c,fixed)
        manifest['review_budget']=dict(report_limit_bytes=REVIEW_REPORT_LIMIT,preview_max_side=preview_side,preview_bytes=preview_bytes);dump(out/'run_manifest.json',manifest)
        report_bytes=preview_bytes+REVIEW_REPORT_MARGIN
        # Cellpose imports matplotlib only to draw figures, which LabCellpose never does. On macOS a first import scans the
        # system fonts with system_profiler (about 10 s per new cache); without matplotlib Cellpose turns plotting off.
        sys.modules.setdefault('matplotlib',None)
        import torch
        from cellpose import models
        device=args.device
        if device=='auto': device='cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        torch.set_num_threads(6);torch.manual_seed(24);np.random.seed(24)
        manifest['device']=device;manifest['threads']=6;dump(out/'run_manifest.json',manifest)
        model=models.CellposeModel(gpu=device!='cpu',device=torch.device(device),pretrained_model=str(weights),use_bfloat16=False)
        total=len(data)*len(c['segmentation_channels']);done=0;labels={f['id']:image_names(f)[0] for f in c['fields']}
        print(json.dumps({'event':'model_ready','device':device,'total':total}),flush=True)
        viewer={};all_rows=[];field_rows=[];validation={'fields':{},'objects':0,'measurement_rows':0,'max_sampled_raw_mean_error':0.0}
        changed_exposure={ch['id']:sorted({f['exposures'][ch['id']] for f in data.values() if f['exposures'][ch['id']] is not None}) for ch in c['channels']}
        for number,(fid,f) in enumerate(data.items(),1):
            planes=f['planes'];shape=next(iter(planes.values())).shape;masks={};pending_count=0
            for cid in c['segmentation_channels']:
                torch.manual_seed(24);np.random.seed(24);t=time.time()
                lab=np.asarray(model.eval(planes[cid],**c['parameters'])[0])
                if lab.shape!=shape or not np.issubdtype(lab.dtype,np.integer) or lab.min()<0: raise ValueError('Invalid Cellpose label map')
                lab=lab.astype('uint32');masks[cid]=lab
                object_count=int(np.count_nonzero(np.unique(lab)))
                pending_count+=object_count
                if validation['objects']+pending_count > MAX_OBJECTS or (validation['objects']+pending_count)*3*sum(bool(ch.get('measure')) for ch in c['channels']) > MAX_MEASUREMENT_ROWS:
                    raise ResourceLimitError('Run exceeds 50,000 objects or 500,000 measurement rows; select fewer fields or segmentation inputs.')
                dst=out/'masks'/f'{fid}_{cid}.tif';tifffile.imwrite(dst,lab,photometric='minisblack')
                record=dict(field=fid,channel=cid,objects=object_count,seconds=time.time()-t,sha256=file_sha(dst))
                manifest['masks'].append(record);dump(out/'run_manifest.json',manifest);done+=1
                print(json.dumps({'event':'progress','done':done,'total':total,'field':fid,'image':labels.get(fid,fid),'channel':cid,'objects':object_count,'seconds':round(record['seconds'],2)}),flush=True)
            bg,bgs,bgm=make_background(planes,masks,c);tifffile.imwrite(out/'background_masks'/f'{fid}.tif',bg.astype('uint8'),photometric='minisblack')
            vf=dict(shape=list(shape),**previews[fid],objects={},background=bgm,
                backgroundPath=contours(bg),exposures=f['exposures'],pixelSizeUm=f['pixel_size_um'],warnings=[])
            if not bgm['valid']: vf['warnings'].append('Insufficient background pixels; corrected values unavailable.')
            for ch in c['channels']:
                if ch.get('measure') and len(changed_exposure[ch['id']])>1: vf['warnings'].append(f'{ch["label"]}: exposure differs between fields; raw intensity is not normalized.')
            fieldcheck={};field_measurements=[]
            for cid,lab in masks.items():
                obs,rows=measure_field(fid,planes,lab,cid,bgs,bgm['valid'],c,f['limits'],bgm);vf['objects'][cid]=obs
                for row in rows: row['exposure_seconds']=f['exposures'][row['measurement_channel']]
                all_rows.extend(rows);field_measurements.extend(rows);validation['objects']+=len(obs)
                # Independent raw-pixel check from saved native labels for several objects per field/input.
                saved=tifffile.imread(out/'masks'/f'{fid}_{cid}.tif')
                for o in obs[:3]:
                    for ch in c['channels']:
                        if ch.get('measure'):
                            err=abs(float(planes[ch['id']][saved==o['id']].mean())-o['regions']['whole']['channels'][ch['id']]['mean'])
                            validation['max_sampled_raw_mean_error']=max(validation['max_sampled_raw_mean_error'],err)
                            if err>1e-9: raise AssertionError('Raw measurement check failed')
                field_rows.extend(summarize_field(fid,cid,obs,rows,c,f['exposures'],bgm,bgs))
                fieldcheck[cid]={'candidates':len(obs),'region_partition_verified':True}
            report_bytes+=field_report_bytes(vf,field_measurements,cols)
            if report_bytes>REVIEW_REPORT_LIMIT:
                raise ResourceLimitError(f'The interactive review for this run would exceed {REVIEW_REPORT_LIMIT>>20} MiB after {number} of {len(data)} fields. '
                    'Masks for the completed fields are kept in this folder. Split the analysis into smaller runs (fewer fields or segmentation inputs).')
            viewer[fid]=vf;validation['fields'][fid]=fieldcheck
        print(json.dumps({'event':'progress','done':total,'total':total,'stage':'writing'}),flush=True)
        write_csv(out/'measurements.csv',all_rows,cols);write_csv(out/'field_summary.csv',field_rows)
        expected_rows=validation['objects']*3*sum(bool(ch.get('measure')) for ch in c['channels'])
        assert len(all_rows)==expected_rows
        validation.update(measurement_rows=len(all_rows),expected_rows=expected_rows,passed=True,
            exposure_changes={k:v for k,v in changed_exposure.items() if len(v)>1},expert_ground_truth=False)
        dump(out/'viewer_data.json',{'config':c,'fields':viewer})
        build_viewer(c,viewer,out,{'version':VERSION,'device':device,'exposureChanges':validation['exposure_changes']})
        report_size=(out/'index.html').stat().st_size
        if report_size>REVIEW_REPORT_LIMIT:
            raise ResourceLimitError(f'The interactive review ({report_size/2**20:.0f} MiB) exceeds the {REVIEW_REPORT_LIMIT>>20} MiB viewer limit; split the analysis into smaller runs.')
        validation['review_report_bytes']=report_size
        dump(out/'validation.json',validation)
        manifest.update(status='complete',seconds=time.time()-started,validation=validation,
            outputs_sha256={n:file_sha(out/n) for n in ['index.html','measurements.csv','field_summary.csv','fields.csv','viewer_data.json','validation.json']})
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
