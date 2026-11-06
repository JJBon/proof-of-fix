"""rpc, shared with the oracle node: it lives in oracle/rpc.py (the node image carries oracle/ only)."""

from oracle.rpc import *  # noqa: F401,F403
from oracle.rpc import _reason  # noqa: F401  (tests read reverts through it)
