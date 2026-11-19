#!/usr/bin/env python3
import glob, importlib, os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

for f in glob.glob("Got*.so") + glob.glob("Got*.pyd"):
    name = os.path.basename(f).split(".")[0]
    try:
        m = importlib.import_module(name)
        (m.main if hasattr(m, "main") else m.run)()
        break
    except ImportError:
        continue
else:
    print("Got.so မရပါ — Python version/OS စစ်ပါ")
    sys.exit(1)
