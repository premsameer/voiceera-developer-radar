"""V2D contributor pipeline, GitHub deliveries, events and alerts."""
from alembic import op
import sqlalchemy as sa

revision="0003"; down_revision="0002"; branch_labels=None; depends_on=None


def upgrade():
    inspector=sa.inspect(op.get_bind())
    developer_columns={column["name"] for column in inspector.get_columns("developers")}
    if "github_user_id" in developer_columns and "contributor_pipeline" in inspector.get_table_names(): return
    with op.batch_alter_table("developers") as batch:
        batch.add_column(sa.Column("github_user_id",sa.Integer(),nullable=True))
        batch.create_unique_constraint("uq_developers_github_user_id",["github_user_id"])
        batch.create_index("ix_developers_github_user_id",["github_user_id"])
    op.create_table("github_webhook_deliveries",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("delivery_id",sa.String(100),nullable=False),
        sa.Column("event_name",sa.String(60),nullable=False),sa.Column("action",sa.String(60)),
        sa.Column("received_at",sa.DateTime(timezone=True),nullable=False),sa.Column("processed_at",sa.DateTime(timezone=True)),
        sa.Column("status",sa.String(20),nullable=False),sa.Column("error",sa.Text()),sa.UniqueConstraint("delivery_id"))
    op.create_index("ix_github_webhook_deliveries_delivery_id","github_webhook_deliveries",["delivery_id"])
    op.create_table("contributor_events",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("source",sa.String(30),nullable=False),sa.Column("external_id",sa.String(220),nullable=False),
        sa.Column("event_type",sa.String(60),nullable=False),sa.Column("action",sa.String(60)),sa.Column("actor_github_id",sa.Integer()),sa.Column("actor_login",sa.String(100)),
        sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="SET NULL")),sa.Column("repository_full_name",sa.String(220),nullable=False),
        sa.Column("repository_scope",sa.String(20),nullable=False),sa.Column("fork_full_name",sa.String(220)),sa.Column("pull_request_number",sa.Integer()),
        sa.Column("canonical_url",sa.String()),sa.Column("title",sa.Text()),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("attribution",sa.String(30),nullable=False),sa.Column("attribution_evidence",sa.Text()),sa.Column("meaningful",sa.Boolean(),nullable=False),
        sa.Column("raw_metadata_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("source","external_id"))
    for column in ["event_type","actor_github_id","actor_login","developer_id","repository_full_name","fork_full_name","pull_request_number","occurred_at","attribution"]:
        op.create_index(f"ix_contributor_events_{column}","contributor_events",[column])
    op.create_table("contributor_pipeline",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE"),nullable=False,unique=True),
        sa.Column("stage",sa.String(40),nullable=False),sa.Column("attribution",sa.String(30),nullable=False),sa.Column("first_event_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("latest_event_at",sa.DateTime(timezone=True),nullable=False),sa.Column("upstream_repository",sa.String(220)),sa.Column("fork_repository",sa.String(220)),
        sa.Column("pull_request_number",sa.Integer()),sa.Column("last_meaningful_activity_at",sa.DateTime(timezone=True)),sa.Column("checks_state",sa.String(30)),
        sa.Column("stalled_since",sa.DateTime(timezone=True)),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    for column in ["developer_id","stage","attribution","latest_event_at"]: op.create_index(f"ix_contributor_pipeline_{column}","contributor_pipeline",[column])
    op.create_table("maintainer_alerts",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE")),
        sa.Column("contributor_event_id",sa.Integer(),sa.ForeignKey("contributor_events.id",ondelete="CASCADE")),sa.Column("alert_type",sa.String(40),nullable=False),
        sa.Column("severity",sa.String(20),nullable=False),sa.Column("message",sa.Text(),nullable=False),sa.Column("status",sa.String(20),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("resolved_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("alert_type","contributor_event_id"))
    for column in ["developer_id","alert_type","status"]: op.create_index(f"ix_maintainer_alerts_{column}","maintainer_alerts",[column])


def downgrade():
    op.drop_table("maintainer_alerts"); op.drop_table("contributor_pipeline"); op.drop_table("contributor_events"); op.drop_table("github_webhook_deliveries")
    with op.batch_alter_table("developers") as batch:
        batch.drop_index("ix_developers_github_user_id"); batch.drop_constraint("uq_developers_github_user_id",type_="unique"); batch.drop_column("github_user_id")
