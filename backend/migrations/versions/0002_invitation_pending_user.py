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

"""Link invited registrations until their email verification completes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_invitation_pending_user"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if "invitations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("invitations")}
    if "pending_user_id" not in columns:
        op.add_column("invitations", sa.Column("pending_user_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_invitations_pending_user", "invitations", "users", ["pending_user_id"], ["id"], ondelete="SET NULL")
        op.create_index("ix_invitations_pending_user_id", "invitations", ["pending_user_id"])


def downgrade():
    # Keep invitation ownership metadata to avoid deleting pending/user data.
    pass
