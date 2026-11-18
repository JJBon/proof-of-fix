#!/usr/bin/env bash
# A judge's chain gate (proof-of-fix#190), run inside a judge (delegate) node's container: push this delegate's
# signed `main` to <fix> only if the head on-chain is that exact commit and the move fast-forwards this delegate's
# own `main`. Otherwise refuse, push nothing, and exit non-zero.
#
#   gate.sh <fix-sha1>
#
# Under v3 (#251, scripts/radicle-spike.sh --v3) the same gate runs on each seated validator's node; a node with no
# `main` yet (a new seat) publishes its first one at the head.
#
# Environment: RPC (anvil's URL), HEADS (the Heads contract), REPO_ID (bytes32: keccak256 of the RID), RID, and
# REPO_DIR (this node's working copy, default ~/repo). Exit codes: 0 pushed, 2 bad input, 3 the fix isn't
# Heads.head(repo), 4 not a fast-forward, 5 the commit isn't on this node, 6 the push failed.
#
# Plain code in a container: the keys are on disk here. The enclave version, where the key signs only what this
# check allows, waits for #94.
set -euo pipefail
fix=${1:-}
: "${RPC:?}" "${HEADS:?}" "${REPO_ID:?}" "${RID:?}"
repo_dir=${REPO_DIR:-$HOME/repo}
storage="$RAD_HOME/storage/${RID#rad:}"
refuse() { echo "gate: REFUSE ($2): $1" >&2; exit "$2"; }

[[ "$fix" =~ ^[0-9a-f]{40}$ ]] || refuse "not a full SHA-1: '$fix'" 2

# 1. The head on-chain. Heads.head returns a struct whose first field is the commit (bytes32, SHA-1 left-aligned).
onchain=$(cast call --rpc-url "$RPC" "$HEADS" \
  "head(bytes32)((bytes32,bytes32,uint256,uint256,uint256,bytes32))" "$REPO_ID" | tr -d '()' | cut -d, -f1)
want="0x${fix}000000000000000000000000"
[[ "${onchain,,}" == "$want" ]] || refuse "fix $fix is not Heads.head(repo) = $onchain" 3

# 2. The commit is on this node (from the patch or branch it was proposed on), and it fast-forwards this delegate's
#    own signed `main` (its namespace in storage, not the canonical ref and not the working copy).
rad sync --fetch "$RID" >/dev/null 2>&1 || true
git --git-dir "$storage" cat-file -e "$fix^{commit}" 2>/dev/null || refuse "commit $fix not on this node" 5
me=$(rad self --did); me=${me#did:key:}
mine=$(git --git-dir "$storage" rev-parse --verify -q "refs/namespaces/$me/refs/heads/main" || true)
# No main yet: a new seat publishes its first main at the head (#251, before it can be added as a delegate).
if [[ -n "$mine" ]]; then
  git --git-dir "$storage" merge-base --is-ancestor "$mine" "$fix" || refuse "$fix doesn't fast-forward main ($mine)" 4
fi

# 3. Push this delegate's main (git-remote-rad signs the refs with the node key and announces them).
cd "$repo_dir"
git fetch -q "$storage" "$fix" || refuse "can't copy $fix into the working copy" 5
git push -q rad "$fix:refs/heads/main" 2>&1 | grep -v '^$' >&2 || true
after=$(git --git-dir "$storage" rev-parse "refs/namespaces/$me/refs/heads/main")
[[ "$after" == "$fix" ]] || refuse "push didn't land: main is $after" 6
echo "gate: pushed main = $fix (Heads.head matches, fast-forward)"
