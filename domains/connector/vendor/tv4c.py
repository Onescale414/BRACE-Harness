"""Independent standard-library checker for the written LC4.1 subset; trial only."""
import base64,hashlib,json,re,sys
CONTRACT='tv4a-independent-subset-baseline-2'
def digest(b):return hashlib.sha256(b).hexdigest()
def reject(reason):raise ValueError(reason)
def pairs(items):
 d={}
 for k,v in items:
  if k in d:reject('duplicate-key')
  d[k]=v
 return d
def integer(s):
 if not re.fullmatch(r'(?:0|[1-9][0-9]{0,4})',s):reject('noncanonical-number')
 return int(s)
def parse(raw):
 if not 0<len(raw)<=8192:reject('input-size')
 text=raw.decode('utf-8')
 if text.startswith('\ufeff'):reject('bom')
 # An escaped object key is not in this profile. Values may contain escapes.
 for match in re.finditer(r'"(?:[^"\\]|\\.)*"',text):
  if text[match.end():].lstrip().startswith(':') and '\\' in match.group(0):reject('escaped-key')
 obj=json.loads(text,object_pairs_hook=pairs,parse_int=integer,parse_float=lambda _:reject('noncanonical-number'),parse_constant=lambda _:reject('non-json-number'))
 count=0
 def bound(x,depth=0):
  nonlocal count
  count+=1
  if depth>8 or count>256:reject('complexity')
  for child in x.values() if isinstance(x,dict) else x if isinstance(x,list) else []:bound(child,depth+1)
 bound(obj);return obj
def shape(x,keys):
 if type(x)!=dict or set(x)!=set(keys.split()):reject('shape')
def literal_path(path):
 if type(path)!=str or not path.startswith('/') or not path.isascii() or len(path)>128:return False
 if path=='/':return True
 parts=path[1:].split('/')
 alphabet=set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
 return 1<=len(parts)<=8 and all(1<=len(p)<=32 and set(p)<=alphabet for p in parts)

def expected(s):
 shape(s,'text source')
 if type(s['text'])!=str or s['text'].strip(' ').lower()!='translate this mapping.':reject('request-text')
 a=s['source'];shape(a,'httpRequest httpResponse');q=a['httpRequest'];r=a['httpResponse'];shape(q,'method path');shape(r,'statusCode body headers delay')
 if q['method']!='GET' or type(q['path'])!=str or not literal_path(q['path']):reject('request-domain')
 if type(r['statusCode'])!=int or r['statusCode']!=200:reject('status-domain')
 if type(r['body'])!=str or len(r['body'])>128 or any(ord(c)<32 or ord(c)>126 for c in r['body']):reject('body-domain')
 if r['headers']!={'Content-Type':['text/plain; charset=utf-8']}:reject('headers-domain')
 d=r['delay'];shape(d,'timeUnit value');u=d['timeUnit'];v=d['value']
 if type(v)!=int or u not in ('SECONDS','MILLISECONDS') or not 0<=v<=(60 if u=='SECONDS' else 60000):reject('delay-domain')
 return {'request':{'method':'GET','urlPath':q['path']},'response':{'status':200,'body':r['body'],'headers':{'Content-Type':'text/plain; charset=utf-8'},'fixedDelayMilliseconds':v*1000 if u=='SECONDS' else v}}
MISSING=object()
def diffs(a,b,path=''):
 def value(x):return {'missing':True} if x is MISSING else x
 if type(a)!=type(b):return [{'path':path or '/','expected':value(a),'actual':value(b)}]
 if type(a)==dict:
  return [r for k in sorted(set(a)|set(b)) for r in diffs(a.get(k,MISSING),b.get(k,MISSING),path+'/'+k.replace('~','~0').replace('/','~1'))]
 if type(a)==list:
  return [r for i in range(max(len(a),len(b))) for r in diffs(a[i] if i<len(a) else MISSING,b[i] if i<len(b) else MISSING,path+'/'+str(i))]
 return [] if a==b else [{'path':path or '/','expected':a,'actual':b}]
import string

def original(raw):
 s=parse(raw);shape(s,'text source serverSettings' if 'serverSettings' in s else 'text source')
 d=s.get('serverSettings',{'mockServerVersion':'unknown','wireMockVersion':'unknown','mockServerMatchExactCase':'unknown'})
 shape(d,'mockServerVersion wireMockVersion mockServerMatchExactCase')
 for k,allowed in [('mockServerVersion',('8.0.0','unknown')),('wireMockVersion',('3.13.2','unknown')),('mockServerMatchExactCase',('true','false','unknown'))]:
  if type(d[k]) is not str or d[k] not in allowed:reject('settings')
 want=expected({k:v for k,v in s.items() if k!='serverSettings'})
 path=want['request']['urlPath'];variants=[path[:i]+c.swapcase()+path[i+1:] for i,c in enumerate(path) if c in string.ascii_letters]
 verdict='unknown';witness=''
 if 'unknown' not in d.values():
  verdict='different' if d['mockServerMatchExactCase']=='false' and variants else 'compatible'
  if verdict=='different':witness=variants[0]
 return want,{**d,'pathCase':verdict,'contrastPath':witness}
def result(source,target):
 try:want,matching=original(source)
 except (ValueError,TypeError,KeyError,UnicodeError):return {'status':'unsupported-source'}
 try:got=parse(target)
 except (ValueError,TypeError,UnicodeError):return {'status':'invalid-target','matching':matching}
 rows=diffs(want,got)
 return {'status':'mismatch' if rows else {'compatible':'accepted','different':'policy-difference','unknown':'policy-unknown'}[matching['pathCase']],'findings':rows,'matching':matching}

def check(source,target):
 out={'contract':'tv4c-independent-fields-and-policy-1','sourceSHA256':digest(source),'targetSHA256':digest(target),**result(source,target)}
 out['id']=digest(json.dumps(out,sort_keys=True,separators=(',',':')).encode());return out
if __name__=='__main__':
 from pathlib import Path
 print(json.dumps(check(Path(sys.argv[1]).read_bytes(),Path(sys.argv[2]).read_bytes()),separators=(',',':')))
