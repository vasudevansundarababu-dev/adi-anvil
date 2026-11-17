"""Explicit v2 module selection; no caller/environment activation or admission."""

import asyncio
import sys

from anvil_harbor.marketing import component_gate, opening_main

if __name__ == "__main__":
    component_gate()
    asyncio.run(opening_main(sys.argv[1]))
