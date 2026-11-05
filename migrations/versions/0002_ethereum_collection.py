"""V0.2.0 : pièces de transactions Ethereum et métadonnées d'actifs figées."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("transaction_bundles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chain_id", sa.String(64), sa.ForeignKey("chains.id"), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=False),
        sa.Column("block_number", sa.Numeric(20, 0), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=False),
        sa.Column("transaction_status", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("source_snapshots.id"), nullable=False),
        sa.Column("normalization_limits", sa.JSON(), nullable=False),
        sa.UniqueConstraint("chain_id", "block_hash", "tx_hash"),
        sa.CheckConstraint("transaction_status IN (0, 1)", name="bundle_transaction_status"))
    op.create_index("ix_transaction_bundles_tx_hash", "transaction_bundles", ["tx_hash"])
    op.add_column("observations", sa.Column("bundle_id", sa.String(36), nullable=True))
    op.add_column("observations", sa.Column("asset_metadata", sa.JSON(), nullable=True))
    op.create_foreign_key("fk_observations_bundle_id", "observations", "transaction_bundles", ["bundle_id"], ["id"])
    op.create_table("run_bundles",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), primary_key=True),
        sa.Column("bundle_id", sa.String(36), sa.ForeignKey("transaction_bundles.id"), primary_key=True))


def downgrade():
    op.drop_table("run_bundles")
    op.drop_constraint("fk_observations_bundle_id", "observations", type_="foreignkey")
    op.drop_column("observations", "asset_metadata")
    op.drop_column("observations", "bundle_id")
    op.drop_index("ix_transaction_bundles_tx_hash", table_name="transaction_bundles")
    op.drop_table("transaction_bundles")
