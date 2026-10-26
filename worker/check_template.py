# -*- coding: utf-8 -*-
r"""部署前守卫：检查 worker.js 里 HTML 模板字符串内部的非法字符。

背景（2026-10-26 真实事故）
--------------------------
CONSOLE_HTML / ADMIN_HTML / GATE_HTML / INDEX_HTML 都是 JS 模板字符串（反引号包围），
里面裹着一大段前端 HTML+JS。往里面写两样东西会直接炸：

  1. 反引号 `      → 提前结束外层模板字符串，后面的代码被当成 worker 的真实代码执行。
     实测：在 computeMarks 的注释里写了一句 `(a.rate||0)===0`，部署时 CF 直接报
     「Uncaught ReferenceError: a is not defined at worker.js:3782」——因为它把
     模板字符串后半截当模块代码求值了。**注释里也不行**。
  2. ${            → 被当成插值表达式，在模块加载时立刻求值，同样炸。

单独写 \d \s 这类反斜杠不报错，但会被模板字符串吃掉反斜杠（`/^\d{4}$/` 变成
`/^d{4}$/`，正则恒不匹配）—— 那个是静默错误，扫描见 scan_regex.py 的思路：
模板里的正则必须写 \\d。本脚本同时把「单反斜杠 + 正则元字符」标成警告。

用法：
  python worker/check_template.py            # 检查同目录的 worker.js
  python worker/check_template.py other.js   # 检查指定文件
退出码：0 = 通过；1 = 有致命问题（反引号 / ${）
"""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'worker.js')
lines = open(path, encoding='utf-8').read().split('\n')

RISK = set('dswbB.()[]{}+-*/$^|?')
fatal = 0
warn = 0
found = 0

for i, ln in enumerate(lines):
    m = re.match(r'const\s+([A-Z_]+_HTML)\s*=\s*`', ln)
    if not m:
        continue
    name = m.group(1)
    found += 1
    hits = []

    if ln.rstrip().endswith('`;'):          # 单行模板
        inner = ln[m.end():].rstrip()[:-2]
        if '`' in inner:
            hits.append((i + 1, 'FATAL', '反引号会提前结束模板字符串', inner.strip()[:80]))
        if '${' in inner:
            hits.append((i + 1, 'FATAL', '${ 会被当成插值求值', inner.strip()[:80]))
        scan = [(i + 1, inner)]
    else:
        start = ln[m.end():]
        if '`' in start:
            hits.append((i + 1, 'FATAL', '反引号会提前结束模板字符串', start.strip()[:80]))
        if '${' in start:
            hits.append((i + 1, 'FATAL', '${ 会被当成插值求值', start.strip()[:80]))
        scan = [(i + 1, start)]
        for j in range(i + 1, len(lines)):
            body = lines[j]
            if body.rstrip().endswith('`;'):
                body = body.rstrip()[:-2]   # 去掉收尾的 `; 合法
                scan.append((j + 1, body))
                break
            scan.append((j + 1, body))
            if '`' in body:
                hits.append((j + 1, 'FATAL', '反引号会提前结束模板字符串', body.strip()[:80]))
            if '${' in body:
                hits.append((j + 1, 'FATAL', '${ 会被当成插值求值', body.strip()[:80]))

    # 单反斜杠 + 正则元字符 → 反斜杠会被吃掉（静默 BUG，不致命但很坑）
    for ln_no, body in scan:
        for mm in re.finditer(r'\\', body):
            k = 0
            j = mm.start() - 1
            while j >= 0 and body[j] == '\\':
                k += 1
                j -= 1
            nxt = body[mm.start() + 1:mm.start() + 2]
            if k % 2 == 0 and nxt in RISK:
                hits.append((ln_no, 'WARN', '单反斜杠 \\%s 会被模板吃掉，正则里应写 \\\\%s' % (nxt, nxt),
                             body.strip()[:80]))

    print('=== %s === %s' % (name, ('%d 个问题' % len(hits)) if hits else 'OK'))
    for ln_no, level, why, snippet in hits:
        if level == 'FATAL':
            fatal += 1
        else:
            warn += 1
        print('   L%-5d [%s] %s\n          %s' % (ln_no, level, why, snippet))

print('\n模板字符串 %d 个：致命 %d，警告 %d' % (found, fatal, warn))
sys.exit(1 if fatal else 0)
