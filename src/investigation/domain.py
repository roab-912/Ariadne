"""Identités et quantités exactes, indépendantes des frameworks et fournisseurs."""
import re
from dataclasses import dataclass
from enum import StrEnum

UINT256_MAX = 2**256 - 1


class CoverageStatus(StrEnum):
    COMPLETE = "complete_within_declared_scope"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


def validate_chain(chain_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{3,16}:[a-zA-Z0-9_-]{1,32}", chain_id):
        raise ValueError("Identifiant de chaîne attendu : espace-de-noms:référence")
    if chain_id.startswith("eip155:") and not re.fullmatch(r"eip155:[1-9][0-9]*", chain_id):
        raise ValueError("Référence EVM canonique attendue")
    return chain_id


@dataclass(frozen=True)
class AddressId:
    chain_id: str
    value: bytes
    display: str

    @classmethod
    def evm(cls, chain_id: str, address: str) -> "AddressId":
        validate_chain(chain_id)
        if not chain_id.startswith("eip155:") or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
            raise ValueError("Adresse EVM de 20 octets attendue")
        return cls(chain_id, bytes.fromhex(address[2:]), address)

    @property
    def key(self) -> str:
        return f"{self.chain_id}:0x{self.value.hex()}"


def asset_id(chain_id: str, contract: str | None = None) -> str:
    validate_chain(chain_id)
    if not chain_id.startswith("eip155:"):
        raise ValueError("Identités d'actifs non EVM réservées à un adaptateur ultérieur")
    if contract is None:
        return f"{chain_id}/native"
    return f"{chain_id}/erc20:0x{AddressId.evm(chain_id, contract).value.hex()}"


def uint256(value: object) -> int:
    # bool est un sous-type de int : le rejeter explicitement.
    if type(value) is not int or not 0 <= value <= UINT256_MAX:
        raise ValueError("Montant entier hors du domaine uint256")
    return value


def parse_amount(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,77}", value):
        raise ValueError("Le montant API doit être une chaîne décimale canonique")
    return uint256(int(value))
