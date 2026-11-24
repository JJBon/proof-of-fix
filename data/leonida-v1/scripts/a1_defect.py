import json, re, math, collections
L = json.load(open('a1_links.json'))
D = json.load(open('a1a2_derived.json')); ci = {int(k): v for k, v in D['ci'].items()}
M = {json.loads(l)['number']: json.loads(l) for l in open('merged_full.jsonl')}
# hand labels from a random sample of 45 X (seed 11), see report
labels = {3278:'d',2100:'d',4060:'d',4427:'d',3978:'d',6318:'d',666:'d',1388:'d',787:'d',4170:'d',2066:'d',2505:'d',1900:'d',
          747:'b?',6339:'b?',743:'b?',3660:'b?',
          753:'f',419:'f',1302:'f',630:'f',383:'f',2859:'f',6208:'f',1671:'f',79:'f',2726:'f',278:'f',4343:'f',122:'f',2603:'f',6285:'f',1282:'f',2479:'f',1948:'f',
          6908:'u',4657:'u',291:'u',1017:'u',1849:'u',965:'u',204:'u',152:'u',2167:'u',4549:'u'}
DEF = re.compile(r'(?i)\b(regress\w*|broke|broken|breaks|breakage|restor\w*|revert\w*|introduced|wrong|incorrect|dropped by|merged (?:without|before)|still (?:causes?|fails?|crash\w*|leaks?|reads?)|fails? (?:on \S+ )?since|crash\w* since|missed|bug (?:in|from)|caused by)\b')
defect = collections.defaultdict(list)
for x, y, line, h in L:
    if DEF.search(line): defect[x].append((y, line))
pred = set(defect)
tp = sum(1 for x, l in labels.items() if l == 'd' and x in pred); fp = sum(1 for x, l in labels.items() if l != 'd' and x in pred)
fn = sum(1 for x, l in labels.items() if l == 'd' and x not in pred)
print(f'defect classifier on 45 hand-labelled: TP {tp} FP {fp} FN {fn}  precision {tp/max(1,tp+fp):.2f} recall {tp/max(1,tp+fn):.2f}')
print('FPs:', [x for x, l in labels.items() if l != 'd' and x in pred], 'FNs:', [x for x, l in labels.items() if l == 'd' and x not in pred])
def wilson(k, n, z=1.96):
    p = k/n; d = 1+z*z/n; c = (p+z*z/(2*n))/d; h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d; return p, c-h, c+h
N = len(M); p, lo, hi = wilson(len(pred), N)
print(f'T1-defect: {len(pred)} / {N} = {100*p:.1f}% (95% CI {100*lo:.1f}-{100*hi:.1f})')
# hand-label-based estimate: precision of T1-any for 'd'
k = sum(1 for l in labels.values() if l == 'd'); p, lo, hi = wilson(k, 45)
print(f'hand-labelled share of T1-any links that are real defects: {k}/45 = {100*p:.0f}% (CI {100*lo:.0f}-{100*hi:.0f}) -> est. {363*p:.0f} ({363*lo:.0f}-{363*hi:.0f}) defective merges = {100*363*p/N:.1f}% ({100*363*lo/N:.1f}-{100*363*hi/N:.1f}) of merged')
print('\n2x2 on T1-defect:')
rows = {}
for g in ['green', 'red', 'none']:
    G = [x for x in M if ci[x][0] == g]; kk = sum(1 for x in G if x in pred); rows[g] = (kk, len(G))
    p, lo, hi = wilson(kk, len(G)); print(f'  {g:5s}: {kk:3d}/{len(G):4d} = {100*p:.1f}% (95% CI {100*lo:.1f}-{100*hi:.1f})')
def diff(a, b):
    (k1, n1), (k2, n2) = a, b; p1, p2 = k1/n1, k2/n2; se = math.sqrt(p1*(1-p1)/n1+p2*(1-p2)/n2)
    return f'{100*(p1-p2):.1f} pp (95% CI {100*(p1-p2-1.96*se):.1f} to {100*(p1-p2+1.96*se):.1f})'
ng = (rows['red'][0]+rows['none'][0], rows['red'][1]+rows['none'][1])
print('  not-green minus green:', diff(ng, rows['green'])); print('  red minus green:', diff(rows['red'], rows['green']))
json.dump(sorted(pred), open('a1_defect_set.json', 'w'))
for x in sorted(pred)[:0]: pass
