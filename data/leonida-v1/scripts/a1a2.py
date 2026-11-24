import json, re, collections, math, random, sys
from datetime import datetime, timedelta
t = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
M = {}
for l in open('merged_full.jsonl'):
    p = json.loads(l); M[p['number']] = p
O = {}
try:
    for l in open('other_full.jsonl'):
        p = json.loads(l); O[p['number']] = p
except FileNotFoundError: pass
ALL = {**O, **M}
nums = set(M)
HARM = r'(revert\w*|regress\w*|broke|broken|breaks|breakage|breaking|restor\w*|introduced|caused|follow[- ]?up|fix(?:es|ed)?|since|after|undo\w*|roll(?:s|ed)?[- ]?back)'
ref_re = re.compile(r'(?:#|/pull/)(\d{2,5})\b')
def lines_with_refs(text):
    for line in (text or '').splitlines():
        for m in ref_re.finditer(line):
            yield int(m.group(1)), line
links = []  # (X, Y, line, tier)
for y in ALL.values():
    yc = t(y['createdAt'])
    text = (y['title'] or '') + '\n' + (y['body'] or '')
    seen = set()
    for n, line in lines_with_refs(text):
        if n == y['number'] or n not in nums or n in seen: continue
        x = M[n]
        if yc <= t(x['mergedAt']): continue   # Y must be opened after X merged
        low = line.lower()
        # keyword must be near the reference: same line, within 60 chars
        pos = [m.start() for m in re.finditer(r'(?:#|/pull/)%d\b' % n, low)]
        hit = None
        for k in re.finditer(r'\b' + HARM + r'\b', low):
            if any(abs(k.start() - p) <= 60 for p in pos): hit = k.group(1); break
        if hit:
            seen.add(n); links.append((n, y['number'], line.strip()[:220], hit))
json.dump(links, open('a1_links.json', 'w'))
strong_kw = re.compile(r'^(revert\w*|regress\w*|broke|broken|breaks|breakage|breaking|restor\w*|introduced|caused|undo\w*|roll\w*)$')
def tier(hit): return 'T1-strong' if strong_kw.match(hit) else 'T1-fix/followup'
by_x = collections.defaultdict(list)
for x, y, line, hit in links: by_x[x].append((y, tier(hit), hit))
# T2: file overlap within 24h + fix-like title, Y merged
DOC = re.compile(r'^(docs/|README|CONTRIBUTING|AGENTS)')
fixtitle = re.compile(r'(?i)\b(fix\w*|revert\w*|regress\w*|broke\w*|restor\w*|repair\w*|correct\w*)\b')
mlist = sorted(M.values(), key=lambda p: p['mergedAt'])
files = {p['number']: {f['path'] for f in p['files']['nodes'] if not DOC.match(f['path'])} for p in M.values()}
t2 = collections.defaultdict(list)
for i, x in enumerate(mlist):
    xm = t(x['mergedAt']); fx = files[x['number']]
    if not fx: continue
    for y in mlist[i+1:]:
        ym = t(y['mergedAt'])
        if ym - xm > timedelta(hours=24): break
        if t(y['createdAt']) <= xm: continue
        if fx & files[y['number']] and fixtitle.search(y['title'] or ''):
            t2[x['number']].append(y['number'])
# CI at merge
CORE = re.compile(r'^(check|translator-tests|semantic-tests.*|macos-python|viewer-tests|stdlib-tests-linux|windows|wine.*|linux-gpu-tools|no-game-data)$')
def ci_at_merge(p):
    mt = t(p['mergedAt']); n = p['commits']['nodes']
    if not n or not n[0]['commit']['statusCheckRollup']: return 'none', []
    fails, succ = [], 0
    for c in n[0]['commit']['statusCheckRollup']['contexts']['nodes']:
        if not c or not c.get('name') or not CORE.match(c['name']): continue
        if not c.get('completedAt') or t(c['completedAt']) > mt: continue
        if c['conclusion'] == 'FAILURE': fails.append(c['name'])
        elif c['conclusion'] == 'SUCCESS': succ += 1
    if fails: return 'red', fails
    if succ: return 'green', []
    return 'none', []
ci = {p['number']: ci_at_merge(p) for p in M.values()}
json.dump({'by_x': by_x, 't2': t2, 'ci': ci}, open('a1a2_derived.json', 'w'))
def wilson(k, n, z=1.96):
    if n == 0: return (float('nan'),)*3
    p = k/n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return p, c-h, c+h
N = len(M)
print('merged PRs (denominator):', N)
def report(name, S):
    k = len(S); p, lo, hi = wilson(k, N)
    print(f'{name}: {k} / {N} = {100*p:.1f}% (95% CI {100*lo:.1f}-{100*hi:.1f})')
T1s = {x for x, v in by_x.items() if any(tt == 'T1-strong' for _, tt, _ in v)}
T1 = set(by_x)
report('T1-strong (revert/regress/broke/restore/introduced/caused near #X)', T1s)
report('T1-any (also fix/follow-up/since/after near #X)', T1)
report('T2 (fix-titled merged PR touching same non-doc file within 24h)', set(t2))
report('T1-any OR T2', T1 | set(t2))
# time to fix
def ttf(S, use='T1'):
    out = []
    for x in S:
        xm = t(M[x]['mergedAt'])
        ys = [y for y, _, _ in by_x.get(x, [])] if use == 'T1' else t2.get(x, [])
        cands = []
        for y in ys:
            yy = ALL[y]
            cands.append((t(yy['createdAt']) - xm).total_seconds()/3600)
        if cands: out.append(min(cands))
    out.sort(); q = lambda f: out[min(len(out)-1, int(f*len(out)))]
    return len(out), q(.5), q(.9)
print('hours from merge of X to first follow-up PR opened (T1-any): n=%d median %.1f p90 %.1f' % ttf(T1))
print('hours (T1-strong): n=%d median %.1f p90 %.1f' % ttf(T1s))
fixed_merged = sum(1 for x in T1 if any(y in M for y, _, _ in by_x[x]))
print('T1-any X whose follow-up Y is itself merged:', fixed_merged)
print('follow-up keyword counts:', collections.Counter(h for _, _, _, h in links).most_common(15))
# 2x2
print('\nCI at merge:', collections.Counter(v[0] for v in ci.values()))
print('red-check names:', collections.Counter(n for v in ci.values() for n in v[1]).most_common(10))
for label, S in [('T1-strong', T1s), ('T1-any', T1), ('T2', set(t2)), ('T1-any|T2', T1 | set(t2))]:
    print(f'\n2x2 for outcome {label}:')
    for g in ['green', 'red', 'none']:
        G = [x for x in M if ci[x][0] == g]; k = sum(1 for x in G if x in S)
        p, lo, hi = wilson(k, len(G))
        print(f'  {g:5s}: {k:4d} later-fixed / {len(G):4d} = {100*p:5.1f}% (95% CI {100*lo:.1f}-{100*hi:.1f})')
    g1 = [x for x in M if ci[x][0] == 'green']; g2 = [x for x in M if ci[x][0] != 'green']
    a = sum(1 for x in g2 if x in S); b = len(g2); c = sum(1 for x in g1 if x in S); d = len(g1)
    p1, p2 = a/b, c/d; se = math.sqrt(p1*(1-p1)/b + p2*(1-p2)/d)
    print(f'  not-green vs green difference: {100*(p1-p2):.1f} pp (95% CI {100*(p1-p2-1.96*se):.1f} to {100*(p1-p2+1.96*se):.1f}); RR {p1/p2 if p2 else float("nan"):.2f}')
# size-stratified (confounding by size)
print('\nsize-stratified T1-any rate (green vs not-green):')
sz = lambda p: p['additions'] + p['deletions']
for lo_, hi_ in [(0, 30), (30, 150), (150, 600), (600, 10**9)]:
    row = []
    for g in [('green',), ('red', 'none')]:
        G = [x for x in M if ci[x][0] in g and lo_ <= sz(M[x]) < hi_]; k = sum(1 for x in G if x in T1)
        row.append(f'{"/".join(g)} {k}/{len(G)}={100*k/max(1,len(G)):.1f}%')
    print(f'  lines {lo_}-{hi_}: ' + '; '.join(row))
