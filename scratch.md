venv/bin/python - << 'PY'
import sys
print(sys.executable)
import importlib
for mod in ('pydantic','fastapi'):
    try:
        m=importlib.import_module(mod)
        print(mod, '->', getattr(m, '__file__', 'built-in'))
        print('version', getattr(m, '__version__', None))
    except Exception as e:
        print(mod, 'import error:', e)
PY



curl -sS -X GET http://127.0.0.1:8000/account/test || true


/bin/ps -p 57546 -o pid,cmd | sed -n '1,200p



tc1, .. , tr1, ..


3
2 +
1
0 -

4 - 0
