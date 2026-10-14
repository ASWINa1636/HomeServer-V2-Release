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

"""Add delivery_status and delivery_error to invitations table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_invitation_delivery"
down_revision = "0004_storage_host_paths"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "invitations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("invitations")}

    if "delivery_status" not in columns:
        op.add_column(
            "invitations",
            sa.Column("delivery_status", sa.String(32), server_default="sent", nullable=False),
        )

    if "delivery_error" not in columns:
        op.add_column(
            "invitations",
            sa.Column("delivery_error", sa.String(256), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "invitations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("invitations")}

    if "delivery_error" in columns:
        op.drop_column("invitations", "delivery_error")
    if "delivery_status" in columns:
        op.drop_column("invitations", "delivery_status")
