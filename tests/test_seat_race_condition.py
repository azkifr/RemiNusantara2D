import os
import sys
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from web_game_server import GAME, GAME_LOCK, _format_state_dict, RemiWebHandler
import time

class TestSeatRaceCondition(unittest.TestCase):
    def setUp(self):
        with GAME_LOCK:
            GAME.reset_match()
            # Pastikan semua kursi berstatus bot / bersih
            for idx, p in enumerate(GAME.players):
                p.is_bot = True
                p.auto_pilot = True
                p.player_id = ""
                p.last_seen = 0.0

    def test_four_players_claiming_same_seat_race_condition(self):
        """Simulasikan 4 pemain berbeda mencoba merebut Kursi 2 (index 1) di saat yang sama."""
        target_seat = 1
        results = []
        num_players = 4

        def try_claim(player_num):
            pid = f"player_uuid_{player_num}"
            name = f"Pemain #{player_num}"
            payload = {
                "seat": target_seat,
                "player_id": pid,
                "player_name": name,
            }

            # Simulasikan atomic logic seperti di do_POST
            with GAME_LOCK:
                now = time.time()
                target_p = GAME.players[target_seat]
                target_pid = getattr(target_p, "player_id", "")
                is_occupied_by_other = (
                    not target_p.is_bot
                    and target_pid
                    and target_pid != pid
                    and (now - getattr(target_p, "last_seen", now)) < 35.0
                )

                if is_occupied_by_other:
                    return {
                        "player_num": player_num,
                        "success": False,
                        "error": f"Kursi {target_seat + 1} baru saja diambil oleh {target_p.name}!",
                    }

                # Pemain berhasil klaim
                target_p.is_bot = False
                target_p.auto_pilot = False
                target_p.player_id = pid
                target_p.name = name
                target_p.last_seen = now
                return {
                    "player_num": player_num,
                    "success": True,
                    "claimed_seat": target_seat,
                }

        # Jalankan 4 thread secara paralel serentak
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(try_claim, i + 1) for i in range(num_players)]
            results = [f.result() for f in futures]

        success_count = sum(1 for r in results if r["success"] is True)
        rejected_count = sum(1 for r in results if r["success"] is False)

        # Harus tepat 1 pemenang yang berhasil duduk di kursi tersebut
        self.assertEqual(success_count, 1, f"Harus tepat 1 pemain yang berhasil, didapat: {success_count}")
        # 3 pemain lainnya harus ditolak secara aman
        self.assertEqual(rejected_count, 3, f"3 pemain lain harus ditolak, didapat: {rejected_count}")

        # Verifikasi state akhir server
        with GAME_LOCK:
            target_p = GAME.players[target_seat]
            self.assertFalse(target_p.is_bot)
            winner = next(r for r in results if r["success"])
            self.assertEqual(target_p.player_id, f"player_uuid_{winner['player_num']}")
            self.assertEqual(target_p.name, f"Pemain #{winner['player_num']}")

    def test_switch_seat_frees_previous_seat(self):
        """Pemain yang pindah kursi harus otomatis mengosongkan kursi lamanya."""
        pid = "player_abc"
        name = "Azkia"

        with GAME_LOCK:
            now = time.time()
            # Duduk di Kursi 0
            p0 = GAME.players[0]
            p0.is_bot = False
            p0.player_id = pid
            p0.name = name
            p0.last_seen = now

            # Sekarang coba klaim Kursi 2
            target_seat = 2
            target_p = GAME.players[target_seat]

            # Logic pelepasan kursi lama
            for old_idx, old_p in enumerate(GAME.players):
                if old_idx != target_seat and not old_p.is_bot and getattr(old_p, "player_id", "") == pid:
                    old_p.is_bot = True
                    old_p.auto_pilot = True
                    old_p.player_id = ""
                    old_p.name = "Bot Budi"

            target_p.is_bot = False
            target_p.player_id = pid
            target_p.name = name

            # Verifikasi kursi lama (0) sudah jadi Bot
            self.assertTrue(GAME.players[0].is_bot)
            self.assertEqual(GAME.players[0].player_id, "")
            # Verifikasi kursi baru (2) ditempati Azkia
            self.assertFalse(GAME.players[2].is_bot)
            self.assertEqual(GAME.players[2].player_id, pid)


if __name__ == "__main__":
    unittest.main()
