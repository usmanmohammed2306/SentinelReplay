import json,tarfile,hashlib
from pathlib import Path
from sentinel_replay.release_audit import source_inventory
from sentinel_replay.canonical import event_digest
R=Path.cwd();B=R/'benchmarks/results/recording-qualification-2026-11-14';A=R/'benchmarks/evidence-archives'
archives=[]
for name,folder in [('demo','current-demo'),('scale','scale-with-docker-access'),('corpus','current-corpus'),('overhead','current-overhead'),('pre-adoption','pre-adoption-repeat'),('scale-permission-failure','current-scale')]:
 src=B/folder;dst=A/f'sentinel-recording-{name}-2026-11-14.tar.gz'
 assert not dst.exists()
 included=[];omitted=[]
 with tarfile.open(dst,'w:gz',compresslevel=6) as tf:
  for p in sorted(src.rglob('*')):
   rel=p.relative_to(R/'benchmarks/results')
   if p.is_symlink():raise ValueError(f'symlink forbidden: {rel}')
   if not p.is_file():continue
   if p.name.endswith('.key') or p.name.startswith('.env') or '__pycache__' in p.parts or '.git/hooks/' in p.as_posix():
    omitted.append(str(rel));continue
   info=tf.gettarinfo(str(p),arcname=str(rel))
   assert info.isfile()
   info.uid=info.gid=0;info.uname=info.gname='';info.pax_headers={}
   with p.open('rb') as stream:tf.addfile(info,stream)
   included.append({'path':str(rel),'bytes':p.stat().st_size})
 digest='sha256:'+hashlib.sha256(dst.read_bytes()).hexdigest()
 assert dst.stat().st_size<50*1024*1024
 archives.append({'path':str(dst.relative_to(R)),'digest':digest,'archive_bytes':dst.stat().st_size,'files':len(included),'members':included,'omitted_paths':omitted})
 print(name,len(included),dst.stat().st_size,flush=True)
manifest={'schema_version':1,'source_commit':'939de2a168b83f222567df5ce94cb98885a6f0f3','source_root':event_digest(source_inventory(R)),'scope':'Selected raw synthetic measurement folders; pre-adoption data belongs to its own historical69-module source snapshot, not the post-adoption inventory. Source bindings inside each report remain authoritative. Original payload bytes retained; private key files, generated Git hooks and caches omitted. Tar owner metadata normalized to uid/gid 0 with empty owner names; archive paths are relative to benchmarks/results. Prior attempts retained separately. No operator credentials or human labels.','archives':archives}
(A/'sentinel-recording-manifest-2026-11-14.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
