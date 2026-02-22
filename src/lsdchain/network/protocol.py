"""Protocolo de comunicacao (Padrao Blockchain LSD 2025)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import json


class MessageType(str, Enum):
    NEW_TRANSACTION = "NEW_TRANSACTION"
    NEW_BLOCK = "NEW_BLOCK"
    REQUEST_CHAIN = "REQUEST_CHAIN"
    RESPONSE_CHAIN = "RESPONSE_CHAIN"


@dataclass
class Message:
    type: MessageType
    payload: dict[str, Any]
    sender: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type.value,
                "payload": self.payload,
                "sender": self.sender,
            },
            sort_keys=True,
        )

    def to_bytes(self) -> bytes:
        body = self.to_json().encode("utf-8")
        length = len(body)
        return length.to_bytes(4, "big") + body

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        parsed = json.loads(data.decode("utf-8"))
        return cls(
            type=MessageType(parsed["type"]),
            payload=parsed["payload"],
            sender=parsed.get("sender", ""),
        )


class Protocol:
    """Factory de mensagens do protocolo."""

    @staticmethod
    def new_transaction(transaction_dict: dict[str, Any]) -> Message:
        return Message(
            type=MessageType.NEW_TRANSACTION,
            payload={"transaction": transaction_dict},
        )

    @staticmethod
    def new_block(block_dict: dict[str, Any]) -> Message:
        return Message(
            type=MessageType.NEW_BLOCK,
            payload={"block": block_dict},
        )

    @staticmethod
    def request_chain() -> Message:
        return Message(
            type=MessageType.REQUEST_CHAIN,
            payload={},
        )

    @staticmethod
    def response_chain(blockchain_dict: dict[str, Any]) -> Message:
        return Message(
            type=MessageType.RESPONSE_CHAIN,
            payload={"blockchain": blockchain_dict},
        )
