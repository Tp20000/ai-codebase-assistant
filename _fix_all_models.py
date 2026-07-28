from pathlib import Path

backend = Path("backend")
for py_file in backend.rglob("*.py"):
    try:
        content = py_file.read_text(encoding="utf-8")
        if "llama3.2" in content:
            fixed = content.replace("llama3.2", "tinyllama")
            py_file.write_text(fixed, encoding="utf-8")
            print(f"Fixed: {py_file}")
    except Exception as e:
        pass

for env_file in ["backend/.env", "backend/.env.example", ".env"]:
    p = Path(env_file)
    if p.exists():
        content = p.read_text(encoding="utf-8")
        if "llama3.2" in content:
            p.write_text(content.replace("llama3.2", "tinyllama"), encoding="utf-8")
            print(f"Fixed env: {p}")
