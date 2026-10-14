# Copyright 2026 Aswin A
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Enhance storage_locations to support system-wide authorized roots and default selection."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from datetime import datetime, timezone

revision = "0003_storage_locations"
down_revision = "0002_invitation_pending_user"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storage_locations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("storage_locations")}

    # Make workspace_id nullable for system-wide storage roots
    op.alter_column("storage_locations", "workspace_id", nullable=True)

    if "is_default" not in columns:
        op.add_column("storage_locations", sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False))

    if "target_path" not in columns:
        op.add_column("storage_locations", sa.Column("target_path", sa.String(512), server_default="", nullable=False))

    # Seed default storage location if none exists
    storage_table = sa.table(
        "storage_locations",
        sa.column("name", sa.String),
        sa.column("root_key", sa.String),
        sa.column("relative_path", sa.String),
        sa.column("target_path", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    res = bind.execute(sa.text("SELECT COUNT(*) FROM storage_locations")).scalar()
    if res == 0:
        bind.execute(
            storage_table.insert().values(
                name="Primary storage",
                root_key="default",
                relative_path="",
                target_path="/data",
                is_default=True,
                created_at=datetime.now(timezone.utc),
            )
        )


def downgrade():
    pass
