"""Local preferences with tolerant reading and atomic file replacement."""
import json,os,tempfile
from pathlib import Path

def read_preferences(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,UnicodeError): return {}

def write_preferences(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='.settings-',suffix='.json',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output: json.dump(value,output,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass

def saved_integer(value,default,low,high):
    return max(low,min(high,value)) if type(value) is int else default

def saved_geometry(value):
    if not isinstance(value,list) or len(value)!=4 or not all(type(v) is int for v in value): return None
    x,y,w,h=value
    return value if abs(x)<=200000 and abs(y)<=200000 and 180<=w<=32768 and 140<=h<=32768 else None
