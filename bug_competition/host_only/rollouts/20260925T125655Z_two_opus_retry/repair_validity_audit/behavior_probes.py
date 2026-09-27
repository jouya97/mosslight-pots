import sys,json,random,itertools,copy
from fractions import Fraction
from mosslight.irrigation_flow import allocate
from mosslight.irrigation import definition,solve,replay,objective
from mosslight.engine import create
from mosslight.field_calibration import estimate
from mosslight import courier
from mosslight.notebook import add_note
rng=random.Random(97021)
counts={}
for case in range(1000):
 nodes=['tank','a','b','c','bed'];pipes=[{'from':a,'to':b,'capacity':rng.randrange(12)} for a in nodes for b in nodes if a!=b and rng.random()<.26]
 outlets={n:rng.randrange(15) for n in rng.sample(nodes[1:],rng.randrange(1,5))};supply=rng.randrange(30)
 cuts=[]
 for bits in itertools.product((0,1),repeat=len(nodes)):
  group={n for n,bit in zip(nodes,bits) if bit}
  cuts.append((0 if 'tank' in group else supply)+sum(p['capacity'] for p in pipes if p['from'] in group and p['to'] not in group)+sum(v for n,v in outlets.items() if n in group))
 result=allocate(pipes,'tank',outlets,supply)
 assert result['total']==min(cuts),(case,result,min(cuts))
 assert sum(result['outlets'].values())==result['total']
 for n in nodes:
  balance=sum(f for p,f in zip(pipes,result['pipes']) if p['to']==n)-sum(f for p,f in zip(pipes,result['pipes']) if p['from']==n)
  assert balance+(result['total'] if n=='tank' else 0)==result['outlets'].get(n,0)
 assert all(0<=f<=p['capacity'] for p,f in zip(pipes,result['pipes']))
counts['I01_random_mincut_and_flow_conservation']=1000
for case in range(25):
 w=create(case+190,4,4)
 for c in w.cells:
  c.species='moss';c.vitality=rng.randrange(25,76);c.age=rng.randrange(0,70);c.moisture=rng.randrange(10,70);c.shade=rng.randrange(35,85)
 problem=definition(w,{'source':'tank','pipes':[{'from':'tank','to':n,'capacity':15} for n in ('left','right')],'outlets':{'left':{'demand':15,'tiles':[[0,0]]},'right':{'demand':15,'tiles':[[3,3]]}}},[{'name':'left','open':['left']},{'name':'right','open':['right']},{'name':'off','open':[]}],3,30,refill=[0,7,0])
 before=copy.deepcopy(problem)
 brute=[replay(problem,s) for s in itertools.product(range(3),repeat=3)]
 best=max((objective(s),s['remaining']) for s in brute)
 result=solve(problem)
 assert (result['score'],result['remaining'])==best,(case,(result['score'],result['remaining']),best)
 assert replay(problem,result['schedule'])['world']==result['world']
 assert before==problem
counts['I02_exhaustive_27_schedules_per_problem']=25
for case in range(200):
 ts=rng.sample(range(-50,51),4);ys=[rng.randrange(101) for _ in ts];at=rng.randrange(-50,51)
 xbar=sum(map(Fraction,ts))/4;ybar=sum(map(Fraction,ys))/4
 slope=sum((x-xbar)*(y-ybar) for x,y in zip(ts,ys))/sum((x-xbar)**2 for x in ts)
 expected=float(max(0,min(100,ybar+slope*(at-xbar))))
 for origin in [0,1750000000,-1750000000]:
  got=estimate([{'timestamp':x+origin,'moisture':y} for x,y in zip(ts,ys)],at+origin)
  assert abs(got-expected)<1e-9
counts['N01_exact_fraction_regression_with_three_origins']=200
# A duplicate timestamp must contribute its average as documented.
duplicate=estimate([{'timestamp':0,'moisture':0},{'timestamp':0,'moisture':40},{'timestamp':1,'moisture':80},{'timestamp':2,'moisture':20}],1)
assert abs(duplicate-40)<1e-10
counts['N01_duplicate_average']=1
# Namespace bug is not among credited repairs, but B did modify this behavior.
w=create(5,4,4);add_note(w,'first');other=copy.deepcopy(w);other.workbench['notes'][0]['text']='independent'
a=courier.from_garden(w,'desk');b=courier.from_garden(other,'field');rows=courier.observations(courier.merge(a,b))
counts['P33_uncredited_default_namespace_result']={'actual_records':len(rows),'expected_records':2,'rows':rows}
print(json.dumps(counts,sort_keys=True))
