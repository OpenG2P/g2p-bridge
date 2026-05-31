#!/usr/bin/env python3

# ruff: noqa: I001

from openg2p_example_bank_api.app import Initializer
from openg2p_fastapi_common.ping import PingInitializer

initializer = Initializer()
PingInitializer()

app = initializer.return_app()

if __name__ == "__main__":
    initializer.main()
