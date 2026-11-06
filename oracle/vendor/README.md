# Vendored Python libraries

The oracle node's cryptography, copied from pinned upstream releases so nothing is fetched at run or check time
(proof-of-fix#94). Don't edit these files: `scripts/check.sh` checks them against `SHA256SUMS`, and
`scripts/oracle-vendor.sh` re-creates them, checking each download against the hash pinned in the script first.

Pure Python only: the required check `pof / check` runs on the CI test runner's Python 3.9, with no pip and no network.

| Library | Release | Pinned by | License | What's copied | Used for |
|---|---|---|---|---|---|
| [python-ecdsa](https://github.com/tlsfuzzer/python-ecdsa) | 0.19.2 | the PyPI wheel's sha256 `840f5dc5…7399` | MIT (`licenses/ecdsa-LICENSE`) | the package's modules, without its `test_*.py` | secp256k1 signing, RFC 6979 nonces, low-s encoding, public-key recovery |
| [six](https://github.com/benjaminp/six) | 1.17.0 | the PyPI wheel's sha256 `4721f391…3274` | MIT (`licenses/six-LICENSE`) | `six.py` | python-ecdsa's only dependency |
| [XKCP CompactFIPS202](https://github.com/XKCP/XKCP/tree/712fabccd5d611459533d554814e00537742624c/Standalone/CompactFIPS202/Python) | commit `712fabcc` | the file's sha256 `0b731097…204f` | CC0 (header of the file) | `keccak/CompactFIPS202.py` | Keccak-256: the Keccak team's reference implementation (Gilles Van Assche) |

`oracle/crypto.py` puts this directory first on `sys.path`, and keeps only Ethereum's glue: the address, `v`, and the
EIP-712 struct encoding. Tests pin signatures made by `cast` (alloy, an independent implementation): a raw digest and a
full EIP-712 `Result` with its `Fee[]` array. The contract accepting the node's signatures is the end-to-end check
(`scripts/oracle-run.sh`).

**Caveat:** python-ecdsa is pure Python and not constant-time. That's acceptable for devnet keys. For real keys, a
node should sign inside its enclave (dstack, #94 phase 2), so nothing outside the confidential VM can time it.
