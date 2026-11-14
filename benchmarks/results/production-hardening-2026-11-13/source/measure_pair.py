import json,tempfile,time
from pathlib import Path
from sentinel_replay.environment_pack import Pack,PackStep,record_pack
from sentinel_replay.policy_language import Action,Policy
pack=Pack(name='paired-recorder',files={},steps=tuple(PackStep(action=Action(operation='model_call'),value='frozen-stub') for _ in range(3000)))
with tempfile.TemporaryDirectory(prefix='sentinel-pair-') as temporary:
 start=time.perf_counter();report=record_pack(pack,Path(temporary)/'run',Policy(),decisions=['allowed']*3000)
 print(json.dumps({'seconds':time.perf_counter()-start,'records':report['records'],'source_file':__import__('sentinel_replay.environment_pack',fromlist=['x']).__file__}))
