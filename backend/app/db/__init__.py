"""SQLAlchemy persistence: the declarative models, and the identifiers every row is keyed by.

what  : The `app.db` package. Re-exports nothing - import from `app.db.models` or `app.db.identifiers`
        directly so that an import line says which of the two it needs.
where : Depended on by services through repositories. Carries no business logic (`architecture-context.md`
        §5): a model is a persistence shape, and a rule about what a value means belongs in the service that
        writes it or in a CHECK constraint that cannot be bypassed.
"""
