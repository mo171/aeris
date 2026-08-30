"""Every fixed vocabulary the backend speaks, in one place, so no literal string is typed twice.

what  : One module per vocabulary. Values that appear on the wire are `StrEnum`s, so Pydantic validates
        them at the boundary and serialises them as the exact strings the frontend expects.
where : The bottom of the dependency direction - `routes/cli -> controllers -> services -> domain -> lib ->
        constants`. Nothing here imports anything from the application, which is what makes it safe for
        everything to import from here.
how   : Most of these vocabularies are **transcribed, not designed**. They are already shipped in
        `frontend/lib/constants/` and `frontend/features/*/schemas/*.schema.ts`, and `api-contract.md` §7
        states the backend may not invent them. Where a value here disagrees with the frontend, the frontend
        is right and this is a bug - Phase 0.7 turns that into a failing contract test rather than a Phase 2
        surprise.

        A vocabulary is added here when something reads it. Absent so far, deliberately: the ~60 interface
        command ids (mirrored when the `ui-command` event is first emitted - a mirror written months early is
        a mirror that has already drifted), the named colour ramps and their domains (Phase 1.2.1, where the
        renderer establishes what it actually draws), and the per-model capability mapping (Phase 1.6/1.7,
        where the fleet becomes real).
"""
