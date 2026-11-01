"""
Remi Nusantara 2D - Multiplayer Lobby & Game Server + Non-Blocking Client
Mendukung:
- Pembuatan Room (Host) & Join Room (Maksimal 4 Pemain, sisanya diisi Bot AI).
- Ready Check di Lobby & Start Match menuju 1.500 Poin.
- Sinkronisasi state 2D realtime via TCP JSON Lines (kompatibel langsung dengan Python bawaan Blender 3.6 tanpa perlu install library pihak ketiga).
"""

from __future__ import annotations
import json
import socket
import threading
import time
from typing import Dict, Optional, List
from remi_engine import RemiGameMatch


class RemiTCPServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 55555, room_code: str = "RM1500"):
        self.host = host
        self.port = port
        self.game = RemiGameMatch(room_code=room_code, num_players=4, turn_timer_sec=25)
        self.running = False
        self.server_socket: Optional[socket.socket] = None
        self.clients: Dict[int, socket.socket] = {}  # seat -> socket
        self.lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._tick_thread: Optional[threading.Thread] = None

    def start(self) -> Tuple[bool, str]:
        if self.running:
            return True, f"Server sudah aktif di {self.host}:{self.port}"
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(8)
            self.server_socket.settimeout(0.5)
            self.running = True

            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            self._tick_thread = threading.Thread(target=self._game_tick_loop, daemon=True)
            self._tick_thread.start()
            return True, f"Server Lobby aktif di {self.host}:{self.port} (Room: {self.game.room_code})"
        except Exception as exc:
            return False, f"Gagal menjalankan server: {exc}"

    def stop(self):
        self.running = False
        with self.lock:
            for s in list(self.clients.values()):
                try:
                    s.close()
                except Exception:
                    pass
            self.clients.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def _accept_loop(self):
        while self.running and self.server_socket:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self._client_handler, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _assign_seat(self, player_name: str, preferred_seat: Optional[int] = None) -> int:
        # Cek apakah ada kursi reconnect dengan nama yang sama
        for p in self.game.players:
            if not p.is_bot and p.name == player_name:
                p.connected = True
                p.auto_pilot = False
                return p.seat

        if preferred_seat is not None and 0 <= preferred_seat < 4:
            p = self.game.players[preferred_seat]
            if p.is_bot or not p.connected:
                p.name = player_name
                p.is_bot = False
                p.connected = True
                p.auto_pilot = False
                return p.seat

        for p in self.game.players:
            if p.is_bot or p.seat not in self.clients:
                p.name = player_name
                p.is_bot = False
                p.connected = True
                p.auto_pilot = False
                return p.seat

        return 0

    def _client_handler(self, conn: socket.socket, addr):
        assigned_seat: Optional[int] = None
        buffer = ""
        try:
            conn.settimeout(1.0)
            while self.running:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buffer += data.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        msg = json.loads(line)
                        assigned_seat = self._process_message(conn, assigned_seat, msg)
                except socket.timeout:
                    continue
        except Exception:
            pass
        finally:
            with self.lock:
                if assigned_seat is not None and self.clients.get(assigned_seat) is conn:
                    del self.clients[assigned_seat]
                    p = self.game.players[assigned_seat]
                    p.connected = False
                    p.auto_pilot = True
                    self.game.status_message = f"{p.name} terputus (Mode Auto-Pilot Bot aktif)."
                    self._broadcast_state()
            try:
                conn.close()
            except Exception:
                pass

    def _process_message(self, conn: socket.socket, seat: Optional[int], msg: dict) -> Optional[int]:
        action = msg.get("action")
        with self.lock:
            if action == "JOIN":
                name = msg.get("name", "Player")
                seat = self._assign_seat(name, msg.get("seat"))
                self.clients[seat] = conn
                self.game.status_message = f"{name} bergabung di Kursi {seat + 1}."
                self._send_to(conn, {"type": "WELCOME", "seat": seat, "state": self.game.to_state_dict(seat)})
                self._broadcast_state()
                return seat

            if seat is None:
                return None

            player = self.game.players[seat]
            player.afk_strikes = 0
            player.auto_pilot = False

            if action == "READY":
                player.is_ready = bool(msg.get("ready", True))
                self.game.status_message = f"{player.name} {'SIAP' if player.is_ready else 'BELUM SIAP'}."
            elif action == "START_ROUND":
                self.game.start_new_round()
            elif action == "DRAW_DECK":
                self.game.draw_from_deck(seat)
            elif action == "TAKE_DISCARD":
                idx = int(msg.get("discard_index", -1))
                self.game.take_from_discard(seat, idx, msg.get("meld_card_ids"))
            elif action == "MELD_HAND":
                self.game.meld_from_hand(seat, msg.get("card_ids", []))
            elif action == "AUTO_MELD":
                self.game.auto_meld_all_valid(seat)
            elif action == "DISCARD":
                self.game.discard_card(seat, msg.get("card_id", ""))
            elif action == "SORT_HAND":
                player.sort_hand(by_suit=bool(msg.get("by_suit", False)))
            elif action == "REORDER_HAND":
                self.game.reorder_player_hand(
                    seat,
                    str(msg.get("source_card_id", "")),
                    str(msg.get("target_card_id", "")),
                )

            self._broadcast_state()
        return seat

    def _game_tick_loop(self):
        last_time = time.time()
        bot_cooldown = 0.0
        while self.running:
            time.sleep(0.2)
            now = time.time()
            dt = now - last_time
            last_time = now

            with self.lock:
                if self.game.phase in ("TURN_DRAW", "TURN_MELD_DISCARD"):
                    cur_p = self.game.players[self.game.current_turn_seat]
                    if cur_p.is_bot or cur_p.auto_pilot:
                        bot_cooldown += dt
                        if bot_cooldown >= 0.7:
                            bot_cooldown = 0.0
                            self.game.execute_bot_or_timeout_step()
                            self._broadcast_state()
                    else:
                        self.game.turn_remaining_sec = max(0.0, self.game.turn_remaining_sec - dt)
                        if self.game.turn_remaining_sec <= 0.0:
                            cur_p.afk_strikes += 1
                            if cur_p.afk_strikes >= 2:
                                cur_p.auto_pilot = True
                            self.game.execute_bot_or_timeout_step()
                            self._broadcast_state()

    def _send_to(self, conn: socket.socket, payload: dict):
        try:
            raw = (json.dumps(payload) + "\n").encode("utf-8")
            conn.sendall(raw)
        except Exception:
            pass

    def _broadcast_state(self):
        for seat, conn in list(self.clients.items()):
            payload = {"type": "STATE", "seat": seat, "state": self.game.to_state_dict(seat)}
            self._send_to(conn, payload)


class RemiTCPClient:
    """Klien non-blocking untuk digunakan langsung di dalam Blender Modal Operator / Timer."""

    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self.my_seat: int = 0
        self.latest_state: Optional[dict] = None
        self._buffer = ""

    def connect(self, host: str = "127.0.0.1", port: int = 55555, player_name: str = "Player") -> Tuple[bool, str]:
        self.disconnect()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((host, port))
            s.setblocking(False)
            self.sock = s
            self.connected = True
            self.send({"action": "JOIN", "name": player_name})
            return True, f"Terhubung ke Server {host}:{port}"
        except Exception as exc:
            self.connected = False
            return False, f"Gagal terhubung ke server: {exc}"

    def disconnect(self):
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, payload: dict):
        if not self.connected or not self.sock:
            return
        try:
            self.sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except Exception:
            self.connected = False

    def poll(self) -> Optional[dict]:
        if not self.connected or not self.sock:
            return self.latest_state
        try:
            while True:
                chunk = self.sock.recv(8192)
                if not chunk:
                    self.connected = False
                    break
                self._buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line.strip())
                        if "seat" in msg:
                            self.my_seat = int(msg["seat"])
                        if "state" in msg:
                            self.latest_state = msg["state"]
        except BlockingIOError:
            pass
        except Exception:
            pass
        return self.latest_state
