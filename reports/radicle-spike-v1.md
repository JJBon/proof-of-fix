# Radicle spike v1: can the judges merge by threshold, gated by the head on-chain?

proof-of-fix#190. Run on 2026-11-09, on one machine, in Docker, on an internal network with no route out. Nothing touched Radicle's public network, a public chain or AWS. Simulated money only.

## The answer

**Yes, with one condition: where the delegate keys live.** Radicle 1.10.3 computes the canonical `main` from the delegates' signed branches and the threshold, and nothing else. With the three judges' node keys as the delegates and threshold 2:

1. **The judges can merge by threshold.** The head moved on-chain (`Heads.move`), then each judge's gate read `Heads.head(repo)`, found the fix, and pushed. After one push the canonical `main` stayed at genesis; after the second it was the fix on all four nodes and in a fresh clone, equal to `Heads.head(repo)`. The outsider's patch turned "merged" at the second push too.
2. **A random person can't get code into `main` without the judges.** The outsider's patch and its own `main` (pushed to an unjudged commit) changed nothing; nor did one delegate pushing alone, or two delegates pushing different things alone. Fresh clones got the judged head.
3. **"Only accept merges from the enclaves" works only if the keys are in the enclaves.** The gate refused every commit that wasn't the head on-chain, and a commit that didn't fast-forward. But Radicle doesn't know about the gate: two delegates who skip it **do** move `main` (control scenario G), and two delegates can change the delegate set. So the gate must run where the key is, and the key must not be extractable (#94). The enclave must also refuse identity updates that don't match the seats on-chain.
4. **The validator's code and checker image can live on Radicle** (analysis below): the source as a public repository whose head is in `Heads`; the image built reproducibly, its digest on-chain, the blob off git.

## What was run

- **Radicle:** heartwood **1.10.3** (2026-09-08, commit `7e1cb406bb935c3de008d2171e8961f57b4336ea`), the x86_64 musl static build `radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz` from `files.radicle.dev/releases/1.10.3/`. **SHA-256 `3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751`**, checked by the Dockerfile's `ADD --checksum` and equal to the release's own `.sha256` file. It's the latest release. No major release has shipped since the September disclosure, so it doesn't have the fix #92 waits for; that doesn't matter for a local network with a public repository.
- **Chain:** anvil and cast from the pinned Foundry v1.8.5 image, and the real `contracts/src/v2/Heads.sol` (solc 0.8.37). Repo id = `keccak256(RID)`, genesis head = the repository's initial commit (SHA-1 left-aligned in bytes32), mover = anvil's second dev account, standing in for `RaceV2.merged()`. `Heads` only checks that its `Verdicts` has code, so a 1-byte stub contract stands in.
- **Nodes:** `judge1`, `judge2`, `judge3` (the delegates, threshold 2) and `outsider`, plus a new `viewer` node for each fresh-clone check. Each has a throwaway key made in its container, never printed. The repository: one file with a bug (`add` returns `a - b`); the fix corrects it.
- **The gate** (`spikes/radicle/gate.sh`, plain code in the judge's container): reads `Heads.head(repo)` with `cast call`, refuses (exit 3) unless the fix equals it, refuses (exit 4) unless it fast-forwards this delegate's own signed `main`, then `git push rad <fix>:refs/heads/main`.
- **One entry point:** `scripts/radicle-spike.sh` builds the image, runs every scenario, prints pass/fail and removes its containers and network. A run takes about 33 seconds after the first image build. The final version passed 3 runs in a row from a clean state, and left no container or network behind. Two earlier drafts failed on bugs in the script itself, not in Radicle.

## Scenario results

| | Scenario | What happened | Result |
|---|---|---|---|
| A | Setup | judge1 ran `rad init`; judge2 and judge3 cloned and pushed their `main`; judge1 ran `rad id update --delegate <judge2> --delegate <judge3> --threshold 2`. All four nodes show 3 delegates, threshold 2. `Heads` deployed, `head(repo)` = genesis = canonical `main` on every node. | pass |
| B | Judges merge | The outsider opened a patch (`git push rad HEAD:refs/patches`). The mover called `Heads.move(repo, genesis, fix, ...)`. judge1's gate pushed: canonical `main` stayed genesis on all nodes, patch "open". judge2's gate pushed: `rad` printed "Canonical reference refs/heads/main updated to target commit <fix>"; canonical `main` = fix on all nodes and in a fresh clone, = `Heads.head(repo)`; patch "merged". | pass |
| E | Gate refuses | judge3 asked to push the old head (genesis, stale): exit 3. An unjudged commit: exit 3. Not a SHA-1: exit 2. judge3's `main` unchanged; canonical unchanged. judge3 then caught up through its gate. | pass |
| D | Outsider | The outsider force-pushed its own `main` to the unjudged commit and opened a patch with it. Its namespace replicated to every node, and the patch is listed, but canonical `main` stayed the fix everywhere, and a fresh clone got the fix. | pass |
| C | One delegate alone | judge1 bypassed its gate and pushed a rogue commit on top of the fix: canonical unchanged. judge3, also alone, force-pushed a commit that diverges from the fix: canonical still the fix. After a second fix was judged on-chain, judge1's gate refused it: exit 4, its rogue `main` doesn't fast-forward to it. | pass |
| F | Delegate set, one delegate | judge2 ran `rad id update --rescind <judge3> --threshold 1`: an *active* revision, not accepted. Every node still has 3 delegates, threshold 2. | pass |
| G | Control: two delegates skip the gate | judge2 pushed the same rogue commit as judge1: canonical `main` = the rogue commit on every node, while `Heads.head(repo)` = the second judged fix. Then judge1 accepted F's revision: the identity became 2 delegates, threshold 1. Expected: Radicle enforces the threshold, nothing more. | pass (as expected) |
| I | Isolation | See below. | pass |

## Radicle's canonical-branch rules (1.10.3) compared with the issue

The issue's description holds: the identity document lists delegates and a threshold, the canonical `main` is what `threshold` delegates' signed `main` branches agree on, and identity changes need the threshold. What we observed adds these details:

1. **"Agree" means by ancestry, not the same tip.** A delegate's `main` counts for its tip and all its ancestors; the canonical `main` is the newest commit with at least `threshold` votes. In C, judge1 was on a rogue child of the fix, judge2 on the fix, judge3 on a commit diverging from it: three different tips, and the canonical `main` was the fix (judge1 + judge2). Under a same-tip rule there would have been no quorum. For us: a delegate that runs ahead still counts for the judged head. It doesn't let anyone move `main` past it.
2. **The default branch's rule can't be set separately.** Its delegates and threshold are the identity's own. `xyz.radicle.crefs` rules (allow `delegates` or a list of DIDs, plus a threshold) apply to other refs, such as `refs/tags/*`. A crefs rule for `refs/heads/main` is refused: "incompatible payloads: The rule(s) xyz.radicle.crefs.rules.["refs/heads/main"] matches the value of xyz.radicle.project.defaultBranch". So on Radicle the merge quorum and the quorum for changing the seats are **the same number**. The contract can't ask for 2 of 3 to merge and 3 of 3 to change the seats.
3. **A delegate must have published the default branch before it can be added.** Without that, `rad id update` refused: "the threshold of 2 delegates cannot be met ... the delegate did:key:... is missing". A new judge seat's node must push `main` (at the current head) first.
4. **The canonical ref is computed by each node** from the signed refs it has fetched (stored as `refs/heads/main` in the node's storage). There's no global value: a node that hasn't fetched lags. After `rad sync --fetch`, all nodes and fresh clones agreed in every scenario.
5. **Patches:** each delegate's push containing the patch's head records a "merged" action by that delegate. The patch's status becomes "merged" only at the threshold (open after 1 of 3, merged after 2 of 3).
6. **Radicle doesn't enforce fast-forward** on a delegate's own `main`: judge3's force-push of a diverging commit was accepted into its namespace. Fast-forward is the gate's rule only.

## Isolation evidence

- **The network:** created with `docker network create --internal`. `docker network inspect` reports `Internal: true`. Every node container's `/proc/net/route` has no default route, only the spike's subnet.
- **Node config:** Radicle's `test` network, which has no bootstrap nodes; every node logged "0 nodes added to address book". Also: `preferredSeeds: []`, `peers: static`, `connect: []`, no external addresses. Peers were connected explicitly with `rad node connect <nid>@<container>:8776`. (On the `main` network, an earlier trial run logged "4 nodes added to address book" from the built-in bootstrap list. It never dialled them, but we switched to `test` so that none are known at all.)
- **Logs:** the script keeps each node's debug log in `.radicle-spike/`. In each of the six nodes' logs:
  - every connection line (`Connecting to`, `Attempted connection to`, `Connected to`) names a spike container or an address in the spike's subnet;
  - no IP address appears outside the subnet (besides `0.0.0.0`, the listen address);
  - no public Radicle hostname appears (`radicle.xyz`, `.garden`, `.dev`, `.network`, `seed.radicle`, `iris.`, `rosa.`).
- **The only download** was the release tarball, at image build time, from `files.radicle.dev`. It's a static file server, not the peer-to-peer network: no node ran, and no key existed then.

## Proven and assumed

- **Proven here:** threshold merge; nothing changes below the threshold, whether outsider, one delegate, or two lone delegates disagreeing; the gate refuses stale, unjudged and non-fast-forward commits; one delegate can't change the delegate set; the rules above. Each check ran on all four nodes. Fresh clones were checked in B and D.
- **Assumed:**
  - **The release's SSH signature (`.sig`) wasn't verified** against Radicle's release key; we checked the SHA-256 only. It came from the same server, so it proves integrity, not origin.
  - **Behaviour across many nodes, slow links or partitions** wasn't tested; four nodes on one host is small.
  - **`RaceV2.merged()` didn't call `move`;** an unlocked dev account did.
  - **Contract behaviour** (e.g. `StaleVerdict`) is covered by the forge tests, not here.

## Limits

- **The keys aren't in an enclave** (#94). They sit on disk in each container, so whoever runs two judge nodes can skip both gates and move `main` (scenario G) or change the delegates. Until the keys are in an enclave, the spike shows the mechanism, not the protection.
- **v3's per-draw judges can't be delegates.** The delegates are a fixed set in the identity document, changed only by a threshold of the current delegates. A judge panel drawn per bounty would need an identity update per draw. That's slow, it needs the previous panel's signatures, and a new delegate must have published `main` first. The delegates fit fixed seats (v2's), or a fixed set of signers that act on any quorum verdict on-chain.
- **Public repositories only on the real network,** until Radicle's fix for the September flaws ships and is checked (#92).
- **The chain and Radicle can disagree** (G): Radicle has no check against `Heads`. Mirrors and fresh clones that must follow the chain need their own check (#85 S1, 5.9): compare the canonical `main` with `Heads.head(repo)` and alert on a difference.

## Question 4: the validator's code and checker image on Radicle (analysis only)

- **Source in git:** the node's code, the checker's Dockerfile and its lockfiles as a public Radicle repository, registered in `Heads` like any target. Fixes to the validator then go through the same race and the same threshold merge, so proof-of-fix heals its own code (#85).
- **A reproducible build:** pinned base image by digest, lockfiles, fixed timestamps (`SOURCE_DATE_EPOCH`), no network during the build. Anyone who rebuilds the head commit gets the same digest.
- **The digest on-chain:** the accepted image digests in the constitution, changed by ADR (#124, ADR 0003). A judge runs only an image whose digest is listed and whose source commit is a `Heads` head.
- **The blob off git:** published to several registries and IPFS, addressed by the digest. Radicle carries the source, not the image.
- **Needed, not built here:** the reproducible build itself, a digest-to-commit record (the image's labels plus an on-chain entry), and the enclave measuring the image it runs (#94).

## Follow-up

Wire this into #189's integration suite: `RaceV2.merged()` calls `Heads.move`, and a Radicle adapter (fetch a patch, run the judges, gate the delegate push) replaces the forge's `merged: true` flag in `oracle/node_v2.py`. Add a check that compares each mirror's canonical `main` with `Heads.head(repo)`, and run #190's negative cases in the suite too. This needs its own issue, linked from #190.
