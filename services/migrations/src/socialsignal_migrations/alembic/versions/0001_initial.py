"""Initial schema and per-role grants.

Tables are owned by the migrator role, which runs this migration. The two
application roles get only the privileges their zone needs (D1):
  ingestor  (ingest zone)   reads subscriptions, adds posts and their links.
  analysis  (analysis zone) manages subscriptions, reads posts, classifies
                            each post once (A9) and writes summaries (A3).

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        # Normalised by the API: handle without "@", hashtag without "#",
        # both lower-case.
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('handle', 'hashtag')", name="subscriptions_kind"),
        sa.UniqueConstraint("kind", "value", name="subscriptions_kind_value"),
    )

    op.create_table(
        "posts",
        # at:// URI: the natural key, so re-ingesting a post is a no-op (D5).
        sa.Column("uri", sa.Text, primary_key=True),
        sa.Column("cid", sa.Text, nullable=False),
        sa.Column("author_did", sa.Text, nullable=False),
        sa.Column("author_handle", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("posts_created_at", "posts", ["created_at"])

    # A post can match several subscriptions (its author and a hashtag).
    op.create_table(
        "subscription_posts",
        sa.Column(
            "subscription_id",
            sa.BigInteger,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "post_uri",
            sa.Text,
            sa.ForeignKey("posts.uri", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("subscription_posts_post_uri", "subscription_posts", ["post_uri"])

    # Each post is classified once (A9); only the analysis zone writes here.
    op.create_table(
        "post_sentiments",
        sa.Column(
            "post_uri",
            sa.Text,
            sa.ForeignKey("posts.uri", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "label IN ('positive', 'neutral', 'negative')", name="post_sentiments_label"
        ),
    )

    # Precomputed by the worker, read by the API (A3). One row per subscription.
    op.create_table(
        "summaries",
        sa.Column(
            "subscription_id",
            sa.BigInteger,
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dominant_label", sa.Text),
        sa.Column("positive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("neutral_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        # NULL when the LLM could not write the sentence (degraded mode, A3).
        sa.Column("summary_text", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dominant_label IS NULL OR dominant_label IN ('positive', 'neutral', 'negative')",
            name="summaries_dominant_label",
        ),
        sa.CheckConstraint(
            "positive_count >= 0 AND neutral_count >= 0 AND negative_count >= 0"
            " AND item_count = positive_count + neutral_count + negative_count",
            name="summaries_counts",
        ),
    )

    # Least privilege per zone (D1). Nothing is granted to PUBLIC.
    op.execute("GRANT SELECT ON subscriptions TO ingestor")
    op.execute("GRANT INSERT ON posts, subscription_posts TO ingestor")

    op.execute("GRANT SELECT, INSERT, DELETE ON subscriptions TO analysis")
    op.execute("GRANT SELECT ON posts, subscription_posts TO analysis")
    op.execute("GRANT SELECT, INSERT, UPDATE ON post_sentiments TO analysis")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON summaries TO analysis")


def downgrade() -> None:
    for table in ("summaries", "post_sentiments", "subscription_posts", "posts", "subscriptions"):
        op.drop_table(table)
