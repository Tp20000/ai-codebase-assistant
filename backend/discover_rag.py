import sys
sys.path.insert(0, '.')

print("=== embeddings.py ===")
import app.core.rag.embeddings as e
print([x for x in dir(e) if not x.startswith("_")])

print("=== vector_store.py ===")
import app.core.rag.vector_store as vs
print([x for x in dir(vs) if not x.startswith("_")])
vs_class = None
for name in dir(vs):
    obj = getattr(vs, name)
    if isinstance(obj, type):
        print(f"  Class {name} methods:", [m for m in dir(obj) if not m.startswith("_")])
        vs_class = obj

print("=== prompt_templates.py ===")
import app.core.llm.prompt_templates as pt
print([x for x in dir(pt) if not x.startswith("_")])