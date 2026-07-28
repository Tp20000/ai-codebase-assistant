import sys
sys.path.insert(0, '.')
from app.main import app
keywords = ['file','chat','history','message','agent','task','analytic']
for r in app.routes:
    if hasattr(r,'path') and hasattr(r,'methods'):
        if any(k in r.path for k in keywords):
            print(sorted(r.methods), r.path)
