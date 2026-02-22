"""No da rede P2P, comunicacao via sockets (TCP)."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any

from ..core.block import Block
from ..core.blockchain import Blockchain
from ..core.mining import Miner
from ..core.transaction import Transaction
from .protocol import Message, MessageType, Protocol


LOGGER_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _read_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


class Node:
    """Representa um no da rede da blockchain."""

    BUFFER_SIZE = 64 * 1024

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

        self.blockchain = Blockchain()
        self.miner = Miner(self.blockchain, self.address)

        self.peers: set[str] = set()
        self._server: socket.socket | None = None
        self._running = False

        logging.basicConfig(level=logging.INFO, format=LOGGER_FORMAT)
        self.logger = logging.getLogger(f"Node:{self.port}")

    def start(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(20)
        self._running = True
        self.logger.info("No iniciado em %s", self.address)

        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()

    def stop(self) -> None:
        self._running = False
        self.miner.stop()
        if self._server:
            self._server.close()
        self.logger.info("No encerrado")

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client_socket, _ = self._server.accept()
                thread = threading.Thread(
                    target=self._handle_client, args=(client_socket,), daemon=True
                )
                thread.start()
            except Exception as exc:
                if self._running:
                    self.logger.error("Erro ao aceitar conexao: %s", exc)

    def _handle_client(self, client_socket: socket.socket) -> None:
        try:
            length_raw = _read_exact(client_socket, 4)
            if not length_raw:
                return
            length = int.from_bytes(length_raw, "big")
            body = _read_exact(client_socket, length)
            if not body:
                return

            message = Message.from_bytes(body)
            response = self._process_message(message)
            if response:
                response.sender = self.address
                client_socket.sendall(response.to_bytes())
        except Exception as exc:
            self.logger.error("Erro ao processar cliente: %s", exc)
        finally:
            client_socket.close()

    def _process_message(self, message: Message) -> Message | None:
        self.logger.info("Mensagem %s de %s", message.type.value, message.sender)
        if message.sender and message.sender != self.address:
            self.peers.add(message.sender)

        if message.type == MessageType.NEW_TRANSACTION:
            tx_data = message.payload.get("transaction", {})
            try:
                transaction = Transaction.from_dict(tx_data)
            except Exception as exc:
                self.logger.warning("Transacao invalida recebida: %s", exc)
                return None
            if self.blockchain.add_transaction(transaction):
                self.logger.info("Transacao adicionada: %s", transaction.id)
                self._broadcast(
                    Protocol.new_transaction(transaction.to_dict()),
                    exclude=message.sender,
                )

        elif message.type == MessageType.NEW_BLOCK:
            block_data = message.payload.get("block", {})
            try:
                block = Block.from_dict(block_data)
            except Exception as exc:
                self.logger.warning("Bloco invalido recebido: %s", exc)
                return None
            if self.blockchain.add_block(block):
                self.logger.info("Bloco #%s adicionado", block.index)
                self.miner.stop()
                self._broadcast(
                    Protocol.new_block(block.to_dict()),
                    exclude=message.sender,
                )

        elif message.type == MessageType.REQUEST_CHAIN:
            return Protocol.response_chain(self.blockchain.to_dict())

        elif message.type == MessageType.RESPONSE_CHAIN:
            chain_data = message.payload.get("blockchain", {})
            new_chain = [Block.from_dict(b) for b in chain_data.get("chain", [])]
            new_pending = [
                Transaction.from_dict(tx)
                for tx in chain_data.get("pending_transactions", [])
            ]
            if self.blockchain.replace_chain(new_chain):
                self.blockchain.pending_transactions = new_pending
                self.logger.info(
                    "Blockchain atualizada (%s blocos)", len(self.blockchain.chain)
                )

        return None

    def _send_message(
        self, peer: str, message: Message, expect_response: bool = False
    ) -> Message | None:
        try:
            host, port = peer.split(":")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((host, int(port)))
                message.sender = self.address
                sock.sendall(message.to_bytes())

                if not expect_response:
                    return None
                length_raw = _read_exact(sock, 4)
                if not length_raw:
                    return None
                length = int.from_bytes(length_raw, "big")
                body = _read_exact(sock, length)
                if not body:
                    return None
                return Message.from_bytes(body)
        except Exception as exc:
            self.logger.error("Erro ao enviar para %s: %s", peer, exc)
            return None

    def _broadcast(self, message: Message, exclude: str | None = None) -> None:
        for peer in list(self.peers):
            if exclude and peer == exclude:
                continue
            thread = threading.Thread(
                target=self._send_message,
                args=(peer, message, False),
                daemon=True,
            )
            thread.start()

    def connect_to_peer(self, peer: str) -> bool:
        if peer == self.address:
            return False
        response = self._send_message(peer, Protocol.request_chain(), True)
        if response and response.type == MessageType.RESPONSE_CHAIN:
            self.peers.add(peer)
            self._process_message(response)
            return True
        return False

    def sync_blockchain(self) -> None:
        for peer in list(self.peers):
            response = self._send_message(peer, Protocol.request_chain(), True)
            if response and response.type == MessageType.RESPONSE_CHAIN:
                self._process_message(response)

    def broadcast_transaction(self, transaction: Transaction) -> bool:
        if not self.blockchain.add_transaction(transaction):
            return False
        self._broadcast(Protocol.new_transaction(transaction.to_dict()))
        return True

    def broadcast_block(self, block: Block) -> bool:
        if not self.blockchain.add_block(block):
            return False
        self._broadcast(Protocol.new_block(block.to_dict()))
        return True

    def mine(self) -> Block | None:
        self.logger.info("Mineracao iniciada")
        block = self.miner.mine_block()
        if block:
            self.logger.info("Bloco minerado #%s", block.index)
            self.broadcast_block(block)
        return block
