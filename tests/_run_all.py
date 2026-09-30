# -*- coding: utf-8 -*-
"""逐文件回归驱动：每个测试文件独立进程，崩溃/失败不串扰，汇总报告。"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
files = sorted((HERE / "tests").glob("test_*.py"))
fails, crashes, passed_files = [], [], 0
t0 = time.time()
for i, f in enumerate(files, 1):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(f), "-q", "--tb=line",
             "-p", "no:faulthandler"],
            cwd=HERE, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
    except subprocess.TimeoutExpired:          # 单文件超时不拖垮整轮回归
        print(f"[{i:02d}/{len(files)}] SLOW  {f.name:40s} >300s（跳过，可单独复跑）")
        fails.append((f.name, "TIMEOUT", "pytest 300s 未结束"))
        continue
    out = (r.stdout or "") + (r.stderr or "")
    tail = out.strip().splitlines()[-1] if out.strip() else "<no output>"
    if r.returncode == 0:
        passed_files += 1
        print(f"[{i:02d}/{len(files)}] PASS  {f.name:40s} {tail}")
    elif r.returncode < 0 or r.returncode in (3221225477, 2147483651, -2147483645):
        crashes.append((f.name, r.returncode, tail))
        print(f"[{i:02d}/{len(files)}] CRASH {f.name:40s} rc={r.returncode} {tail}")
    else:
        fails.append((f.name, r.returncode, out))
        print(f"[{i:02d}/{len(files)}] FAIL  {f.name:40s} rc={r.returncode} {tail}")

print("\n" + "=" * 72)
print(f"文件数={len(files)} 通过={passed_files} 失败={len(fails)} 崩溃={len(crashes)} "
      f"耗时={time.time()-t0:.0f}s")
for name, rc, _ in crashes:
    print(f"  CRASH {name} rc={rc}")
for name, rc, out in fails:
    print(f"  FAIL  {name} rc={rc}")
    for line in out.strip().splitlines()[-12:]:
        print("    " + line)
