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

"""Add host_path, mount_status, and mount_type to storage_locations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_storage_host_paths"
down_revision = "0003_storage_locations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storage_locations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("storage_locations")}

    if "host_path" not in columns:
        op.add_column("storage_locations", sa.Column("host_path", sa.String(512), nullable=True))

    if "mount_status" not in columns:
        op.add_column(
            "storage_locations",
            sa.Column("mount_status", sa.String(40), server_default="mounted_and_writable", nullable=False),
        )

    if "mount_type" not in columns:
        op.add_column(
            "storage_locations",
            sa.Column("mount_type", sa.String(40), server_default="container_volume", nullable=False),
        )

    # Populate host_path for the default Primary storage row
    bind.execute(
        sa.text(
            "UPDATE storage_locations SET host_path = './data', mount_type = 'host_bind_mount' "
            "WHERE root_key = 'default' AND (host_path IS NULL OR host_path = '')"
        )
    )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storage_locations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("storage_locations")}
    if "host_path" in columns:
        op.drop_column("storage_locations", "host_path")
    if "mount_status" in columns:
        op.drop_column("storage_locations", "mount_status")
    if "mount_type" in columns:
        op.drop_column("storage_locations", "mount_type")
