"""Fondations V0.1 : identités, preuves, opérations, dossiers et runs.

Schéma figé, indépendant de l'évolution des modèles applicatifs.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('cases',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('chains',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('family', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('operations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('protocol', sa.String(length=100), nullable=True),
    sa.Column('decoder_version', sa.String(length=100), nullable=False),
    sa.Column('decoding_status', sa.String(length=32), nullable=False),
    sa.Column('evidence_refs', sa.JSON(), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('source_snapshots',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=False),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('coverage', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('addresses',
    sa.Column('id', sa.String(length=160), nullable=False),
    sa.Column('chain_id', sa.String(length=64), nullable=False),
    sa.Column('value', sa.LargeBinary(), nullable=False),
    sa.Column('display', sa.String(length=100), nullable=False),
    sa.CheckConstraint('length(value) = 20', name='address_evm_length'),
    sa.ForeignKeyConstraint(['chain_id'], ['chains.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chain_id', 'value'),
    sa.UniqueConstraint('id', 'chain_id')
    )
    op.create_table('analysis_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('case_id', sa.String(length=36), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('state', sa.String(length=32), nullable=False),
    sa.Column('coverage_status', sa.String(length=40), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('seeds_snapshot', sa.JSON(), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=False),
    sa.Column('block_bounds', sa.JSON(), nullable=False),
    sa.Column('allocation_policy', sa.String(length=100), nullable=False),
    sa.Column('decoder_versions', sa.JSON(), nullable=False),
    sa.Column('label_snapshot', sa.JSON(), nullable=False),
    sa.Column('coverage', sa.JSON(), nullable=False),
    sa.Column('stop_reasons', sa.JSON(), nullable=False),
    sa.Column('manifest', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'idempotency_key')
    )
    op.create_index(op.f('ix_analysis_runs_case_id'), 'analysis_runs', ['case_id'], unique=False)
    op.create_table('assets',
    sa.Column('id', sa.String(length=180), nullable=False),
    sa.Column('chain_id', sa.String(length=64), nullable=False),
    sa.Column('contract_address', sa.LargeBinary(), nullable=True),
    sa.Column('symbol', sa.String(length=64), nullable=True),
    sa.Column('decimals', sa.Integer(), nullable=True),
    sa.Column('metadata_source', sa.String(length=200), nullable=False),
    sa.CheckConstraint('decimals IS NULL OR (decimals >= 0 AND decimals <= 255)', name='asset_decimals'),
    sa.ForeignKeyConstraint(['chain_id'], ['chains.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'chain_id')
    )
    op.create_table('label_assertions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('subject_address_id', sa.String(length=160), nullable=False),
    sa.Column('predicate', sa.String(length=100), nullable=False),
    sa.Column('value', sa.String(length=500), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=False),
    sa.Column('evidence_ref', sa.String(length=200), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('method', sa.String(length=200), nullable=False),
    sa.Column('review_status', sa.String(length=40), nullable=False),
    sa.Column('version', sa.String(length=100), nullable=False),
    sa.Column('author', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['subject_address_id'], ['addresses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('observations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('chain_id', sa.String(length=64), nullable=False),
    sa.Column('block_number', sa.Numeric(precision=20, scale=0), nullable=False),
    sa.Column('block_hash', sa.String(length=66), nullable=False),
    sa.Column('parent_hash', sa.String(length=66), nullable=False),
    sa.Column('tx_hash', sa.String(length=66), nullable=False),
    sa.Column('transaction_index', sa.Integer(), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('position', sa.String(length=100), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('canonicality', sa.String(length=16), nullable=False),
    sa.Column('finality', sa.JSON(), nullable=False),
    sa.Column('source_address_id', sa.String(length=160), nullable=False),
    sa.Column('target_address_id', sa.String(length=160), nullable=False),
    sa.Column('asset_id', sa.String(length=180), nullable=False),
    sa.Column('amount_raw', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('snapshot_id', sa.String(length=36), nullable=False),
    sa.Column('evidence_ref', sa.String(length=200), nullable=False),
    sa.CheckConstraint("canonicality IN ('canonical', 'orphaned', 'unknown')", name='observation_canonicality'),
    sa.CheckConstraint("origin IN ('top_level', 'trace', 'log')", name='observation_origin'),
    sa.CheckConstraint('amount_raw >= 0 AND amount_raw <= 115792089237316195423570985008687907853269984665640564039457584007913129639935', name='observation_uint256'),
    sa.CheckConstraint('block_number >= 0 AND transaction_index >= 0', name='observation_order'),
    sa.ForeignKeyConstraint(['asset_id', 'chain_id'], ['assets.id', 'assets.chain_id'], ),
    sa.ForeignKeyConstraint(['chain_id'], ['chains.id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['source_snapshots.id'], ),
    sa.ForeignKeyConstraint(['source_address_id', 'chain_id'], ['addresses.id', 'addresses.chain_id'], ),
    sa.ForeignKeyConstraint(['target_address_id', 'chain_id'], ['addresses.id', 'addresses.chain_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chain_id', 'block_hash', 'tx_hash', 'origin', 'position'),
    sa.UniqueConstraint('id', 'chain_id')
    )
    op.create_index(op.f('ix_observations_chain_id'), 'observations', ['chain_id'], unique=False)
    op.create_index(op.f('ix_observations_tx_hash'), 'observations', ['tx_hash'], unique=False)
    op.create_table('run_operations',
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('operation_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ),
    sa.PrimaryKeyConstraint('run_id', 'operation_id')
    )
    op.create_table('allocations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('run_id', sa.String(length=36), nullable=False),
    sa.Column('observation_id', sa.String(length=36), nullable=False),
    sa.Column('amount_raw', sa.Numeric(precision=78, scale=0), nullable=False),
    sa.Column('policy_version', sa.String(length=100), nullable=False),
    sa.Column('rationale', sa.String(length=2000), nullable=False),
    sa.CheckConstraint('amount_raw >= 0 AND amount_raw <= 115792089237316195423570985008687907853269984665640564039457584007913129639935', name='allocation_uint256'),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'observation_id', 'policy_version')
    )
    op.create_table('case_seeds',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('case_id', sa.String(length=36), nullable=False),
    sa.Column('chain_id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('reference', sa.String(length=180), nullable=False),
    sa.Column('observation_id', sa.String(length=36), nullable=True),
    sa.Column('window', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
    sa.ForeignKeyConstraint(['chain_id'], ['chains.id'], ),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_seeds_case_id'), 'case_seeds', ['case_id'], unique=False)
    op.create_table('operation_movements',
    sa.Column('operation_id', sa.String(length=36), nullable=False),
    sa.Column('observation_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.CheckConstraint("role IN ('input', 'output', 'transfer', 'fee')", name='movement_role'),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], ),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ),
    sa.PrimaryKeyConstraint('operation_id', 'observation_id', 'role')
    )


def downgrade():
    op.drop_table('operation_movements')
    op.drop_index(op.f('ix_case_seeds_case_id'), table_name='case_seeds')
    op.drop_table('case_seeds')
    op.drop_table('allocations')
    op.drop_table('run_operations')
    op.drop_index(op.f('ix_observations_tx_hash'), table_name='observations')
    op.drop_index(op.f('ix_observations_chain_id'), table_name='observations')
    op.drop_table('observations')
    op.drop_table('label_assertions')
    op.drop_table('assets')
    op.drop_index(op.f('ix_analysis_runs_case_id'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
    op.drop_table('addresses')
    op.drop_table('source_snapshots')
    op.drop_table('operations')
    op.drop_table('chains')
    op.drop_table('cases')
