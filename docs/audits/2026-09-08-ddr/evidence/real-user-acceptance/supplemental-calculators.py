import json,sys,inspect,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from core.engineering.bridge import CalculatorBridge as B
from core.engineering.engines.well_control import WellControlEngine as W
from core.engineering.engines.cement import CementEngine as C
from core.engineering.engines.mud_volume import MudVolumeEngine as M
from core.engineering.engines.bit_performance import BitPerformanceEngine as P
from core.engineering.engines.fishing import FishingEngine as F
from core.engineering.engines.torque_drag import TorqueDragEngine as T
from core.engineering.engines.trajectory import TrajectoryCalculator as D
from core.engineering.engines.anti_collision import AntiCollisionEngine as A
survey=[{'md':0,'inc':0,'azi':90},{'md':100,'inc':10,'azi':90}]
run={'bit_size':8.5,'depth_in':1000,'depth_out':1200,'hours_on_bottom':10,'wob_max':20,'rpm_max':100,'torque_max':5}
cases=[(W.kill_mw,dict(original_mw_ppg=10,sidpp_psi=520,tvd_ft=5000)),
(W.maasp,dict(max_allowable_mw_ppg=14,current_mw_ppg=10,shoe_tvd_ft=3000)),
(W.formation_pressure,dict(mw_ppg=10,tvd_ft=5000,sidpp_psi=520)),
(B.kick_volume,dict(pit_gain_bbl=10,annular_capacity_bbl_ft=.05)),
(B.trip_margin,dict(mw_ppg=11,formation_emw_ppg=10,tvd_ft=5000,swab_pressure_psi=100)),
(C.displacement,dict(casing_id_in=6.276,casing_length_ft=5000,shoe_track_ft=80)),
(C.toc_from_volume,dict(hole_size_in=8.5,casing_od_in=7,slurry_bbl=100,excess_pct=10,shoe_md_ft=5000)),
(M.dilution,dict(current_mw=12,target_mw=10,system_vol=1000,dilutant_mw=8.33)),
(M.mix,dict(mw1=10,vol1=100,mw2=12,vol2=100)),
(P.from_daily_params,dict(params=run)),(P.rollup,dict(runs=[run,run])),
(F.adjusted_weight,dict(od_in=5,id_in=4.276)),
(F.free_point,dict(stretch_in=12,pipe_weight_ppf=19.5,pull_lbf=100000)),
(F.string_stretch,dict(length_ft=10000,mw_ppg=10)),
(F.jar_operating_range,dict(string_weight_lbs=200000,buoyancy_factor=.85,overpull_lbs=50000)),
(F.overshot_fit,dict(fish_od_in=5,overshot_id_in=5.25)),
(T.component_air_weight,dict(length_m=30,weight_ppf=19.5)),
(T.calculate_weight_card,dict(components=[{'length':30,'weight':19.5}],mud_density_pcf=71,inclination_deg=20,top_drive_weight_klbf=10,friction_factor=.2)),
(T.casing_landing_load,dict(casing_weight_ppf=29,length_ft=5000,buoyancy_factor=.85,friction_factor=.2)),
(D.calculate,dict(surveys=survey)),
(A.calculate_clearance,dict(reference=[{'north':0,'east':0,'tvd':100}],offset=[{'north':10,'east':0,'tvd':100}])),
(B.min_curvature_pair,dict(md1=0,inc1=0,azi1=90,md2=100,inc2=10,azi2=90)),
(B.mse,dict(wob_lbf=20000,torque_ft_lbf=5000,rpm=100,rop_ft_hr=30,bit_diameter_in=8.5)),
(B.mud_balance,dict(active_volume_bbl=1000,additions_bbl=10,losses_bbl=5)),
(B.cement_volumes,dict(hole_size_in=8.5,casing_od_in=7,open_hole_length_ft=5000,excess_pct=10))]
results=[]
for fn,inputs in cases:
 for state in ('valid','missing'):
  args=inputs if state=='valid' else {k:([] if isinstance(v,list) else {} if isinstance(v,dict) else None) for k,v in inputs.items()}
  try:
   result=fn(**args)
   value=result.as_dict() if hasattr(result,'as_dict') else result
   results.append({'calculator':fn.__qualname__,'state':state,'inputs':args,'result':value})
  except Exception as exc:
   results.append({'calculator':fn.__qualname__,'state':state,'inputs':args,'exception':type(exc).__name__,'message':str(exc)})
assert W.kill_mw(10,520,5000).value==12
assert M.mix(10,100,12,100).value==11
assert B.kick_volume(pit_gain_bbl=10,annular_capacity_bbl_ft=.05).values['kick_height_ft']==200
assert B.kick_volume(pit_gain_bbl=0).values['is_kick'] is False
assert not B.kick_volume(pit_gain_bbl=-1).success
assert math.isclose(B.min_curvature_pair(0,0,90,100,10,90).values['closure_azimuth_deg'],90)
Path('build/acceptance/supplemental-calculators.json').write_text(json.dumps(results,indent=2,default=str))
print('Supplemental cases:',len(results))
for r in results:
 if r['state']=='valid' and ('exception'in r or isinstance(r['result'],dict) and r['result'].get('success') is False):print('VALID CASE NEEDS INVESTIGATION',r)
for r in results:
 if 'exception' in r:print('Exception contract',r['calculator'],r['state'],r['exception'],r['message'])
