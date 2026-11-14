import os,sys,json,shutil,subprocess
from pathlib import Path
from scripts.run_validation import execute
R=Path.cwd();B=R/'benchmarks/results/latency-remediation-2026-11-14';P=R/'.local-controller/latency-remediation-2026-11-14'
os.environ['UV_OFFLINE']='1'
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(R/'.local-controller/browsers')
def run(stem,artifact,command,summary=False):
 print('START',stem,flush=True)
 receipt=execute(R,B/'source/validation'/('current-'+stem),B/artifact,command,summary=summary)
 print('END',stem,receipt['exit_code'],flush=True)
 if receipt['exit_code']:raise SystemExit(receipt['exit_code'])
py=str(R/'.venv/bin/python');cli=str(R/'.venv/bin/sentinel')
run('guarded','current-guarded.json',['make','branch-contract'],True)
run('ui-build','current-ui-build.json',['pnpm','--dir','ui','build'],True)
script="import subprocess,shutil;from pathlib import Path;subprocess.run(['pnpm','--dir','ui','test:e2e'],check=True);a=Path('.local-controller/ui-validation');b=Path('benchmarks/results/latency-remediation-2026-11-14');[(shutil.copyfile(a/x,b/y)) for x,y in [('results.json','current-browser.json'),('timeline-performance.json','current-timeline-3k.json'),('timeline-performance-50000.json','current-timeline-50k.json')]]"
run('browser','current-browser.json',[py,'-c',script])
run('demo','current-demo/demo-report.json',[cli,'demo','--destination',str(B/'current-demo')])
run('corpus','current-corpus/results.json',[cli,'security-corpus',str(B/'current-corpus')])
run('search','current-search/progress.json',[cli,'policy-search',str(B/'current-search')])
run('search-resume','current-search-resume.json',[py,'-c',"import subprocess,shutil;from pathlib import Path;p=Path('benchmarks/results/latency-remediation-2026-11-14/current-search/progress.json');before=p.read_bytes();subprocess.run(['.venv/bin/sentinel','policy-search',str(p.parent),'--resume'],check=True);assert before==p.read_bytes();shutil.copyfile(p,'benchmarks/results/latency-remediation-2026-11-14/current-search-resume.json')"])
with (P/'api-image-build.log').open('wb') as out:
 subprocess.run(['docker','build','--platform','linux/amd64','--tag','sentinel-replay-api:validation-20261113','.'],stdout=out,stderr=subprocess.STDOUT,check=True)
script="import subprocess,shutil;subprocess.run(['.venv/bin/python','scripts/validate_branch_api.py','--capsule','benchmarks/results/latency-remediation-2026-11-14/current-demo/investigation.sentinel','--output','.local-controller/latency-remediation-2026-11-14/postgres'],check=True);shutil.copyfile('.local-controller/latency-remediation-2026-11-14/postgres/receipt.json','benchmarks/results/latency-remediation-2026-11-14/current-postgres.json')"
run('postgres','current-postgres.json',[py,'-c',script])
script="import subprocess,shutil;subprocess.run(['.venv/bin/python','scripts/validate_deployment.py','--capsule','benchmarks/results/latency-remediation-2026-11-14/current-demo/investigation.sentinel','--scale-capsule','benchmarks/results/latency-remediation-2026-11-14/current-scale/50000/scale.sentinel','--browser-proof','--output','.local-controller/latency-remediation-2026-11-14/deployment'],check=True);shutil.copyfile('.local-controller/latency-remediation-2026-11-14/deployment/receipt.json','benchmarks/results/latency-remediation-2026-11-14/current-deployment.json')"
run('deployment','current-deployment.json',[py,'-c',script])
print('VALIDATION COMPLETE',flush=True)
