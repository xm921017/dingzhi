# -*- coding: utf-8 -*-
r"""部署前守卫：worker.js 的两类「模板字符串炸弹」+ 页面内联 JS 语法。

背景（2026-10-26 真实事故）
--------------------------
CONSOLE_HTML / ADMIN_HTML / GATE_HTML / INDEX_HTML 都是 JS 模板字符串（反引号包围），
里面裹着一大段前端 HTML+JS。往里写两样东西会直接炸：

  1. 反引号 `   → 提前结束外层模板字符串，后面的代码被当成 worker 真实代码执行。
     实测：在 computeMarks 的注释里写了 `(a.rate||0)===0`，CF 部署直接报
     「Uncaught ReferenceError: a is not defined at worker.js:3782」——
     它把模板字符串后半截当模块代码求值了。**写在注释里也不行**。
  2. ${         → 被当成插值表达式，模块加载时立刻求值，同样炸。

另外两类静默问题也一并检查：
  3. 模板里的正则写了单反斜杠（`\d` 被吃成 `d`，`/^\d{4}$/` 变成 `/^d{4}$/`，
     正则恒不匹配）—— 这个不报错，只是逻辑悄悄失效，2026-10-26 之前踩过一次。
  4. 模板字符串本身语法没问题，但里面的前端 <script> 有语法错误 —— 只有浏览器打开
     才会炸。有 node 时抽出来跑 node --check。

用法：
  python worker/check_template.py            # 检查同目录的 worker.js
  python worker/check_template.py other.js
退出码：0 = 通过；1 = 有致命问题
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

here = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'worker.js')
lines = open(path, encoding='utf-8').read().split('\n')

RISK = set('dswbB.()[]{}+-*/$^|?')
fatal = warn = 0
templates = []          # [(name, [ (行号, 该行内容) ... ], start_line)]

for i, ln in enumerate(lines):
    m = re.match(r'const\s+([A-Z_]+_HTML)\s*=\s*`', ln)
    if not m:
        continue
    name = m.group(1)
    if ln.rstrip().endswith('`;'):                      # 单行模板
        inner = ln[m.end():].rstrip()[:-2]
        templates.append((name, [(i + 1, inner)], i + 1))
        continue
    body_rows = [(i + 1, ln[m.end():])]
    for j in range(i + 1, len(lines)):
        if lines[j].rstrip().endswith('`;'):
            body_rows.append((j + 1, lines[j].rstrip()[:-2]))
            break
        body_rows.append((j + 1, lines[j]))
    templates.append((name, body_rows, i + 1))

for name, rows, start in templates:
    hits = []
    for ln_no, body in rows:
        if '`' in body:
            hits.append((ln_no, 'FATAL', '反引号会提前结束模板字符串', body.strip()[:80]))
        if '${' in body:
            hits.append((ln_no, 'FATAL', '${ 会被当成插值求值', body.strip()[:80]))
        for mm in re.finditer(r'\\', body):
            k, j = 0, mm.start() - 1
            while j >= 0 and body[j] == '\\':
                k += 1
                j -= 1
            nxt = body[mm.start() + 1:mm.start() + 2]
            if k % 2 == 0 and nxt in RISK:
                hits.append((ln_no, 'WARN', '单反斜杠 \\%s 会被模板吃掉（正则里应写 \\\\%s）' % (nxt, nxt),
                             body.strip()[:80]))
    print('=== %s（第 %d 行起）=== %s' % (name, start, ('%d 个问题' % len(hits)) if hits else 'OK'))
    for ln_no, level, why, snippet in hits:
        if level == 'FATAL':
            fatal += 1
        else:
            warn += 1
        print('   L%-5d [%s] %s\n          %s' % (ln_no, level, why, snippet))

# ---- 页面内联 JS 语法（有 node 才查）----
node = shutil.which('node')
if node and templates:
    print('\n--- 内联 <script> 语法 ---')
    for name, rows, _ in templates:
        html = '\n'.join(b for _, b in rows)
        for k, s in enumerate(re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)):
            fd, out = tempfile.mkstemp(suffix='.js')
            os.close(fd)
            open(out, 'w', encoding='utf-8').write(s)
            r = subprocess.run([node, '--check', out], capture_output=True)
            os.remove(out)
            if r.returncode == 0:
                print('   %s script#%d OK（%d 字符）' % (name, k, len(s)))
            else:
                fatal += 1
                print('   %s script#%d 语法错误：' % (name, k))
                print((r.stderr or b'').decode('utf-8', 'replace')[:500])
elif not node:
    print('\n（没找到 node，跳过内联 <script> 语法检查）')

print('\n模板字符串 %d 个：致命 %d，警告 %d' % (len(templates), fatal, warn))
sys.exit(1 if fatal else 0)
