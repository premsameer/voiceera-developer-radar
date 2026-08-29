"""V2A segmentation and V2B engagement intelligence."""
from alembic import op
import sqlalchemy as sa

revision="0002"; down_revision="0001"; branch_labels=None; depends_on=None


def upgrade():
    with op.batch_alter_table("developers") as batch:
        batch.add_column(sa.Column("primary_segment_code",sa.String(),nullable=False,server_default="UNKNOWN_DEVELOPER"))
        batch.add_column(sa.Column("intent_strength",sa.Integer(),nullable=False,server_default="0"))
        batch.add_column(sa.Column("current_funnel_stage",sa.String(),nullable=False,server_default="DISCOVERED"))
        batch.add_column(sa.Column("next_best_action",sa.String(),nullable=False,server_default="MONITOR"))
        batch.add_column(sa.Column("next_action_reason",sa.Text(),nullable=True))
    with op.batch_alter_table("signals") as batch:
        batch.add_column(sa.Column("intent_strength_base",sa.Integer(),nullable=False,server_default="0"))
        batch.add_column(sa.Column("intent_strength_final",sa.Integer(),nullable=False,server_default="0"))
    op.create_table("organizations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("name",sa.String(200),nullable=False),sa.Column("canonical_domain",sa.String(200),unique=True),sa.Column("github_org",sa.String(100),unique=True),sa.Column("profile_url",sa.String()),sa.Column("organization_type",sa.String(),nullable=False,server_default="UNKNOWN"),sa.Column("metadata_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("campaigns",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("name",sa.String(),nullable=False),sa.Column("segment_code",sa.String()),sa.Column("source",sa.String()),sa.Column("route",sa.String()),sa.Column("tracking_code",sa.String(80),nullable=False,unique=True),sa.Column("destination_url",sa.String(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    with op.batch_alter_table("review_actions") as batch:
        batch.add_column(sa.Column("campaign_id",sa.Integer(),sa.ForeignKey("campaigns.id",name="fk_review_actions_campaign_id"),nullable=True))
        batch.add_column(sa.Column("outcome_status",sa.String(),nullable=True))
    op.create_table("developer_segments",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE"),nullable=False),sa.Column("segment_code",sa.String(50),nullable=False),sa.Column("is_primary",sa.Boolean(),nullable=False),sa.Column("confidence",sa.Float(),nullable=False),sa.Column("evidence_signal_id",sa.Integer(),sa.ForeignKey("signals.id",ondelete="SET NULL")),sa.Column("classifier_version",sa.String(),nullable=False),sa.Column("manual_override",sa.Boolean(),nullable=False),sa.Column("override_reason",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("developer_id","segment_code","manual_override"))
    op.create_index("ix_developer_segments_developer_id","developer_segments",["developer_id"])
    op.create_table("developer_technologies",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE"),nullable=False),sa.Column("technology_type",sa.String(50),nullable=False),sa.Column("technology_name",sa.String(100),nullable=False),sa.Column("evidence_signal_id",sa.Integer(),sa.ForeignKey("signals.id",ondelete="CASCADE"),nullable=False),sa.Column("confidence",sa.Float(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("developer_id","technology_type","technology_name","evidence_signal_id"))
    op.create_index("ix_developer_technologies_developer_id","developer_technologies",["developer_id"])
    op.create_table("developer_organizations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE"),nullable=False),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("relationship_type",sa.String(50),nullable=False),sa.Column("evidence_url",sa.String(),nullable=False),sa.Column("valid_from",sa.DateTime(timezone=True)),sa.Column("valid_to",sa.DateTime(timezone=True)),sa.Column("manually_verified",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("developer_id","organization_id","relationship_type"))
    op.create_index("ix_developer_organizations_developer_id","developer_organizations",["developer_id"])
    op.create_table("message_versions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("review_action_id",sa.Integer(),sa.ForeignKey("review_actions.id",ondelete="SET NULL")),sa.Column("campaign_id",sa.Integer(),sa.ForeignKey("campaigns.id",ondelete="SET NULL")),sa.Column("template_version",sa.String(),nullable=False),sa.Column("generated_text",sa.Text(),nullable=False),sa.Column("final_text",sa.Text()),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("sent_at",sa.DateTime(timezone=True)),sa.Column("channel",sa.String()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("engagement_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("developer_id",sa.Integer(),sa.ForeignKey("developers.id",ondelete="CASCADE")),sa.Column("event_type",sa.String(50),nullable=False),sa.Column("event_at",sa.DateTime(timezone=True),nullable=False),sa.Column("evidence_level",sa.String(30),nullable=False),sa.Column("source",sa.String(30),nullable=False),sa.Column("campaign_id",sa.Integer(),sa.ForeignKey("campaigns.id",ondelete="SET NULL")),sa.Column("message_id",sa.Integer(),sa.ForeignKey("message_versions.id",ondelete="SET NULL")),sa.Column("metadata_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_engagement_events_developer_id","engagement_events",["developer_id"])


def downgrade():
    op.drop_table("engagement_events"); op.drop_table("message_versions"); op.drop_table("developer_organizations"); op.drop_table("developer_technologies"); op.drop_table("developer_segments")
    with op.batch_alter_table("review_actions") as batch: batch.drop_column("outcome_status"); batch.drop_column("campaign_id")
    op.drop_table("campaigns"); op.drop_table("organizations")
    with op.batch_alter_table("signals") as batch: batch.drop_column("intent_strength_final"); batch.drop_column("intent_strength_base")
    with op.batch_alter_table("developers") as batch:
        batch.drop_column("next_action_reason"); batch.drop_column("next_best_action"); batch.drop_column("current_funnel_stage"); batch.drop_column("intent_strength"); batch.drop_column("primary_segment_code")
