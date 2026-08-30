"""Cross-cutting infrastructure with no domain knowledge in it: logging, typed errors, wire envelopes.

what  : Adapters and primitives that everything above may import - `logger`, `exceptions`, `responses`, and
        later the clients for Postgres, object storage, the tiler and the queue.
where : One level above `constants/` in the dependency direction `routes/cli -> controllers -> services ->
        domain -> lib -> constants`. Nothing here imports from `services/`, `controllers/` or `routes/`.
how   : `lib/` wraps things we did not write. A module belongs here when it exists to make a library or a
        protocol usable from this codebase; it belongs in `services/` when it exists to make a decision about
        satellite imagery.
"""
