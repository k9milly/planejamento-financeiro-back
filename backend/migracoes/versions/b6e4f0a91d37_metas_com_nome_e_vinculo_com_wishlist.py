"""Metas de poupança ganham nome e vínculo com a wishlist

Revision ID: b6e4f0a91d37
Revises: a4d1e7b09c52

ADR-13. Aditiva: duas colunas nuláveis em `metas_poupanca`. Nenhuma meta
existente muda de comportamento — as duas nascem nulas, que é o estado
"meta sem nome, sem objetivo vinculado" de sempre.

A mudança de cardinalidade do ADR-13 (várias metas ativas do mesmo tipo) não
precisa de migração: nunca houve restrição no banco, só a regra do router que
aposentava a anterior ao criar uma nova.

`SET NULL` no vínculo, e não `CASCADE`: apagar um desejo da wishlist não pode
levar a meta junto, porque o dinheiro já guardado continua guardado — só perde
a etiqueta de para que era.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6e4f0a91d37"
down_revision: Union[str, None] = "a4d1e7b09c52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("metas_poupanca") as batch:
        batch.add_column(sa.Column("nome", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("wishlist_item_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_meta_wishlist_item",
            "wishlist",
            ["wishlist_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        op.f("ix_metas_poupanca_wishlist_item_id"),
        "metas_poupanca",
        ["wishlist_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_metas_poupanca_wishlist_item_id"), table_name="metas_poupanca"
    )
    with op.batch_alter_table("metas_poupanca") as batch:
        batch.drop_constraint("fk_meta_wishlist_item", type_="foreignkey")
        batch.drop_column("wishlist_item_id")
        batch.drop_column("nome")
