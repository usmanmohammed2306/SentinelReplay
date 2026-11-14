"""Assemble retained evidence; never supply missing reviews or waive a budget."""
import json,re
from pathlib import Path
from sentinel_replay.release_audit import audit_release,source_inventory
from sentinel_replay.canonical import event_digest
from sentinel_replay.evidence_store import blob_digest
R=Path.cwd()
B=R/"benchmarks/results/recording-qualification-2026-11-14"
def ref(path):
 p=R/path if not Path(path).is_absolute() else Path(path)
 return {"path":str(p.relative_to(R)),"digest":blob_digest(p.read_bytes())}
def write(path,value):
 Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
names={"local_tests":"current-local.json","guarded_tests":"current-guarded.json",
 "ui_build":"current-ui-build.json","browser_tests":"current-browser.json",
 "product_demo":"current-demo/demo-report.json","corpus":"current-corpus/results.json",
 "policy_search":"current-search-revalidation.json","scale":"scale-with-docker-access/results.json",
 "recording_overhead":"current-overhead/results.json","deployment_recovery":"current-deployment.json",
 "postgres_http":"current-postgres.json","proof_video":"current-proof.json",
 "operational_validation":"current-operational.json","provenance_validation":"provenance-pending.json"}
manifest={"schema_version":2,"source_files":source_inventory(R),
 "source_commit":"939de2a168b83f222567df5ce94cb98885a6f0f3",
 "artifacts":{name:ref(B/path) for name,path in names.items()},"execution_receipts":{},"reviews":{},"traceability":[]}
source_root=event_digest(manifest["source_files"])
for name in names:
 if name=="provenance_validation":continue
 stem={"local_tests":"local","guarded_tests":"guarded","ui_build":"ui-build",
  "browser_tests":"browser","product_demo":"demo","policy_search":"search",
  "scale":"scale-with-docker-access","recording_overhead":"overhead","deployment_recovery":"deployment",
  "postgres_http":"postgres","proof_video":"proof","operational_validation":"operational"}.get(name,name)
 manifest["execution_receipts"][name]=ref(B/"source/validation"/(stem if name=="scale" else "current-"+stem)/"receipt.json")
for name,reviewer,evidence in [
 ("hosted_ci","GitHub Actions (automated; not human peer review)",[B/"hosted-ci-complete.json"]),
 ("clean_room_reproduction","Fresh Ubuntu CI checkout and empty volumes (automated transcript)",[B/"hosted-ci-complete.json"]),
 ("license_and_distribution","Explicit owner MIT/public-main authorization; mechanical verification",
  [R/"LICENSE",B/"public-mit-complete.json",B/"publication-scan.json",R/"benchmarks/evidence-archives/THIRD_PARTY_NOTICES.md"])]:
 path=B/(name+"-review.json")
 write(path,{"source_root":source_root,"decision":"accepted","reviewer":reviewer,
  "evidence":[ref(p) for p in evidence],"scope":"Only the named mechanically verified gate; no independent human adjudication, mastery or general production guarantee."})
 manifest["reviews"][name]=ref(path)
# Each row links actual source/tests/results; failing measurements stay unverified.
rows={
1:(["README.md"],["product_demo"]),
2:(["docs/FROZEN_PRODUCT_CHARTER.md"],["product_demo","local_tests","guarded_tests"]),
3:([names["product_demo"]],["product_demo"]),
4:(["src/sentinel_replay/boundary.py","tests/test_evidence.py"],["local_tests"]),
5:(["docs/ENVIRONMENT_PACK_CONTRACT.md","tests/test_agent_coverage.py"],["local_tests","product_demo"]),
6:(["src/sentinel_replay/telemetry.py","tests/test_telemetry.py"],["local_tests"]),
7:(["src/sentinel_replay/checkpoint_set.py","tests/test_git_snapshot.py","tests/test_sqlite_snapshot.py"],["local_tests","deployment_recovery"]),
8:(["src/sentinel_replay/progress_anchor.py","tests/test_capsule_witness.py"],["local_tests","deployment_recovery"]),
9:([names["corpus"],"src/sentinel_replay/incident_rules.py"],["corpus"]),
10:(["src/sentinel_replay/timeline.py",names["scale"]],["scale","timeline_first_page_3k","timeline_interactive_3k"]),
11:(["src/sentinel_replay/provenance_eval.py",names["provenance_validation"]],["provenance_and_blast_radius"]),
12:(["src/sentinel_replay/provenance.py",names["provenance_validation"]],["provenance_and_blast_radius"]),
13:(["src/sentinel_replay/environment_pack.py","tests/test_replay_profiles.py"],["product_demo","deployment_recovery","local_tests"]),
14:(["src/sentinel_replay/divergence.py","tests/test_divergence.py"],["local_tests"]),
15:(["src/sentinel_replay/bisection.py",names["recording_overhead"]],["local_tests","product_demo","recording_overhead"]),
16:(["src/sentinel_replay/policy.py","tests/test_opa_contract.py"],["guarded_tests"]),
17:(["src/sentinel_replay/policy_language.py","tests/test_policy_language.py"],["guarded_tests"]),
18:(["src/sentinel_replay/futures.py","tests/test_futures.py"],["product_demo","local_tests"]),
19:(["src/sentinel_replay/policy_search.py",names["policy_search"]],["policy_search"]),
20:(["ui/src/components/policy-chart.tsx",names["policy_search"]],["policy_search","browser_tests"]),
21:([names["corpus"]],["corpus"]),
22:(["src/sentinel_replay/pack_comparison.py"],["product_demo","browser_tests"]),
23:(["src/sentinel_replay/capsule.py","tests/test_capsule.py"],["product_demo","local_tests"]),
24:(["src/sentinel_replay/signed_capsule.py","tests/test_signed_capsule.py"],["deployment_recovery","local_tests"]),
25:(["src/sentinel_replay/database.py","tests/test_migration.py"],["postgres_http"]),
26:(["src/sentinel_replay/contracts.py","src/sentinel_replay/database.py"],["local_tests","postgres_http"]),
27:(["src/sentinel_replay/api.py","tests/test_investigation_api.py"],["deployment_recovery","browser_tests","local_tests"]),
28:(["src/sentinel_replay/product_cli.py","tests/test_product_cli.py"],["product_demo","local_tests"]),
29:(["ui/src/app/page.tsx","ui/tests/investigation.spec.ts"],["browser_tests","ui_build"]),
30:(["ui/src/app/page.tsx"],["browser_tests"]),
31:(["README.md","ui/src/app/page.tsx"],["browser_tests"]),
32:([names["corpus"]],["corpus"]),
33:([names["scale"],names["recording_overhead"],names["provenance_validation"]],["recording_latency_3k","recording_added_time_per_boundary","provenance_and_blast_radius","journal_verification_50k"]),
34:([names["local_tests"],names["guarded_tests"],names["browser_tests"]],["local_tests","guarded_tests","browser_tests","provenance_and_blast_radius","recording_latency_3k","recording_added_time_per_boundary"]),
35:(["pyproject.toml","uv.lock","ui/pnpm-lock.yaml"],["ui_build","deployment_recovery"]),
36:(["README.md","docs/ENVIRONMENT_PACK_CONTRACT.md"],["product_demo"]),
37:(["docs/FROZEN_PRODUCT_CHARTER.md","docs/THREAT_MODEL.md"],["local_tests"]),
38:(["README.md",names["proof_video"]],["proof_video"]),
39:(["README.md","docs/FROZEN_PRODUCT_CHARTER.md"],["local_tests"]),
40:(["README.md","docs/PERFORMANCE_EVIDENCE.md"],["scale","product_demo"]),
41:(["docs/STATUS.md","docs/SCOPE_TRACEABILITY.md"],["local_tests"]),
42:([names["product_demo"],"src/sentinel_replay/release_quality.py"],["product_demo","recording_latency_3k","recording_added_time_per_boundary","provenance_and_blast_radius"]),
43:([names["proof_video"],"docs/assets/sentinel-replay-proof-v3.webm"],["proof_video"])}
titles={}
for line in (R/"docs/SCOPE_TRACEABILITY.md").read_text().splitlines():
 m=re.match(r"\| (\d+)\. ([^|]+)\|",line)
 if m:titles[int(m[1])]=m[2].strip()
assert len(rows)==len(titles)==43
path=R/"benchmarks/results/current-release-manifest.json"
write(path,manifest)
first=audit_release(R,path)
checks={**first["engineering_checks"],**first["quality_budgets"]}
for identifier,(files,required) in rows.items():
 evidence=[]
 for file in files:
  candidate=R/file
  if not candidate.exists():candidate=B/file
  evidence.append(ref(candidate))
 verified=all(checks[name]["passed"] for name in required) and identifier!=41
 manifest["traceability"].append({"section":identifier,"title":titles[identifier],
  "state":"verified" if verified else "implemented", "checks":required,"evidence":evidence})
write(path,manifest)
write(B/"manifest.json",manifest)
result=audit_release(R,path)
write(B/"release-report.json",result)
print(json.dumps({"status":result["status"],"source_mismatches":result["source_mismatches"],
 "artifacts_passed":sum(r["passed"] for r in result["engineering_checks"].values()),
 "artifacts_total":len(result["engineering_checks"]),"quality":result["quality_budgets"],
 "scope_rows":len(result["scope_traceability"]),"scope_verified":sum(r["passed"] for r in result["scope_traceability"].values())},indent=2))
