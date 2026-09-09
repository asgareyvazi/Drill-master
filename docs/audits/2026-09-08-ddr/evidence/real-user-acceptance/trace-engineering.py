import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import pytest
calls={}; current=''
def profile(frame,event,arg):
 if event != 'call' or '/core/engineering/' not in frame.f_code.co_filename:return
 if frame.f_code.co_name.startswith('_') or frame.f_code.co_name.startswith('<'):return
 key=str(Path(frame.f_code.co_filename).relative_to(Path.cwd()))+':'+frame.f_code.co_qualname
 calls.setdefault(key,set()).add(current)
class Trace:
 @pytest.hookimpl(hookwrapper=True)
 def pytest_runtest_call(self,item):
  global current
  current=item.nodeid
  sys.setprofile(profile)
  try:yield
  finally:sys.setprofile(None)
code=pytest.main(['-p','no:pytest-qt','tests/test_engineering_completion.py','tests/test_engineering_ground_truth.py','tests/test_engineering_integrations.py','tests/test_extended_engineering.py','tests/test_p0_engineering_core.py','--junitxml=build/acceptance/engineering.xml'],plugins=[Trace()])
Path('build/acceptance/engineering-executed.json').write_text(json.dumps({k:sorted(v) for k,v in sorted(calls.items())},indent=2))
raise SystemExit(code)
