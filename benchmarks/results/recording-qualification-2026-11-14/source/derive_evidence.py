"""Derive summaries only from completed, current-source validation receipts."""
import json,sys,shutil,subprocess,re
from pathlib import Path
from sentinel_replay.canonical import event_digest
from sentinel_replay.release_audit import source_inventory
from sentinel_replay.evidence_store import blob_digest
from sentinel_replay.capsule import verify_capsule
R=Path.cwd();B=R/"benchmarks/results/recording-qualification-2026-11-14"
def load(p):return json.loads(p.read_text())
def ref(p):return {"path":str(p.relative_to(R)),"digest":blob_digest(p.read_bytes())}
def current(stem,artifact):
 receipt=load(B/"source/validation"/("current-"+stem)/"receipt.json")
 source=event_digest(source_inventory(R))
 assert receipt["exit_code"]==0
 assert receipt["source_root_before"]==receipt["source_root_after"]==source
 assert receipt["artifact"]==ref(artifact)
 return receipt
D=load(B/"current-deployment.json")
assert D["completed"] and all(D["cleanup"].values())
current("deployment",B/"current-deployment.json")
if sys.argv[1]=="operational":
 current("browser",B/"current-browser.json")
 browser=load(B/"current-browser.json");assert browser["stats"]["expected"]==6 and not browser["stats"]["unexpected"]
 checks=D["checks"]
 resources=[checks["bounded_API_cgroup"],checks["bounded_API_cgroup_before_crash"]]
 bounded=all(v["memory.max"]=="1073741824" and v["pids.max"]=="128" and
  int(v["memory.peak"])<1073741824 and int(v["pids.current"])<=128 and
  "oom_kill 0" in v["memory.events"].splitlines() for v in resources)
 recovered=(checks["abrupt_running_job_recovery"]["state"]=="interrupted" and
  checks["interrupted_job_survives_backup_restore"] and
  all(checks[name]["three_adapter_replay"] for name in ["original","restarted","restored"]))
 assert bounded and recovered and checks["operator_witness_readonly"]
 assert checks["missing_operator_witness_quarantines_replay"]
 timing3=load(B/"current-timeline-3k.json");timing50=load(B/"current-timeline-50k.json")
 assert timing3["timeline_interactive_after_data"]["n"]==25
 assert timing50["timeline_interactive_after_data"]["n"]==25
 assert timing50["timeline_interactive_after_data"]["boundaries"]==50000
 report={"schema_version":1,"completed":True,"failure_recovery_verified":bool(recovered),
  "bounded_resources_verified":bounded,"declared_capacity":1,
  "scope":"One local operator; two admitted heavy requests and one worker;1GiB/128pids.32-request surge may return429. This is not a successful-throughput SLO or remote/multi-tenant qualification.",
  "timeline_interactive_after_data":timing3["timeline_interactive_after_data"],
  "timeline_50k_after_data":timing50["timeline_interactive_after_data"],
  "cold_first_navigation_to_data_seconds":{"3186":timing3["cold_first_navigation_to_data_seconds"],"50000":timing50["cold_first_navigation_to_data_seconds"]},
  "source_inputs":[ref(B/name) for name in ["current-deployment.json","current-browser.json","current-timeline-3k.json","current-timeline-50k.json"]],
  "limits_observed":resources,"HTTP_50k_probe":checks["HTTP_50k_scale"]}
 target=B/"current-operational.json"
elif sys.argv[1]=="proof":
 private=R/".local-controller/recording-adoption-2026-11-14/deployment/browser-proof"
 capture=load(private/"capture.json");capsule=verify_capsule(B/"current-demo/investigation.sentinel")
 assert capture["continuous_capture"] and not capture["errors"] and capture["run_id"]==capsule.run_id
 video=R/"docs/assets/sentinel-replay-proof-v3.webm"
 shutil.copyfile(private/"sentinel-replay-proof.webm",video)
 shutil.copyfile(private/"provenance-desktop.png",R/"docs/assets/investigation-v3.png")
 shutil.copyfile(private/"capture.json",B/"current-capture.json")
 result=subprocess.run([str(R/".local-controller/browsers/ffmpeg-1013/ffmpeg-mac"),"-i",str(video)],capture_output=True,text=True)
 match=re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)",result.stderr);assert match
 duration=int(match[1])*3600+int(match[2])*60+float(match[3]);assert 74<=duration<=77
 report={"schema_version":1,"continuous_capture":True,"duration_seconds":duration,
  "journal_root":capsule.root,"video":ref(video),
  "capture_source_digest":blob_digest((R/"ui/scripts/record-proof.mjs").read_bytes()),
  "source_inputs":[ref(B/"current-capture.json"),ref(B/"current-deployment.json")],
  "measurement":"Actual uninterrupted local Compose UI, declared synthetic finite pack; duration inspected with bundled FFmpeg. No edited or generated outcomes."}
 target=B/"current-proof.json"
else:raise ValueError("choose operational or proof")
with target.open("x") as stream:stream.write(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(target.name)
