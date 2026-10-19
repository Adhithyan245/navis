"""
Navis multi-agent layer.

Every user-facing function is owned by one agent (see catalog.py). The
supervisor (supervisor.py) routes each request, runs the chosen agents and
streams their results using the runtime's public wire contract.
"""
