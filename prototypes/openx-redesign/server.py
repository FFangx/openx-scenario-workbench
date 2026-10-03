"""Loopback-only, read-only workspace adapter for the design review build."""
from pathlib import Path
from dataclasses import asdict
from functools import lru_cache
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / 'src'))
from openx_workbench.asset_store import AssetStore
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore
from openx_workbench.classification import read_classification
from openx_workbench.preview_frames import read_frame
from openx_workbench.presentation import display, asset_display_title
from types import SimpleNamespace

assets = AssetStore()
pdfs = PdfStore(assets)
projects = ProjectStore(assets)

def document(q):
    pid = q.get('project', [''])[0]
    did = q.get('document', [''])[0]
    return next(d for d in pdfs.documents(pid) if d.document_id == did)

def versions():
    return sorted(assets.latest(), key=lambda v: v.created_at, reverse=True)

def version(q):
    key = q.get('asset', [''])[0]
    return next(v for v in versions() if v.asset_id == key)

def workspace(pid=''):
    ps = projects.projects()
    selected = next((p for p in ps if p.project_id == pid), None)
    if selected is None:
        selected = next((p for p in ps if p.name == '11'), ps[0] if ps else None)
    docs = pdfs.documents(selected.project_id) if selected else []
    scenes = {d.document_id: [dict(id=s.scene_id, revision=s.revision,
        title=s.package.title, text=s.package.preferred_text,
        evidence=[asdict(e) for e in s.package.evidence], structure=s.package.structure,
        classification=s.package.classification, parameters=s.package.parameters,
        status=s.package.extraction.get('review_status','pending'),
        anchors=[dict(page=b['page_number'],y=b['bbox'][1]) for b in s.package.extraction.get('source_blocks',[]) if b.get('bbox') and b.get('page_number')])
        for s in pdfs.scenes(d.project_id,d.document_id)] for d in docs}
    vs = []
    for v in versions():
        c = read_classification(assets,v)
        final=c.get('final',{})
        frame=read_frame(assets,v)
        vs.append(dict(id=v.asset_id,version=v.version_number,version_id=v.version_id,
            title=asset_display_title(SimpleNamespace(title=v.title,xosc_name=v.xosc_name,classification=final)),original_title=v.title,source=v.source_name,xosc=v.xosc_name,xodr=v.xodr_name,
            imported=v.created_at,preview=v.compatibility,
            function=final.get('function_type','未知'), road=final.get('label_road_type','未知'),
            classification=c.get('status','pending'),
            frame=f'/api/frame?asset={v.asset_id}' if frame else None,
            frame_meta=frame[1] if frame else None))
    return dict(projects=[asdict(p) for p in ps], project=asdict(selected) if selected else None,
        documents=[asdict(d) for d in docs], scenes=scenes,assets=vs)

@lru_cache(maxsize=1)
def index():
    from openx_workbench.retrieval import OpenXIndex
    return OpenXIndex([assets.load_asset(v) for v in versions()])

@lru_cache(maxsize=48)
def page_image(pid,did,page):
    import pymupdf
    d=next(d for d in pdfs.documents(pid) if d.document_id==did)
    with pymupdf.open(stream=pdfs.pdf_bytes(d),filetype='pdf') as doc:
        if page<1 or page>len(doc): raise ValueError('Page out of range')
        return doc[page-1].get_pixmap(matrix=pymupdf.Matrix(1.7,1.7)).tobytes('png')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT/'dist'),**kwargs)
    def send(self,data,mime='application/json; charset=utf-8',status=200):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        u=urlparse(self.path)
        if not u.path.startswith('/api/'):
            return super().do_GET()
        q=parse_qs(u.query)
        try:
            if u.path=='/api/data':
                return self.send(workspace(q.get('project',[''])[0]))
            if u.path=='/api/page':
                d=document(q)
                return self.send(page_image(d.project_id,d.document_id,int(q['page'][0])),'image/png')
            if u.path=='/api/pdf':
                return self.send(pdfs.pdf_bytes(document(q)),'application/pdf')
            if u.path=='/api/frame':
                f=read_frame(assets,version(q))
                if not f: return self.send({'error':'这个版本尚无缓存画面'},status=404)
                return self.send(f[0],'image/jpeg')
            if u.path=='/api/asset':
                a=assets.load_asset(version(q))
                return self.send(dict(scenario=asdict(a.bundle.scenario),road=asdict(a.bundle.road)))
            if u.path=='/api/retrieve':
                from openx_workbench.scene_package import scene_package_to_query
                d=document(q)
                s=next(s for s in pdfs.scenes(d.project_id,d.document_id) if s.scene_id==q['scene'][0])
                import copy, math
                package=copy.deepcopy(s.package)
                override=json.loads(q.get('overrides',['{}'])[0])
                if override:
                    if not isinstance(override,dict): raise ValueError('Invalid override')
                    if 'text' in override:
                        if not isinstance(override['text'],str) or len(override['text'])>20000: raise ValueError('Invalid text')
                        package.preferred_text=override['text']
                    for k,v in override.get('structure',{}).items():
                        if k in ('road_class','tested_function') and isinstance(v,str) and len(v)<200:
                            package.structure[k]=v
                    for k,v in override.get('params',{}).items():
                        if k not in ('ego_speed_kph','ttc_value'): continue
                        if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or v<0): raise ValueError('Invalid parameter')
                        package.structure.setdefault('params',{})[k]=v
                query=scene_package_to_query(package)
                found=index().search(query.text,query=query,top_k=8)
                by_xosc={v.xosc_name:v.asset_id for v in versions()}
                return self.send([dict(id=by_xosc[r.asset.xosc_name],score=r.score,
                    level=r.confirmation_level,reasons=[display(reason) for reason in r.reasons],
                    differences=[dict(asdict(x),category=display(x.category),requested=display(x.requested),candidate=display(x.candidate)) for x in r.differences]) for r in found])
            return self.send({'error':'Unknown route'},status=404)
        except (ValueError,KeyError,StopIteration) as e:
            return self.send({'error':'所选内容不可用，请重新选择。'},status=400)
        except Exception as e:
            print(type(e).__name__,str(e),flush=True)
            return self.send({'error':'读取失败，请重试。'},status=500)
    def log_message(self,fmt,*args): pass

if __name__=='__main__':
    port=int(sys.argv[1]) if len(sys.argv)>1 else 0
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'OPENX_DESIGN_URL=http://127.0.0.1:{server.server_port}/',flush=True)
    server.serve_forever()
