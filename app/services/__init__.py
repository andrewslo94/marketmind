"""
app/services/ — the "business logic" layer.

Services fetch external data, cache it, and do calculations. Routes call
services; services never render templates, and routes never call external
APIs directly. This split keeps each piece small and testable, and means a
data provider can be swapped by editing one service file.
"""
