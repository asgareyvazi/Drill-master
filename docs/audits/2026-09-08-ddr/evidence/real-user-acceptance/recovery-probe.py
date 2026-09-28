import os, secrets, subprocess, sqlite3, shutil, json, sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from core.database import DatabaseManager, Company
out=Path('build/acceptance/recovery-final');out.mkdir()
os.environ['DRILLMASTER_ENV']='production';os.environ['DRILLMASTER_DATA_DIR']=str(out.resolve());os.environ['DRILLMASTER_DB_PATH']=str((out/'live.db').resolve())
for key in ('DRILLMASTER_ADMIN_PASSWORD','DRILLMASTER_USER_PASSWORD','DRILLMASTER_VIEWER_PASSWORD'):os.environ.pop(key,None)
secret=secrets.token_urlsafe(24);db=DatabaseManager(bootstrap_passwords={'admin':secret});assert db.initialize();db.generic_save(Company,{'name':'Backup marker','code':'BACKUP'});db.close()
target=out/'live.db';before=target.read_bytes();unrelated=out/'unrelated.db';unrelated.write_bytes(b'unrelated QA file')
command=[sys.executable,'reset_database.py']
cancel=subprocess.run(command,input='CANCEL\n',text=True,capture_output=True);assert cancel.returncode==0 and target.read_bytes()==before
refused=subprocess.run(command,input='RESET\n',text=True,capture_output=True);assert refused.returncode==1 and target.read_bytes()==before
backup=out/'backup.db'
src=sqlite3.connect(target);dst=sqlite3.connect(backup)
try:src.backup(dst)
finally:src.close();dst.close()
env=dict(os.environ,DRILLMASTER_ADMIN_PASSWORD=secrets.token_urlsafe(24));new_secret=env['DRILLMASTER_ADMIN_PASSWORD']
reset=subprocess.run(command,input='RESET\n',text=True,capture_output=True,env=env)
for result in (cancel,refused,reset):assert secret not in result.stdout+result.stderr and new_secret not in result.stdout+result.stderr
(out/'cli.txt').write_text('\n'.join(r.stdout+r.stderr for r in (cancel,refused,reset)))
assert reset.returncode==0, reset.stdout
fresh=DatabaseManager();assert fresh.initialize();assert fresh.generic_get_list(Company)==[] and fresh.authenticate_user('admin',new_secret);fresh.close()
recovered=out/'recovered.db';shutil.copy2(backup,recovered);restore=DatabaseManager();restore.db_path=str(recovered.resolve());assert restore.initialize();assert restore.generic_get_list(Company)[0]['name']=='Backup marker';assert restore.authenticate_user('admin',secret);restore.close()
assert unrelated.read_bytes()==b'unrelated QA file'
(out/'evidence.json').write_text(json.dumps({'mode':'production','target':str(target),'cancel_keeps_bytes':True,'missing_bootstrap_keeps_bytes':True,'secure_reset_exit':0,'fresh_login_without_bootstrap':True,'backup_restore_and_login':True,'unrelated_target_unchanged':True,'secrets_not_printed':True},indent=2))
print('Production CLI cancel/preflight/reset/backup restore/target isolation: PASS')
