# exchange: the drawn judges' convenience relay (proof-of-fix#117)

A small HTTP service (standard library only) where the judges drawn for a check post their seals, reveals and
signatures when they share no folder. It checks every message against the chain (drawn, not recused, signed by the
seat key; a reveal against its seal; deadlines from the seal and reveal windows) and holds no key: it can withhold,
never forge. It is optional, never a required dependency (ADR 0003, #121): the node's transport is pluggable
(`oracle/transport.py`) and the target primary path is on-chain seals (#122, task 5.5).

Design, trust model, limits, API and hosting on the devnet (live, behind the same API keys as the chain): [`docs/exchange.md`](../docs/exchange.md).

```
EXCHANGE_RPC=http://127.0.0.1:8546 EXCHANGE_RACE=0x… python3 -m exchange
python3 -m unittest discover -s tests -p test_exchange.py
```
