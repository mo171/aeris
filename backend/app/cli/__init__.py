"""The Phase 1 adapter. A sibling of the future `app/routes/`, and never imported by it.

what  : The Typer application and its commands. `doctor` today; `dataset`, `ingest`, `analyse`,
        `investigate` and `voice` arrive with the Phase 1 sub-phases that build them.
where : The outermost layer. It calls services and never the reverse, exactly as `routes/` will in Phase 2 -
        which is what makes Phase 2 additive rather than a rewrite (`folder-archtecture.md` rule 1).
how   : `asyncio.run()` is called in `main.py` and nowhere else in `app/`. Every command's real work is an
        `async def` in its own module, so the same function is callable from a route later without touching
        the loop (`code-standards.md` §7).
"""
