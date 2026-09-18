"""make_scene_geometry_nullable_before_ingest

Revision ID: c4532e60526b
Revises: e757afab871d
Created: 2026-09-18 07:01:19.431916+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4532e60526b'
down_revision: str | None = 'e757afab871d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('scenes', 'footprint', nullable=True)
    op.alter_column('scenes', 'centroid', nullable=True)
    op.create_check_constraint(
        'ready_scene_has_geometry',
        'scenes',
        "processing_state != 'ready' OR (footprint IS NOT NULL AND centroid IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint('ready_scene_has_geometry', 'scenes', type_='check')
    op.alter_column('scenes', 'centroid', nullable=False)
    op.alter_column('scenes', 'footprint', nullable=False)

