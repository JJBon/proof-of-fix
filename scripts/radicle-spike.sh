#!/usr/bin/env bash
# The Radicle spike (proof-of-fix#190): can the judges, as a repository's delegates (threshold 2 of 3), merge a fix
# only after its head moves on-chain in Heads, and can nobody else move the canonical `main`?
#
#   scripts/radicle-spike.sh          build the node image, run every scenario, print pass/fail, clean up
#   scripts/radicle-spike.sh clean    remove any containers and network a stopped run left behind (v1's and v3's)
#   scripts/radicle-spike.sh --v3     the spike under v3 (proof-of-fix#251): candidates (a) and (b) with the v3
#                                     contracts on anvil and v3 node objects (spikes/radicle/v3_spike.py)
#
# Everything runs in Docker on a network created with --internal (no route out): an anvil with Heads deployed, three
# judge nodes (the delegates), one outsider node, and a fresh "viewer" node per clone check. The only download is the
# pinned Radicle release, at image build time (spikes/radicle/Dockerfile). The nodes use Radicle's test network (no
# bootstrap nodes), no preferred seeds, static peers, and connect only to each other. Keys are throwaway, generated in
# the containers and never printed; anvil's dev accounts are used unlocked, so no private key is handled at all.
# Simulated money only. The node logs and the results are kept in .radicle-spike/ (gitignored) after the run.
#
# Needs: Docker, and the pinned solc (scripts/contracts.sh setup).
set -euo pipefail
cd "$(dirname "$0")/.."

P=pof190
NET=$P-net
IMAGE=$P-radicle:spike
FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
# shellcheck source=scripts/solc.sh
source scripts/solc.sh # SOLC: the same pinned solc as scripts/contracts.sh
OUT=.radicle-spike
NODES=(judge1 judge2 judge3 outsider)
JUDGES=(judge1 judge2 judge3)
RPC=http://anvil:8545
HOME_C=/home/foundry

clean() {
  docker ps -aq --filter "name=^$P-" | xargs -r docker rm -f >/dev/null
  docker network rm "$NET" >/dev/null 2>&1 || true
}

if [[ "${1:-}" == clean ]]; then clean; python3 spikes/radicle/v3_spike.py clean >/dev/null; echo "cleaned"; exit 0; fi
[[ $# -eq 0 || "$1" == --v3 ]] || { sed -n '5,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
if [[ "${1:-}" == --v3 ]]; then
  # Under v3 (#251): the same image and isolation rules; the run, its scenarios and its clean-up are in Python, as
  # the v3 node objects it drives are. Results and node logs: .radicle-spike/v3/.
  echo "building $IMAGE (pinned Radicle release, sha256-checked) ..."
  docker build -q -t "$IMAGE" spikes/radicle >/dev/null
  POF_SOLC="$SOLC" exec python3 spikes/radicle/v3_spike.py run "${@:2}" </dev/null
fi

# --- helpers -------------------------------------------------------------------------------------------------------
declare -A DID RESULT
ORDER=()
current=""
scenario() { current=$1; ORDER+=("$1"); RESULT[$1]=PASS; echo; echo "=== $1"; }
ok() { echo "  ok   $*"; }
bad() { echo "  FAIL $*"; RESULT[$current]=FAIL; }
expect_eq() { # description actual expected
  if [[ "$2" == "$3" ]]; then ok "$1: $2"; else bad "$1: got '$2', want '$3'"; fi
}
on() { local n=$1; shift; docker exec -w "$HOME_C/repo" "$P-$n" bash -c "$*"; }
on_home() { local n=$1; shift; docker exec -w "$HOME_C" "$P-$n" bash -c "$*"; }
chain() { docker exec "$P-anvil" "$@"; }
storage() { echo "$HOME_C/.radicle/storage/${RID#rad:}"; }
canonical() { on_home "$1" "git --git-dir $(storage) rev-parse refs/heads/main"; } # the canonical ref on that node
ns_main() { on_home "$1" "git --git-dir $(storage) rev-parse refs/namespaces/${2#did:key:}/refs/heads/main"; }
# rad sync takes the RID as a positional argument (Radicle 1.10.3 refuses --rid); a failed sync is reported, not hidden
# (it doesn't fail a scenario by itself: the checks after it read each node's own copy).
sync_on() { # node [fetch|announce]
  local out
  out=$(on_home "$1" "rad sync --${2:-fetch} $RID 2>&1") ||
    echo "  warn $1: rad sync --${2:-fetch} $RID failed: $(grep -v '^[[:space:]]*$' <<<"$out" | tail -1)"
}
sync_all() { for n in "${NODES[@]}"; do sync_on "$n"; done; }
onchain_head() {
  chain cast call --rpc-url http://127.0.0.1:8545 "$HEADS" \
    "head(bytes32)((bytes32,bytes32,uint256,uint256,uint256,bytes32))" "$REPO_ID" | tr -d '()' | cut -d, -f1
}
b32() { echo "0x${1}000000000000000000000000"; } # a git SHA-1, left-aligned in bytes32
all_canonical_eq() { # description expected-sha: the canonical main on every node
  local n
  for n in "${NODES[@]}"; do expect_eq "$1 canonical main on $n" "$(canonical "$n")" "$2"; done
}
gate() { # judge fix: the judge's chain gate; prints its output, returns its exit code
  docker exec -w "$HOME_C/repo" -e RPC="$RPC" -e HEADS="$HEADS" -e REPO_ID="$REPO_ID" -e RID="$RID" \
    "$P-$1" gate.sh "$2" 2>&1 | sed 's/^/    /'
  return "${PIPESTATUS[0]}"
}
start_node() { # name: a node container on the internal network, initialised, connected to the given peers
  local n=$1; shift
  docker run -d --name "$P-$n" --hostname "$n" --network "$NET" --network-alias "$n" "$IMAGE" >/dev/null
  DID[$n]=$(on_home "$n" node-init.sh "$n" 2>/dev/null)
  local peer
  for peer in "$@"; do on_home "$n" "rad node connect ${DID[$peer]#did:key:}@$peer:8776 >/dev/null"; done
}
fresh_clone_head() { # viewer-name: a brand-new node clones the repository from the network; prints its HEAD
  start_node "$1" "${NODES[@]}"
  on_home "$1" "rad clone $RID fresh --no-confirm >/dev/null 2>&1 && git -C fresh rev-parse HEAD"
}
patch_status() { sync_on "$1" >&2; on "$1" "rad patch show $2" | sed -n 's/^│ *Status *\([a-z]*\).*/\1/p'; }
identity() { # node: "<number of delegates> <threshold>" of the identity document in force on that node
  on "$1" "rad inspect --identity" | tr -d ' \n' | sed -E 's/.*"delegates":\[([^]]*)\],"threshold":([0-9]+).*/\1 \2/' |
    awk '{ print gsub(/did:key:/, "", $1), $2 }'
}

# --- setup ---------------------------------------------------------------------------------------------------------
clean
trap clean EXIT
rm -rf "$OUT" && mkdir -p "$OUT"
echo "building $IMAGE (pinned Radicle release, sha256-checked) ..."
docker build -q -t "$IMAGE" spikes/radicle >/dev/null
docker network create --internal "$NET" >/dev/null
docker run -d --name "$P-anvil" --network "$NET" --network-alias anvil --entrypoint anvil "$FOUNDRY_IMAGE" \
  --host 0.0.0.0 --port 8545 --chain-id 31337 --silent >/dev/null
for n in "${NODES[@]}"; do start_node "$n"; done
for a in "${NODES[@]}"; do # a full mesh among the four nodes, and nothing else
  for b in "${NODES[@]}"; do
    [[ "$a" < "$b" ]] && on_home "$a" "rad node connect ${DID[$b]#did:key:}@$b:8776 >/dev/null"
  done
done
echo "radicle: $(on_home judge1 'rad --version')"
for n in "${NODES[@]}"; do echo "  $n ${DID[$n]}"; done

# --- A. setup: the repository, its delegates (3 judges, threshold 2), and Heads' genesis ---------------------------
scenario "A. setup: 3 judge delegates, threshold 2; Heads genesis = the initial commit"
on_home judge1 'mkdir repo && cd repo && git init -q -b main &&
  printf "def add(a, b):\n    return a - b\n" > calc.py && git add calc.py && git commit -q -m "genesis: add() is wrong" &&
  rad init --name pof-target --description "proof-of-fix#190 spike target" --default-branch main --public \
    --no-confirm >/dev/null 2>&1'
RID=$(on judge1 'rad .')
GENESIS=$(on judge1 'git rev-parse main')
echo "  RID $RID, genesis $GENESIS"
for n in judge2 judge3 outsider; do on_home "$n" "rad clone $RID repo --no-confirm >/dev/null 2>&1"; done
# A delegate must have published the default branch before it can be added (rad refuses: "the delegate is missing").
for n in judge2 judge3; do on "$n" 'git push -q rad main 2>/dev/null'; done
sync_on judge1
on judge1 "rad id update --title 'The judges are the delegates' \
  --description 'Three judge seats, threshold 2 (proof-of-fix#190)' \
  --delegate ${DID[judge2]} --delegate ${DID[judge3]} --threshold 2 --no-confirm >/dev/null 2>&1"
sync_on judge1 announce
sync_all
for n in "${NODES[@]}"; do expect_eq "identity on $n (delegates threshold)" "$(identity "$n")" "3 2"; done
# Heads on anvil: repo id = keccak256(RID), genesis head = the initial commit, mover = anvil's 2nd dev account (it
# stands in for RaceV2.merged()). Heads requires its Verdicts to have code: a 1-byte stub contract stands in.
DEPLOYED=$(docker run --rm -i --network "$NET" --user "$(id -u):$(id -g)" -v "$PWD/contracts:/work" \
  -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work --entrypoint bash "$FOUNDRY_IMAGE" -s "$RID" "$GENESIS" <<'EOF'
set -euo pipefail
RPC=http://anvil:8545
for _ in $(seq 50); do cast chain-id --rpc-url $RPC >/dev/null 2>&1 && break; sleep 0.2; done
accounts=$(cast rpc --rpc-url $RPC eth_accounts | tr -d '[]" ')
deployer=$(cut -d, -f1 <<<"$accounts"); mover=$(cut -d, -f2 <<<"$accounts")
stub=$(cast send --rpc-url $RPC --unlocked --from "$deployer" --create 0x6001600c60003960016000f300 --json |
  grep -o '"contractAddress":"0x[0-9a-fA-F]*"' | cut -d'"' -f4)
repo=$(cast keccak "$1")
heads=$(forge create --rpc-url $RPC --unlocked --from "$deployer" --broadcast src/v2/Heads.sol:Heads \
  --constructor-args "$stub" "[$repo]" "[0x${2}000000000000000000000000]" "$(cast keccak 'spike constitution')" \
  "$mover" 2>/dev/null | sed -n 's/^Deployed to: //p')
echo "$heads $repo $mover"
EOF
)
read -r HEADS REPO_ID MOVER <<<"$DEPLOYED"
echo "  Heads $HEADS, repo id $REPO_ID, mover $MOVER"
expect_eq "Heads.head(repo) at genesis" "$(onchain_head)" "$(b32 "$GENESIS")"
all_canonical_eq "genesis:" "$GENESIS"

# --- B. the judges merge: the head moves on-chain, then 2 of 3 delegates push through the gate ----------------------
scenario "B. judges merge: Heads.move, then 2 of 3 gated pushes; canonical main = Heads.head"
PATCH=$(on outsider 'git checkout -q -b fix &&
  printf "def add(a, b):\n    return a + b\n" > calc.py && git commit -q -a -m "fix add()" &&
  git push rad HEAD:refs/patches 2>&1' | sed -n 's/.*Patch \([0-9a-f]\{40\}\) opened.*/\1/p')
FIX=$(on outsider 'git rev-parse fix')
echo "  outsider's patch $PATCH, fix $FIX"
sync_all
chain cast send --rpc-url http://127.0.0.1:8545 --unlocked --from "$MOVER" "$HEADS" \
  "move(bytes32,bytes32,bytes32,uint256,uint256,bytes32)" "$REPO_ID" "$(b32 "$GENESIS")" "$(b32 "$FIX")" 1 1 \
  "$(chain cast keccak "verdict on $FIX")" >/dev/null
expect_eq "Heads.head(repo) after move" "$(onchain_head)" "$(b32 "$FIX")"
if gate judge1 "$FIX"; then ok "judge1's gate pushed"; else bad "judge1's gate refused"; fi
sync_all
all_canonical_eq "1 of 3 pushed:" "$GENESIS"
expect_eq "patch status after 1 of 3" "$(patch_status outsider "$PATCH")" "open"
if gate judge2 "$FIX"; then ok "judge2's gate pushed"; else bad "judge2's gate refused"; fi
sync_all
all_canonical_eq "2 of 3 pushed:" "$FIX"
expect_eq "canonical main on judge1 = Heads.head(repo)" "$(b32 "$(canonical judge1)")" "$(onchain_head)"
expect_eq "a fresh clone's HEAD (new node viewer-b)" "$(fresh_clone_head viewer-b)" "$FIX"
expect_eq "patch status after 2 of 3" "$(patch_status outsider "$PATCH")" "merged"

# --- E. the gate refuses a commit that isn't Heads.head(repo) -------------------------------------------------------
scenario "E. gate refuses: stale (old head) or unjudged commit; nothing pushed"
UNJUDGED=$(on outsider 'git checkout -q -b unjudged fix && printf "# unjudged\n" >> calc.py &&
  git commit -q -a -m "an unjudged change" && git push -q rad unjudged 2>/dev/null; git rev-parse HEAD')
sync_all
before=$(ns_main judge3 "${DID[judge3]}")
gate judge3 "$GENESIS" && code=0 || code=$?
expect_eq "judge3's gate on the stale genesis commit: exit code" "$code" 3
gate judge3 "$UNJUDGED" && code=0 || code=$?
expect_eq "judge3's gate on the unjudged commit: exit code" "$code" 3
gate judge3 "not-a-sha" && code=0 || code=$?
expect_eq "judge3's gate on a malformed input: exit code" "$code" 2
sync_all
expect_eq "judge3's own main unchanged (on judge1's copy)" "$(ns_main judge1 "${DID[judge3]}")" "$before"
all_canonical_eq "after refusals:" "$FIX"
if gate judge3 "$FIX"; then ok "judge3 catches up to the judged head through its gate"; else bad "judge3 refused"; fi

# --- D. an outsider pushes its own main to an unjudged commit and opens a patch -------------------------------------
scenario "D. outsider: own main -> unjudged commit, plus a patch; canonical main unchanged"
on outsider "git push -q -f rad $UNJUDGED:refs/heads/main 2>/dev/null; git push -q rad unjudged:refs/patches 2>/dev/null"
sync_all
expect_eq "the outsider's own main (on judge1's copy) is the unjudged commit" \
  "$(ns_main judge1 "${DID[outsider]}")" "$UNJUDGED"
expect_eq "the outsider's patches (open)" "$(on judge1 'rad patch list' | grep -c 'outsider')" 1
all_canonical_eq "outsider pushed:" "$FIX"
expect_eq "a fresh clone's HEAD (new node viewer-d)" "$(fresh_clone_head viewer-d)" "$FIX"

# --- C. one delegate alone, bypassing its gate, pushes main to an unjudged commit ----------------------------------
scenario "C. one delegate alone (gate bypassed) pushes main; canonical main unchanged"
ROGUE=$(on judge1 "git fetch -q $(storage) $FIX && git checkout -q -B main $FIX && printf '# rogue\n' >> calc.py &&
  git commit -q -a -m 'a rogue change, never judged' && git rev-parse HEAD")
on judge1 'git push -q rad main 2>/dev/null'
sync_all
expect_eq "judge1's own main (on judge2's copy) is the rogue commit" "$(ns_main judge2 "${DID[judge1]}")" "$ROGUE"
all_canonical_eq "one delegate pushed:" "$FIX"
expect_eq "Heads.head(repo) unchanged" "$(onchain_head)" "$(b32 "$FIX")"
# A second delegate, alone too, force-pushes a commit that diverges from the judged head (built on genesis): judge1's
# main still descends from the fix, so the fix keeps 2 votes (judge1, judge2) and stays canonical.
DIVERGED=$(on judge3 "git fetch -q $(storage) $GENESIS && git checkout -q -B main $GENESIS && printf '# other\n' >> calc.py &&
  git commit -q -a -m 'a diverging change, never judged' && git rev-parse HEAD")
on judge3 'git push -q -f rad main 2>/dev/null || true'
sync_all
expect_eq "judge3's own main (on judge2's copy) is the diverging commit" "$(ns_main judge2 "${DID[judge3]}")" "$DIVERGED"
all_canonical_eq "two lone delegates disagree:" "$FIX"
# The next fix is judged on-chain; the rogue delegate's gate refuses it: its own main no longer fast-forwards to it.
FIX2=$(on outsider 'git checkout -q -b fix2 fix && printf "# fix 2\n" >> calc.py && git commit -q -a -m "fix 2" &&
  git push -q rad HEAD:refs/patches 2>/dev/null; git rev-parse HEAD')
sync_all
chain cast send --rpc-url http://127.0.0.1:8545 --unlocked --from "$MOVER" "$HEADS" \
  "move(bytes32,bytes32,bytes32,uint256,uint256,bytes32)" "$REPO_ID" "$(b32 "$FIX")" "$(b32 "$FIX2")" 2 2 \
  "$(chain cast keccak "verdict on $FIX2")" >/dev/null
expect_eq "Heads.head(repo) after the second move" "$(onchain_head)" "$(b32 "$FIX2")"
gate judge1 "$FIX2" && code=0 || code=$?
expect_eq "judge1's gate on the next judged fix, from its rogue main: exit code" "$code" 4

# --- F. one delegate alone tries to change the delegate set --------------------------------------------------------
scenario "F. one delegate alone proposes 'drop judge3, threshold 1'; the identity doesn't change"
on judge2 "rad id update --title 'Drop judge3' --description 'One delegate alone (proof-of-fix#190)' \
  --rescind ${DID[judge3]} --threshold 1 --no-confirm >/dev/null 2>&1 || true"
sync_on judge2 announce
sync_all
REV=$(on judge2 'rad id list' | sed -n 's/^│ *● *\([0-9a-f]\{7\}\) *Drop judge3.*active.*/\1/p')
if [[ -n "$REV" ]]; then ok "the revision $REV is proposed and active (not accepted)"; else bad "no active revision"; fi
for n in "${NODES[@]}"; do expect_eq "identity on $n (delegates threshold)" "$(identity "$n")" "3 2"; done

# --- G. control: two delegates who both bypass their gates do move main (threshold is all Radicle checks) ----------
scenario "G. control: 2 of 3 delegates bypassing their gates DO move main (why the keys need #94)"
on judge2 "git fetch -q $(storage) $ROGUE && git push -q rad $ROGUE:refs/heads/main 2>/dev/null"
sync_all
all_canonical_eq "two delegates pushed the rogue commit:" "$ROGUE"
expect_eq "Heads.head(repo) is the judged fix 2 (the chain and Radicle now disagree)" \
  "$(onchain_head)" "$(b32 "$FIX2")"
if [[ -n "$REV" ]]; then
  sync_on judge1
  on judge1 "rad id accept $REV --no-confirm >/dev/null 2>&1 || true"
  sync_on judge1 announce
  sync_all
  expect_eq "identity on outsider after judge1 accepts F's revision (2 of 3)" "$(identity outsider)" "2 1"
fi

# --- isolation evidence --------------------------------------------------------------------------------------------
scenario "I. isolation: internal network, no route out, nodes dialled only each other"
expect_eq "network $NET is internal" "$(docker network inspect -f '{{.Internal}}' "$NET")" true
subnet=$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' "$NET")
prefix=$(cut -d. -f1-2 <<<"$subnet")
local_hosts="judge1|judge2|judge3|outsider|viewer-b|viewer-d"
for n in "${NODES[@]}" viewer-b viewer-d; do
  docker exec "$P-$n" bash -c 'cat $RAD_HOME/node/node.log.* $RAD_HOME/node/node.log 2>/dev/null' > "$OUT/$n.log"
  expect_eq "$n: default routes" "$(docker exec "$P-$n" awk '$2 == "00000000"' /proc/net/route | wc -l)" 0
  expect_eq "$n: bootstrap nodes added" "$(sed -n 's/.* \([0-9]*\) nodes added to address book.*/\1/p' "$OUT/$n.log" | sort -u)" 0
  dialled=$(grep -E 'Connecting to|Attempted connection to|Connected to' "$OUT/$n.log" |
    sed -nE 's/.*\(([^()]*:[0-9]+)\).*/\1/p' | sed -E 's/:[0-9]+$//' | sort -u | tr '\n' ' ')
  foreign=$(tr ' ' '\n' <<<"$dialled" | grep -vE "^($local_hosts|$prefix\.[0-9]+\.[0-9]+|)$" || true)
  expect_eq "$n: peers outside the spike network (dialled: $dialled)" "${foreign:-none}" none
  ips=$(grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' "$OUT/$n.log" | grep -vE "^($prefix\.|0\.0\.0\.0$|127\.)" | sort -u |
    tr '\n' ' ' || true)
  expect_eq "$n: IP addresses in the log outside $subnet" "${ips:-none}" none
  expect_eq "$n: public Radicle hostnames in the log" \
    "$(grep -ciE 'radicle\.(xyz|garden|dev|network)|seed\.radicle|iris\.|rosa\.' "$OUT/$n.log" || true)" 0
done

# --- summary -------------------------------------------------------------------------------------------------------
{
  echo "radicle $(on_home judge1 'rad --version')"
  echo "RID $RID; Heads $HEADS; genesis $GENESIS; fix $FIX; unjudged $UNJUDGED; rogue $ROGUE; diverged $DIVERGED; fix2 $FIX2"
  for s in "${ORDER[@]}"; do echo "${RESULT[$s]}  $s"; done
} | tee "$OUT/results.txt" | { echo; echo "=== results"; cat; }
! grep -q '^FAIL' "$OUT/results.txt"
