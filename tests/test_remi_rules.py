import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from remi_engine import (
    Card,
    create_deck_53,
    validate_meld,
    has_valid_seri_meld,
    RemiGameMatch,
    TARGET_WIN_SCORE,
    TUTUP_TANGAN_BONUS,
    MAX_DISCARD_TAKE_DEPTH,
)


def test_deck_53_and_4_wildcards_from_first_card():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=42)

    assert game.wildcard_indicator_card is not None, "Harus ada 1 kartu bukaan pertama penentu Wild Card"
    w_rank = game.wildcard_rank
    assert w_rank is not None and w_rank != "JOKER"

    # Kumpulkan seluruh kartu yang beredar di tangan 4 pemain + pak kartu (52 kartu aktif di luar 1 kartu indikator)
    all_play_cards = list(game.draw_pile)
    for p in game.players:
        all_play_cards.extend(p.hand)

    assert len(all_play_cards) == 52, f"Expected 52 play cards + 1 indicator = 53, got {len(all_play_cards)}"
    wild_cards = [c for c in all_play_cards if game.is_wildcard(c)]
    assert len(wild_cards) == 4, f"Harus ada tepat 4 Wild Card (1 Joker + 3 kartu '{w_rank}'), dapat {len(wild_cards)}"

    # Uji kartu berangka w_rank berfungsi sebagai Wild Card di Seri dan Tris
    wild_sample = [c for c in wild_cards if not c.is_joker][0]
    seri_with_wild = validate_meld(
        [Card.from_id("7S"), Card.from_id("8S"), wild_sample],
        wildcard_rank=w_rank,
    )
    assert seri_with_wild.valid and seri_with_wild.meld_type == "SERI_NUMBER" and seri_with_wild.points == 15
    print(f"[PASS] 4 Wild Card Aktif (1 JOKER + 3 Kartu '{w_rank}' dari bukaan pertama '{game.wildcard_indicator_card.id}')")


def test_3_tier_separation_rules():
    r1 = validate_meld([Card.from_id("8S"), Card.from_id("9S"), Card.from_id("10S")])
    assert r1.valid and r1.points == 15

    r2 = validate_meld([Card.from_id("9S"), Card.from_id("10S"), Card.from_id("JS")])
    assert not r2.valid, "9S-10S-JS must be INVALID"

    r3 = validate_meld([Card.from_id("10H"), Card.from_id("JH"), Card.from_id("QH")])
    assert not r3.valid, "10H-JH-QH must be INVALID"

    r4 = validate_meld([Card.from_id("10S"), Card.from_id("JOKER"), Card.from_id("QS")])
    assert not r4.valid, "10S-JOKER-QS must be INVALID"

    r5 = validate_meld([Card.from_id("JD"), Card.from_id("QD"), Card.from_id("KD")])
    assert r5.valid and r5.points == 30

    r6 = validate_meld([Card.from_id("AS"), Card.from_id("2S"), Card.from_id("3S")])
    assert not r6.valid, "AS-2S-3S must be INVALID"

    r7 = validate_meld([Card.from_id("QS"), Card.from_id("KS"), Card.from_id("AS")])
    assert not r7.valid, "QS-KS-AS must be INVALID"

    r8 = validate_meld([Card.from_id("AS"), Card.from_id("AH"), Card.from_id("AD")])
    assert r8.valid and r8.points == 45

    r9 = validate_meld([Card.from_id("AS"), Card.from_id("AH"), Card.from_id("JOKER")])
    assert r9.valid and r9.points == 45
    print("[PASS] Pemisahan 3 Kelompok Kartu (Number 2-10, Face J-Q-K, Ace A berdiri sendiri)")


def test_mandatory_seri_min_3_or_burn_all():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=100)
    game.wildcard_rank = "2"  # Supaya kartu di bawah ini bukan wildcard

    # Pemain 0: Punya SERI_NUMBER (7S-8S-9S = +15) + TRIS_ACE (AS-AH-AD = +45) -> AMAN, tidak terbakar!
    p0 = game.players[0]
    p0.melds = [
        [Card.from_id("7S"), Card.from_id("8S"), Card.from_id("9S")],
        [Card.from_id("AS"), Card.from_id("AH"), Card.from_id("AD")],
    ]
    p0.hand = [Card.from_id("4C")]  # Buang 4C untuk menutup ronde

    # Pemain 1: HANYA punya TRIS_NUMBER (10S-10H-10C) dan TRIS_FACE (KS-KH-KD) di meja, TANPA Kartu Urut dan TANPA Tris As!
    # Saat ronde berakhir, P1 WAJIB TERBAKAR SEMUA (tidak dapat poin positif, semua Tris + kartu tangan menjadi minus!)
    p1 = game.players[1]
    p1.melds = [
        [Card.from_id("10S"), Card.from_id("10H"), Card.from_id("10C")],  # 3x Number = -15 jika terbakar
        [Card.from_id("KS"), Card.from_id("KH"), Card.from_id("KD")],  # 3x Face = -30 jika terbakar
    ]
    p1.hand = [Card.from_id("5D")]  # 1x Number = -5

    # Pemain 2: Punya Seri di tangan (4H-5H-6H = +15) dan 1 kartu mati 10C (-5) -> Fitur No. 2 kembali ke semula:
    # Seri di tangan otomatis dievaluasi saat ronde berakhir sehingga P2 AMAN (+15 - 5 = +10)!
    p2 = game.players[2]
    p2.melds = []
    p2.hand = [
        Card.from_id("4H"),
        Card.from_id("5H"),
        Card.from_id("6H"),
        Card.from_id("10C"),
    ]

    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 2  # Sudah ada kartu jadi sebelumnya -> Tutup Biasa (+0 bonus tutup)

    ok_d, msg_d = game.discard_card(0, "4C")
    assert ok_d, msg_d
    assert game.phase == "ROUND_OVER"

    # Cek P0: Aman karena punya Seri 7S-8S-9S -> +15 + 45 = +60, ditambah Tutup Biasa: buang 4C (5) x Wild '2' (5) = +25
    assert not p0.burned_last_round
    assert p0.last_round_score == 85, f"Expected P0 score +85, got {p0.last_round_score}"

    # Cek P1: TERBAKAR SEMUA karena tidak punya Seri min 3 atau Tris As! (-15 - 30 - 5 = -50)
    assert p1.burned_last_round, "P1 harus berstatus TERBAKAR karena tidak punya Kartu Urut (Seri min 3) atau Tris As!"
    assert p1.last_round_score == -50, f"Expected P1 burned score -50, got {p1.last_round_score}"

    # Cek P2: Aman karena punya Seri 4H-5H-6H (+15) dikurangi 10C (-5) = +10
    assert not p2.burned_last_round
    assert p2.last_round_score == 10, f"Expected P2 score +10, got {p2.last_round_score}"
    print("[PASS] Aturan Wajib Seri Min 3 (Kartu Urut): Pemain tanpa Seri tidak dapat poin & SEMUA kartunya TERBAKAR")


def test_feature_2_reverted_auto_meld_and_tutup_tangan_250():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=250)
    game.wildcard_rank = "2"

    # 1. Uji Ambil Buangan otomatis langsung menurunkan Kartu Jadi ke meja (Fitur No. 2 kembali ke semula)
    p0 = game.players[0]
    game.discard_pile = [Card.from_id("7H"), Card.from_id("3C")]
    p0.hand = [
        Card.from_id("8H"),
        Card.from_id("9H"),
        Card.from_id("JD"),
        Card.from_id("QD"),
        Card.from_id("KD"),
        Card.from_id("AS"),
        Card.from_id("AC"),
    ]
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0
    ok_take, _ = game.take_from_discard(0, 0)
    assert ok_take
    assert len(p0.melds) == 1, "Ambil kartu buangan harus otomatis langsung menurunkan Kartu Jadi ke meja!"

    # 2. Uji tombol AUTO TURUN (auto_meld_all_valid) menurunkan JD-QD-KD dari tangan
    ok_auto, _ = game.auto_meld_all_valid(0)
    assert ok_auto
    assert len(p0.melds) == 2

    # 3. Uji Tutup Tangan Murni (+250 Poin) TANPA Kartu Jadi sebelumnya & wajib punya Seri min 3
    game.start_new_round(seed=300)
    game.wildcard_rank = "9"
    p0 = game.players[0]
    p0.total_score = 0
    p0.melds = []
    p0.hand = [
        Card.from_id("3S"),
        Card.from_id("4S"),
        Card.from_id("5S"),
        Card.from_id("6S"),
        Card.from_id("AS"),
        Card.from_id("AH"),
        Card.from_id("AD"),
        Card.from_id("KC"),
    ]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 0
    ok_tt, msg_tt = game.declare_tutup_tangan(0, "KC")
    assert ok_tt, msg_tt
    assert p0.last_round_score == TUTUP_TANGAN_BONUS, f"Tutup Tangan Murni harus HANYA +250, got {p0.last_round_score}"
    print("[PASS] Fitur No. 2 kembali ke semula (Auto-Meld Buangan & Akhir Ronde) + Tutup Tangan Murni = HANYA +250 Poin")


def test_take_discard_for_tris_requires_seri_first_and_ace_exception():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=500)
    game.wildcard_rank = "2"
    p0 = game.players[0]

    # 1. Belum punya Seri: ambil 7H untuk Tris (7S-7D) harus DITOLAK
    p0.melds = []
    p0.hand = [Card.from_id("7S"), Card.from_id("7D"), Card.from_id("JC"), Card.from_id("AS")]
    game.discard_pile = [Card.from_id("7H")]
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0
    ok, msg = game.take_from_discard(0, 0)
    assert not ok, "Ambil buangan untuk Tris selain As harus ditolak sebelum punya Seri!"

    # 2. Belum punya Seri tapi buangan membentuk Seri (5H-6H + 7H) -> BOLEH
    p0.hand = [Card.from_id("5H"), Card.from_id("6H"), Card.from_id("7S"), Card.from_id("7D"), Card.from_id("AS")]
    ok2, msg2 = game.take_from_discard(0, 0)
    assert ok2, msg2
    assert [c.id for c in p0.melds[0]] == ["5H", "6H", "7H"], "Harus turun sebagai Seri, bukan Tris"

    # 3. KHUSUS KARTU 'A':
    # Kasus 3a: Belum punya Seri di meja, tapi di tangan punya HANYA 1 As (+ Joker) -> DITOLAK (harus min 2 kartu As)
    game.start_new_round(seed=501)
    game.wildcard_rank = "6"
    p0 = game.players[0]
    p0.melds = []
    p0.hand = [Card.from_id("AS"), Card.from_id("JOKER"), Card.from_id("8H"), Card.from_id("9H"), Card.from_id("KC")]
    game.discard_pile = [Card.from_id("AH")]
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0
    ok3a, msg3a = game.take_from_discard(0, 0)
    assert not ok3a, f"Harus ditolak jika di tangan hanya punya 1 As: {msg3a}"

    # Kasus 3b: Belum punya Seri di meja, dan di tangan PUNYA MINIMAL 2 KARTU AS (AS, AD) -> BOLEH diambil & turun Tris As!
    p0.hand = [Card.from_id("AS"), Card.from_id("AD"), Card.from_id("8H"), Card.from_id("9H"), Card.from_id("KC")]
    game.discard_pile = [Card.from_id("AH")]
    ok3b, msg3b = game.take_from_discard(0, 0)
    assert ok3b, f"Harus berhasil ambil As jika punya min 2 As di tangan: {msg3b}"
    assert len(p0.melds) == 1
    assert set(c.id for c in p0.melds[0]) == {"AH", "AS", "AD"}

    # Kasus 3c: Sudah punya Seri di meja, ambil kartu buangan angka untuk Tris -> BOLEH
    p0.melds = [[Card.from_id("7S"), Card.from_id("8S"), Card.from_id("9S")]]  # Sudah ada Seri
    p0.hand = [Card.from_id("10S"), Card.from_id("10D"), Card.from_id("KC")]
    game.discard_pile = [Card.from_id("10H")]
    game.phase = "TURN_DRAW"
    ok3c, msg3c = game.take_from_discard(0, 0)
    assert ok3c, msg3c
    print("[PASS] Ambil buangan wajib straight min 3, dan khusus kartu 'A' bisa diambil jika min punya 2 kartu 'A'")


def test_tutup_biasa_discard_times_wildcard():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=600)
    game.wildcard_rank = "6"  # Wild Card kelompok Angka = 5 poin
    p0 = game.players[0]
    p0.melds = [[Card.from_id("7S"), Card.from_id("8S"), Card.from_id("9S")]]  # +15
    p0.hand = [Card.from_id("KC")]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 1
    ok, msg = game.discard_card(0, "KC")
    assert ok, msg
    assert game.phase == "ROUND_OVER"
    # Kartu jadi +15, Tutup Biasa: K (10) x Wild angka (5) = +50 -> total +65
    assert p0.last_round_breakdown["tutup_bonus"] == 50, p0.last_round_breakdown
    assert p0.last_round_score == 65, f"Expected +65, got {p0.last_round_score}"

    # Wild Card kelompok Face (Q=10): buang A (15) x 10 = +150
    game.start_new_round(seed=601)
    game.wildcard_rank = "Q"
    p0 = game.players[0]
    p0.melds = [[Card.from_id("3H"), Card.from_id("4H"), Card.from_id("5H")]]
    p0.hand = [Card.from_id("AC")]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 1
    ok, msg = game.discard_card(0, "AC")
    assert ok, msg
    assert p0.last_round_breakdown["tutup_bonus"] == 150, p0.last_round_breakdown
    print("[PASS] Tutup Biasa: nilai kartu buangan penutup x nilai Wild Card (K=10 x 5 = +50)")


def test_tris_ace_can_meld_without_seri_and_saves_from_burn():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=700)
    game.wildcard_rank = "2"
    p0 = game.players[0]

    # 1. Pemain belum punya Seri di meja:
    # Coba turunkan Tris Angka (7S-7H-7D) dari tangan -> DITOLAK karena belum buka Seri / Tris As!
    p0.melds = []
    p0.hand = [
        Card.from_id("7S"), Card.from_id("7H"), Card.from_id("7D"),
        Card.from_id("AS"), Card.from_id("AH"), Card.from_id("AD"),
        Card.from_id("KC"), Card.from_id("KD"),
    ]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    ok_num, msg_num = game.meld_from_hand(0, ["7S", "7H", "7D"])
    assert not ok_num, f"Harus ditolak menurunkan Tris angka sebelum buka Seri / Tris As: {msg_num}"

    # 2. Turunkan Tris As (AS-AH-AD) langsung dari tangan TANPA Seri -> BERHASIL!
    ok_ace, msg_ace = game.meld_from_hand(0, ["AS", "AH", "AD"])
    assert ok_ace, f"Harus berhasil menurunkan Tris As tanpa kartu Seri: {msg_ace}"
    assert len(p0.melds) == 1

    # 3. Sekarang setelah punya Tris As di meja, Tris angka (7S-7H-7D) sudah boleh turun!
    ok_num2, msg_num2 = game.meld_from_hand(0, ["7S", "7H", "7D"])
    assert ok_num2, f"Harus bisa turunkan Tris angka setelah buka Tris As: {msg_num2}"
    assert len(p0.melds) == 2

    # 4. Status akhir ronde: Pemain yang hanya punya Tris As di meja AMAN dari penalti terbakar!
    game.start_new_round(seed=701)
    game.wildcard_rank = "2"
    p0 = game.players[0]
    p0.melds = [[Card.from_id("AS"), Card.from_id("AH"), Card.from_id("AD")]]  # Hanya Tris As (tanpa Seri)
    p0.hand = [Card.from_id("10C"), Card.from_id("JC")]  # Kartu mati -15
    p1 = game.players[1]
    p1.melds = [[Card.from_id("KS"), Card.from_id("KH"), Card.from_id("KD")]]  # Hanya Tris Face (tanpa Seri & tanpa Tris As) -> TERBAKAR!
    p1.hand = [Card.from_id("9H")]

    # Buat pemain 2 menutup ronde
    p2 = game.players[2]
    p2.melds = [[Card.from_id("4H"), Card.from_id("5H"), Card.from_id("6H")]]
    p2.hand = [Card.from_id("3C")]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 2
    game.discard_card(2, "3C")
    assert game.phase == "ROUND_OVER"

    # P0 aman tidak terbakar karena punya Tris As (skor +45 As - 15 mati = +30)
    assert not p0.burned_last_round, "P0 harus AMAN karena punya Tris As!"
    assert p0.last_round_score == 30, f"Expected +30, got {p0.last_round_score}"

    # P1 terbakar karena tidak punya Seri dan tidak punya Tris As (minus semua: -30 Tris K - 5 = -35)
    assert p1.burned_last_round, "P1 harus TERBAKAR karena hanya punya Tris K tanpa Seri/Tris As!"
    assert p1.last_round_score == -35, f"Expected -35, got {p1.last_round_score}"
    print("[PASS] Tris As min 3 bisa langsung turun tanpa Seri, dan aman dari terbakar di akhir ronde")


def test_feeder_penalty_x10_when_discard_is_taken_to_close():
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=800)
    game.wildcard_rank = "2"  # Kartu 2 adalah Wild

    # Pemain 0 (Bot Budi / Feeder) membuang kartu 5S (kartu angka bernilai 5 poin)
    p0 = game.players[0]
    p0.hand = [Card.from_id("5S"), Card.from_id("KC")]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    ok0, _ = game.discard_card(0, "5S")
    assert ok0
    assert game.current_turn_seat == 1
    assert game.card_discarder["5S"] == 0

    # Pemain 1 (Closer): di tangan punya 4S, 6S, JS, QS, KS, dan kartu buang 10H
    # Pemain 1 mengambil 5S dari buangan -> jadi Seri 4S-5S-6S, lalu buang 10H untuk TUTUP!
    p1 = game.players[1]
    p1.melds = [[Card.from_id("JS"), Card.from_id("QS"), Card.from_id("KS")]]  # Sudah ada 1 Seri
    p1.hand = [Card.from_id("4S"), Card.from_id("6S"), Card.from_id("10H")]
    game.melds_count_at_turn_start = 1

    # Ambil 5S dari buangan
    ok_take, msg_take = game.take_from_discard(1, len(game.discard_pile) - 1)
    assert ok_take, msg_take
    assert game.turn_taken_discard_card.id == "5S"
    assert game.turn_taken_discarder_seat == 0

    # Buang 10H untuk TUTUP BIASA!
    ok_close, msg_close = game.discard_card(1, "10H")
    assert ok_close, msg_close
    assert game.phase == "ROUND_OVER"

    # Pemain 0 (Feeder) harus terkena penalti kartu 5 x 10 = 50 poin (-50)!
    assert p0.last_round_breakdown["feed_penalty"] == 50, p0.last_round_breakdown
    assert "PENALTI UMPAN TUTUP x10" in game.status_message
    print("[PASS] Penalti umpan tutup x10 (pemain yang membuang kartu yang dimakan untuk tutup terkena penalti nilai kartu x 10)")


def test_drag_and_drop_reorder_hand():
    game = RemiGameMatch(num_players=4)
    p0 = game.players[0]
    p0.hand = [Card.from_id("4S"), Card.from_id("5S"), Card.from_id("6S"), Card.from_id("10H")]
    
    # Drag 10H ke posisi 4S (geser ke paling depan)
    ok1, msg1 = game.reorder_player_hand(0, "10H", "4S")
    assert ok1
    assert [c.id for c in p0.hand] == ["10H", "4S", "5S", "6S"]
    
    # Drag 4S ke posisi 6S (pindah ke dekat 6S)
    ok2, msg2 = game.reorder_player_hand(0, "4S", "6S")
    assert ok2
    assert [c.id for c in p0.hand] == ["10H", "5S", "4S", "6S"]
    
    # Drag ke kartu yang sama tidak mengubah apa pun
    ok3, _ = game.reorder_player_hand(0, "10H", "10H")
    assert not ok3

    # Drag kartu yang tidak ada di tangan gagal secara aman
    ok4, _ = game.reorder_player_hand(0, "UNKNOWN", "10H")
    assert not ok4
    print("[PASS] Fitur Drag and Drop reorder hand berhasil diuji")


def test_tutup_tangan_with_single_ace_and_two_wildcards():
    """
    Menguji skenario persis pada screenshot pengguna:
    - 4 Wildcard: JOKER + 3 kartu '8' (misal: 8C, 8S)
    - Tangan Pemain (8 kartu): 3D, 5D, 6D, 8C(Wild), AD, JOKER(Wild), 8S(Wild), 2H
    - Seri 4 kartu: 3D - 8C(sebagai 4D) - 5D - 6D
    - Tris As 3 kartu: AD - JOKER - 8S (1 As asli + 2 Wildcard = sah Tris As!)
    - Sisa 1 kartu buang: 2H
    Pemain langsung bisa klik Tutup Tangan Murni (+250 Poin) dan sukses menutup ronde!
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=123)
    game.wildcard_rank = "8"
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 0
    p0 = game.players[0]
    p0.melds = []
    p0.hand = [Card.from_id(cid) for cid in ["3D", "5D", "6D", "8C", "AD", "JOKER", "8S", "2H"]]

    # Periksa deteksi can_tutup_tangan (bisa tutup dengan membuang 2H atau AD)
    can_tutup, closing_card_id = game.check_can_declare_tutup_tangan(0)
    assert can_tutup, "Pemain harus terdeteksi SIAP Tutup Tangan Murni!"
    assert closing_card_id in ("2H", "AD"), f"Kartu penutup harus 2H atau AD, dapat: {closing_card_id}"

    # Eksekusi declare_tutup_tangan dengan kartu buang 2H
    ok, msg = game.declare_tutup_tangan(0, "2H")
    assert ok, f"Tutup Tangan harus berhasil: {msg}"
    assert game.phase == "ROUND_OVER", f"Fase game harus ROUND_OVER, dapat: {game.phase}"
    assert p0.last_round_score == 250, f"Skor harus +250 Poin murni, dapat: {p0.last_round_score}"
    assert not p0.burned_last_round, "Pemain tidak boleh terbakar karena punya Seri dan Tris As!"
    assert [c.id for c in game.discard_pile][-1] == "2H", "Kartu buangan terakhir harus 2H"
    print("[PASS] Tutup Tangan Murni dengan 1 As asli + 2 Wildcard berhasil 100% (+250 Poin)")


def test_taking_discard_avoids_consuming_wildcard_from_hand():
    """
    Menguji Aturan Baru:
    1. Mengambil kartu buangan otomatis memprioritaskan kombinasi natural (0 Wild Card dari tangan).
       Jika pemain punya kartu natural untuk Seri dan juga memegang Wild Card (Joker / Rank Wild),
       Wild Card TIDAK BOLEH termakan otomatis ke dalam meld!
    2. Jika pemain tidak memiliki kombinasi murni (hanya bisa dengan mengorbankan Wild Card),
       pengambilan otomatis dicegah untuk melindungi Wild Card pemain, KECUALI pemain secara
       eksplisit memilih kartu di tangannya (explicit_meld_card_ids).
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=1)
    game.wildcard_rank = '8'

    # Setup pemain 0
    p0 = game.players[0]
    p0.melds = []  # Belum ada seri di meja
    # Tangan pemain 0: 5 wajik, 6 wajik, Joker (wild), 8 keriting (wild), A wajik, 2 hati
    p0.hand = [
        Card.from_id('5D'),
        Card.from_id('6D'),
        Card.from_id('JOKER'),
        Card.from_id('8C'),
        Card.from_id('AD'),
        Card.from_id('2H'),
    ]
    # Discard pile teratas adalah 7 wajik (7D)
    game.discard_pile = [Card.from_id('KH'), Card.from_id('7D')]
    game.phase = 'TURN_DRAW'
    game.current_turn_seat = 0

    # Tes 1: can_take_discard harus memilih kombinasi natural 5D-6D-7D (0 Wildcard!)
    ok, msg, req_meld = game.can_take_discard(0, 1)
    assert ok, f'Seharusnya boleh ambil: {msg}'
    assert req_meld is not None
    req_ids = [c.id for c in req_meld]
    assert 'JOKER' not in req_ids, 'Joker TIDAK boleh termakan ke dalam kombinasi buangan!'
    assert '8C' not in req_ids, '8C (Wild) TIDAK boleh termakan ke dalam kombinasi buangan!'
    assert sorted(req_ids) == ['5D', '6D', '7D'], f'Kombinasi harus 5D-6D-7D natural, tapi didapat: {req_ids}'

    # Tes 2: Eksekusi take_from_discard
    ok_take, msg_take = game.take_from_discard(0, 1)
    assert ok_take
    hand_ids = [c.id for c in p0.hand]
    assert 'JOKER' in hand_ids, 'JOKER harus tetap aman di tangan pemain!'
    assert '8C' in hand_ids, '8C (Wild) harus tetap aman di tangan pemain!'

    # Tes 3: Kasus di mana pemain HANYA bisa membentuk kombinasi jika mengorbankan Wild Card
    p0.hand = [
        Card.from_id('5D'),
        Card.from_id('JOKER'),
        Card.from_id('AD'),
    ]
    p0.melds = [[Card.from_id('9S'), Card.from_id('10S'), Card.from_id('JS')]]  # Sudah aman seri
    game.discard_pile = [Card.from_id('6D')]
    game.phase = 'TURN_DRAW'

    # Tanpa explicit selection: auto-take dicegah agar tidak rugi wild card
    ok_auto, msg_auto, _ = game.can_take_discard(0, 0)
    assert not ok_auto, 'Auto-take dengan wildcard dari tangan harus dicegah secara otomatis'
    assert 'Wild Card' in msg_auto

    # Dengan explicit selection: pemain sengaja memilih 5D dan JKR
    ok_exp, msg_exp = game.take_from_discard(0, 0, explicit_meld_card_ids=['5D', 'JOKER'])
    assert ok_exp, f'Explicit take harus diizinkan: {msg_exp}'
    assert any('JOKER' in [c.id for c in m] for m in p0.melds), 'Meld dengan wildcard eksplisit berhasil diturunkan'
    print('[PASS] Proteksi Wild Card saat ambil buangan lulus 100%!')


def test_highest_score_player_starts_and_main_terus():
    """
    Menguji Aturan Baru:
    Pemain yang memiliki skor tertinggi yang seharusnya main terus menerus (mulai pertama ronde)!
    - Ronde 1: Semua skor 0 -> Pemain 0 mulai.
      Setelah ronde 1: Bot Budi (seat 1) memiliki total skor tertinggi (250 poin) -> Bot Budi pegang giliran pembuka.
    - Ronde 2: Bot Budi mulai. Setelah ronde 2, Bot Budi masih memimpin (skor 300) -> Bot Budi TETAP MAIN TERUS!
    - Ronde 3: Bot Budi mulai. Setelah ronde 3, Bot Agus (seat 3) menyalip dengan total skor 450 -> Sekarang Bot Agus yang MAIN TERUS!
    - Ronde 4: Bot Agus mulai.
    - Reset Match: Reset ke Ronde 1 -> Pemain 0 mulai.
    """
    game = RemiGameMatch(num_players=4)
    assert game.starter_seat == 0
    assert game.highest_score_seat == 0

    # 1. Ronde 1 dimulai
    game.start_new_round(seed=10)
    assert game.starter_seat == 0
    assert game.current_turn_seat == 0

    # Bot Budi (seat 1) dapat skor tertinggi di Ronde 1
    game.players[0].total_score = -30
    game.players[1].total_score = 250
    game.players[2].total_score = 40
    game.players[3].total_score = 50
    game._finish_round(closer_seat=1, is_tutup_tangan=True, reason='Bot Budi Tutup')
    assert game.starter_seat == 1
    assert game.highest_score_seat == 1

    # 2. Ronde 2 dimulai: Bot Budi (skor tertinggi) harus jadi pembuka!
    game.start_new_round(seed=20)
    assert game.starter_seat == 1
    assert game.current_turn_seat == 1

    # Di Ronde 2: Bot Budi masih skor tertinggi
    game.players[1].total_score = 310
    game.players[3].total_score = 120
    game._finish_round(closer_seat=None, is_tutup_tangan=False, reason='Pak habis')
    assert game.starter_seat == 1
    assert game.highest_score_seat == 1

    # 3. Ronde 3 dimulai: Bot Budi tetap main terus!
    game.start_new_round(seed=30)
    assert game.starter_seat == 1
    assert game.current_turn_seat == 1

    # Di Ronde 3: Bot Agus menyalip menjadi skor tertinggi (450 poin)!
    game.players[3].total_score = 450
    game.players[1].total_score = 310
    game._finish_round(closer_seat=3, is_tutup_tangan=False, reason='Bot Agus Tutup Biasa')
    assert game.starter_seat == 3
    assert game.highest_score_seat == 3

    # 4. Ronde 4 dimulai: Sekarang Bot Agus yang main terus!
    game.start_new_round(seed=40)
    assert game.starter_seat == 3
    assert game.current_turn_seat == 3

    # 5. Reset Match
    game.phase = 'MATCH_OVER'
    game.start_new_round(seed=50)
    assert game.starter_seat == 0
    assert game.highest_score_seat == 0
    print('[PASS] Aturan Pemain Skor Tertinggi Main Terus Lulus 100%!')


def test_dashboard_match_configuration_and_timer_settings():
    """
    Menguji Fitur Dashboard & Pengaturan Permainan:
    1. Pengaturan Waktu Jalan (Turn Timer): 15s (Blitz), 40s (Santai), 0 (Tanpa Batas/Unlimited).
    2. Pengaturan Target Skor: 500 Poin, 1000 Poin, 1500 Poin.
    3. Pengaturan Jumlah Pemain: 2 Pemain (Duel 1v1), 3 Pemain, 4 Pemain.
    4. Custom Nama Pemain.
    5. Reset Match & Memulai Permainan dari Dashboard.
    """
    game = RemiGameMatch(room_code="RM1500", num_players=4, turn_timer_sec=25)
    assert game.phase == "LOBBY"
    assert game.turn_timer_sec == 25
    assert game.target_score == 1500
    assert len(game.players) == 4

    # 1. Konfigurasi Mode Blitz 15 Detik & Target 500 Poin dengan 2 Pemain
    cfg = game.configure_match(
        num_players=2,
        turn_timer_sec=15,
        target_score=500,
        player_name="Sultan Remi",
        bot_delay_sec=0.4,
    )
    assert cfg["turn_timer_sec"] == 15
    assert cfg["target_score"] == 500
    assert cfg["num_players"] == 2
    assert cfg["player_name"] == "Sultan Remi"
    assert len(game.players) == 2
    assert game.players[0].name == "Sultan Remi"

    # Mulai ronde pertama dari Dashboard
    game.start_new_round()
    assert game.phase == "TURN_DRAW"
    assert game.turn_timer_sec == 15
    assert game.turn_remaining_sec == 15.0
    assert game.target_score == 500

    # 2. Uji Mode Tanpa Batas Waktu (Unlimited / turn_timer_sec = 0)
    game.configure_match(turn_timer_sec=0)
    assert game.turn_timer_sec == 0
    game.start_new_round()
    assert game.turn_remaining_sec >= 999.0, "Mode Unlimited tidak boleh timeout"

    # 3. Uji Reset Match dari Dashboard
    game.players[0].total_score = 350
    game.reset_match()
    assert game.phase == "LOBBY"
    assert game.round_number == 0
    assert game.players[0].total_score == 0

    # 4. Uji Serialisasi to_state_dict menyertakan data Dashboard
    st = game.to_state_dict()
    assert "turn_timer_sec" in st
    assert "target_score" in st
    assert "max_players" in st
    assert "bot_delay_sec" in st
    print("[PASS] Dashboard Match Configuration & Timer Settings Lulus 100%!")


def test_auto_next_round_countdown_5_seconds():
    """
    Menguji Aturan Baru:
    - Tidak ada tombol Next Round yang bisa kepencet sembarangan.
    - Saat ronde selesai (ROUND_OVER), sistem mengeset countdown 5 detik (round_over_timer = 5.0).
    - Ketika countdown habis (round_over_timer <= 0), ronde berikutnya otomatis dimulai!
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=1)
    assert game.phase == 'TURN_DRAW'

    # Selesaikan ronde 1 (Pak habis)
    game._finish_round(closer_seat=None, is_tutup_tangan=False, reason='Pak kartu habis')
    assert game.phase == 'ROUND_OVER'
    assert game.round_over_timer == 5.0

    # Simulasi status countdown
    st = game.to_state_dict()
    assert st['round_over_timer'] == 5.0

    # Ketika timer habis -> panggil start_new_round otomatis
    game.start_new_round(seed=2)
    assert game.phase == 'TURN_DRAW'
    assert game.round_number == 2
    assert game.round_over_timer is None
    print('[PASS] Auto Next Round Countdown 5 Detik Lulus 100%!')


def test_closing_after_taking_discard_is_not_250_but_tutup_biasa():
    """
    Menguji Aturan Baru:
    Jika pemain menutup tangan tetapi hasil dari mengambil kartu di tempat pembuangan,
    nilainya BUKAN 250 (bukan Tutup Tangan Murni)!
    Melainkan dihitung sebagai TUTUP BIASA:
    Skor = Total Poin Kartu Jadi + Bonus (Nilai Kartu Buangan Penutup x Nilai Wild Card).
    Serta pemain yang membuang kartu terkena Penalti Umpan Tutup x10.
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=999)
    game.wildcard_rank = "8"  # Nilai Wild = 5 (angka)

    # Pemain 0 belum pernah meld sebelumnya (melds_count_at_turn_start = 0)
    p0 = game.players[0]
    p0.melds = []
    # Di tangan ada: 4H, 6H, JH, QH, KH, 9S (sisa 1 kartu buang)
    # Discard pile ada 5H yang baru dibuang oleh Pemain 3 (feeder)
    p0.hand = [
        Card.from_id("4H"),
        Card.from_id("6H"),
        Card.from_id("JH"),
        Card.from_id("QH"),
        Card.from_id("KH"),
        Card.from_id("9S"),
    ]
    target_5h = Card.from_id("5H")
    game.discard_pile = [target_5h]
    game.card_discarder["5H"] = 3
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0

    # Pemain 0 mengambil 5H dari tumpukan buangan -> membentuk Seri 4H-5H-6H
    ok_take, msg_take = game.take_from_discard(0, 0)
    assert ok_take, msg_take
    assert game.turn_taken_discard_card.id == "5H"

    # Di tangan p0 sekarang ada: JH, QH, KH, 9S
    # Sisa kartu di tangan membentuk Seri Face (JH-QH-KH = 30 poin) dan 9S (angka 9 = 5 poin) dibuang untuk TUTUP!
    ok_close, msg_close = game.discard_card(0, "9S")
    assert ok_close, msg_close
    assert game.phase == "ROUND_OVER"
    assert not game.round_closed_by_tutup_tangan, "Harus TUTUP BIASA, bukan Tutup Tangan Murni!"

    # Evaluasi Skor Pemain 0:
    # Kartu Jadi 1: 4H-5H-6H (Seri Number = 5+5+5 = 15 poin)
    # Kartu Jadi 2: JH-QH-KH (Seri Face = 10+10+10 = 30 poin)
    # Total Kartu Jadi = 45 poin.
    # Bonus Buangan: 9S (angka = 5 poin) x Wild '8' (angka = 5 poin) = +25 poin.
    # Total Skor Ronde = 45 + 25 = 70 poin (BUKAN 250!).
    p0_bd = p0.last_round_breakdown
    assert p0_bd["tutup_bonus"] == 25, f"Tutup bonus harus 25, didapat {p0_bd['tutup_bonus']}"
    assert p0_bd["meld_points"] == 45, f"Meld points harus 45, didapat {p0_bd['meld_points']}"
    assert p0_bd["round_net"] == 70, f"Skor harus 70 (bukan 250!), didapat {p0_bd['round_net']}"
    assert p0.last_round_score == 70

    # Pemain 3 (Feeder) kena penalti kartu 5S x 10 = 50 poin
    p3 = game.players[3]
    assert p3.last_round_breakdown["feed_penalty"] == 50
    print("[PASS] Tutup dari buangan bukan 250 melainkan Tutup Biasa (Meld + Buang x Wild) Lulus 100%!")




def test_discarded_wildcards_cannot_be_taken_by_other_players():
    """
    Menguji Aturan Baru:
    'jika wildcard dibuang tidak bisa diambil oleh pemain lain'
    1. Kartu Wildcard (JOKER atau 3 kartu se-angka dengan bukaan wild) yang dibuang ke discard pile
       TIDAK DAPAT diambil (can_take_discard dan take_from_discard mengembalikan False).
    2. Jika suatu kartu berada di bawah kartu Wildcard pada tumpukan buangan (sehingga pengambilan
       akan mengikutsertakan Wildcard ke tangan), kartu tersebut juga TIDAK BOLEH diambil.
    3. Kartu biasa yang dibuang SETELAH Wildcard (berada di atas Wildcard) tetap boleh diambil normal.
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=42)
    game.wildcard_rank = "8"
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0

    p0 = game.players[0]
    p0.hand = [
        Card.from_id("3D"),
        Card.from_id("4D"),
        Card.from_id("5D"),
        Card.from_id("10H"),
        Card.from_id("JH"),
        Card.from_id("QH"),
        Card.from_id("2C"),
    ]

    c_6d = Card.from_id("6D")
    c_8c = Card.from_id("8C")
    c_jkr = Card.from_id("JOKER")
    c_9h = Card.from_id("9H")
    game.discard_pile = [c_6d, c_8c, c_jkr, c_9h]

    # Kasus 1: Pemain 0 mencoba mengambil JOKER (Index 2)
    ok, msg, _ = game.can_take_discard(0, 2)
    assert not ok, "Joker di tempat buangan TIDAK BOLEH diambil!"
    assert "Wild Card" in msg

    ok_take, msg_take = game.take_from_discard(0, 2)
    assert not ok_take, "take_from_discard pada Joker harus gagal!"

    # Kasus 2: Pemain 0 mencoba mengambil 8C (Index 1 - Wild Rank 8)
    ok_8, msg_8, _ = game.can_take_discard(0, 1)
    assert not ok_8, "Wild Card 8C di tempat buangan TIDAK BOLEH diambil!"
    assert "Wild Card" in msg_8

    # Kasus 3: Pemain 0 mencoba mengambil 6D (Index 0 - kartu di bawah Wildcard)
    ok_sub, msg_sub, _ = game.can_take_discard(0, 0)
    assert not ok_sub, "Kartu di bawah Wildcard buangan TIDAK BOLEH diambil!"
    assert "Wild Card" in msg_sub

    # Kasus 4: Kartu 2D (Index 3 - berada di atas Wildcard)
    c_2d = Card.from_id("2D")
    game.discard_pile[3] = c_2d
    ok_top, msg_top, _ = game.can_take_discard(0, 3)
    assert ok_top, f"Kartu 2D di atas Wildcard harusnya bisa diambil! Pesan: {msg_top}"

    print("[PASS] Wild Card buangan tidak bisa diambil oleh pemain lain (dan melindungi kartu di bawahnya) Lulus 100%!")


def test_take_discard_forms_full_sequence_7_to_10():
    """
    Memverifikasi kasus di mana pemain memegang 7C, 9C, 10C di tangan dan mengambil 8C dari buangan.
    Sistem harus otomatis memilih kombinasi lengkap [7C-8C-9C-10C] (4 kartu),
    bukan memotong jadi [7C-8C-9C] yang meninggalkan 10C sebagai kartu mati!
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=1)
    game.wildcard_rank = "Q"

    p0 = game.players[0]
    p0.melds = []
    p0.hand = [
        Card.from_id("7C"),
        Card.from_id("9C"),
        Card.from_id("10C"),
        Card.from_id("3S"),
        Card.from_id("3H"),
        Card.from_id("5H"),
        Card.from_id("KH"),
        Card.from_id("AS"),
    ]
    game.discard_pile = [Card.from_id("8C"), Card.from_id("AH")]
    game.phase = "TURN_DRAW"
    game.current_turn_seat = 0

    ok, msg, req_meld = game.can_take_discard(0, 0)
    assert ok, f"Gagal can_take_discard: {msg}"
    assert req_meld is not None
    req_ids = [c.id for c in req_meld]
    assert req_ids == ["7C", "8C", "9C", "10C"], f"Harusnya 7C-8C-9C-10C, didapat: {req_ids}"

    ok_take, msg_take = game.take_from_discard(0, 0)
    assert ok_take, f"Gagal take_from_discard: {msg_take}"
    assert len(p0.melds) == 1
    assert [c.id for c in p0.melds[0]] == ["7C", "8C", "9C", "10C"]
    hand_ids = [c.id for c in p0.hand]
    assert "10C" not in hand_ids, "10C harusnya ikut turun ke meja dalam meld 7-8-9-10!"
    print("[PASS] Ambil buangan 8C saat pegang 7C, 9C, 10C membentuk run utuh [7C-8C-9C-10C] Lulus 100%!")


def test_extend_and_layoff_cards_to_table_melds():
    """
    Memverifikasi fitur menyambung kartu tangan ke kombinasi yang sudah ada di meja (layoff/extend):
    1. Pemain dapat memilih 1 kartu (misal 10C) dan meld_from_hand untuk menyambung ke [7C, 8C, 9C] menjadi [7C, 8C, 9C, 10C].
    2. auto_meld_all_valid otomatis menyambung kartu yang cocok ke meja jika menyisakan >= 1 kartu buang.
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=1)
    game.wildcard_rank = "Q"

    p0 = game.players[0]
    p0.melds = [[Card.from_id("7C"), Card.from_id("8C"), Card.from_id("9C")]]
    p0.hand = [Card.from_id("10C"), Card.from_id("3S"), Card.from_id("5H")]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0

    # Tes 1: meld_from_hand dengan memilih 1 kartu 10C
    ok_meld, msg_meld = game.meld_from_hand(0, ["10C"])
    assert ok_meld, f"Gagal meld 10C ke meja: {msg_meld}"
    assert len(p0.melds) == 1
    assert [c.id for c in p0.melds[0]] == ["7C", "8C", "9C", "10C"]
    assert "10C" not in [c.id for c in p0.hand]

    # Tes 2: auto_meld_all_valid menyambung kartu 6C dari tangan ke meja
    p0.hand.append(Card.from_id("6C"))  # Tangan sekarang: 3S, 5H, 6C
    ok_auto, msg_auto = game.auto_meld_all_valid(0)
    assert ok_auto, f"Gagal auto meld menyambung 6C: {msg_auto}"
    assert [c.id for c in p0.melds[0]] == ["6C", "7C", "8C", "9C", "10C"]
    assert "6C" not in [c.id for c in p0.hand]
    assert len(p0.hand) == 2  # 3S, 5H tersisa

    print("[PASS] Fitur nempel/menyambung kartu (layoff/extend) ke kombinasi meja Lulus 100%!")


def test_pause_resume_feature():
    """
    Memverifikasi fitur Jeda (Pause / Resume):
    - toggle_pause() dapat menjeda dan melanjutkan match.
    - to_state_dict() menyertakan field is_paused.
    """
    game = RemiGameMatch(num_players=4)
    # Di lobby, belum bisa pause
    ok_lob, _ = game.toggle_pause()
    assert not ok_lob, "Di lobby permainan belum dimulai sehingga pause tidak aktif"

    game.start_new_round(seed=1)
    assert not game.is_paused

    # Pause permainan
    ok_p, msg_p = game.toggle_pause()
    assert ok_p and game.is_paused
    assert "DIJEDA" in msg_p
    assert game.to_state_dict()["is_paused"] is True

    # Resume permainan
    ok_r, msg_r = game.toggle_pause()
    assert ok_r and not game.is_paused
    assert "DILANJUTKAN" in msg_r
    assert game.to_state_dict()["is_paused"] is False

    print("[PASS] Fitur Jeda (Pause / Resume) Lulus 100%!")


def test_discard_keeps_cards_in_hand_until_auto_meld_clicked():
    """
    Memverifikasi bahwa saat membuang kartu (bukan menutup ronde):
    Kartu kombinasi di tangan TIDAK otomatis turun ke meja!
    Kartu tetap berada di tangan pemain, menunggu pemain mengklik tombol 'Auto Turun' atau 'Turunkan Pilihan'.
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=1)
    game.wildcard_rank = "Q"

    p0 = game.players[0]
    p0.melds = []
    # Tangan pemain: Seri 7C-8C-9C-10C + kartu mati 2D + kartu yang ingin dibuang 3H
    p0.hand = [
        Card.from_id("7C"),
        Card.from_id("8C"),
        Card.from_id("9C"),
        Card.from_id("10C"),
        Card.from_id("2D"),
        Card.from_id("3H"),
    ]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0

    # Buang kartu 3H
    ok_disc, msg_disc = game.discard_card(0, "3H")
    assert ok_disc, f"Gagal buang kartu: {msg_disc}"

    # Verifikasi kartu jadi 7C-8C-9C-10C TETAP BERADA DI TANGAN (TIDAK otomatis turun ke meja!)
    assert len(p0.melds) == 0, "Kartu meja harusnya tetap kosong karena pemain belum klik Auto Turun!"
    hand_ids = [c.id for c in p0.hand]
    assert "7C" in hand_ids and "8C" in hand_ids and "9C" in hand_ids and "10C" in hand_ids and "2D" in hand_ids
    assert game.discard_pile[-1].id == "3H"

    # Pemain kemudian secara sadar memanggil auto_meld_all_valid:
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    ok_auto, msg_auto = game.auto_meld_all_valid(0)
    assert ok_auto
    assert len(p0.melds) == 1
    assert [c.id for c in p0.melds[0]] == ["7C", "8C", "9C", "10C"]
    assert [c.id for c in p0.hand] == ["2D"]

    # Tes 2: Jika pemain membuang kartu terakhir dan SELURUH sisa kartu jadi (len(rem) == 0),
    # maka dan HANYA saat itu kartu otomatis turun untuk TUTUP!
    p0.hand = [Card.from_id("5S"), Card.from_id("5H"), Card.from_id("5D"), Card.from_id("KD")]
    ok_close, _ = game.discard_card(0, "KD")
    assert ok_close
    assert len(p0.hand) == 0, "Harusnya menutup ronde karena seluruh kartu jadi!"
    assert any([c.id for c in m] == ["5S", "5H", "5D"] for m in p0.melds)

    print("[PASS] Kartu di tangan TIDAK otomatis turun saat buang biasa (menunggu klik Auto Turun) Lulus 100%!")


def test_pure_tutup_tangan_freezes_other_players_scores_to_zero():
    """
    Aturan Baru:
    Jika Tutup Tangan Murni (+250):
    1. Pemain yang menutup mendapat skor murni +250 Poin.
    2. Nilai pemain lain TIDAK DIHITUNG baik minus atau plus (skor ronde = 0 Poin),
       karena ronde dihentikan seketika dan pemain lain tidak sempat menyelesaikan permainan.
    """
    game = RemiGameMatch(num_players=4)
    game.start_new_round(seed=123)
    game.wildcard_rank = "9"

    # Set initial scores
    game.players[0].total_score = 100
    game.players[1].total_score = 80
    game.players[2].total_score = 50
    game.players[3].total_score = 30

    # Player 1 punya kartu mati tanpa seri (seharusnya terbakar jika Tutup Biasa)
    game.players[1].melds = []
    game.players[1].hand = [Card.from_id("KH"), Card.from_id("QD"), Card.from_id("JC")]

    # Player 2 punya seri sah yang harusnya menghasilkan poin plus
    game.players[2].melds = [[Card.from_id("4S"), Card.from_id("5S"), Card.from_id("6S")]]
    game.players[2].hand = []

    # Player 3 punya kombinasi biasa
    game.players[3].melds = []
    game.players[3].hand = [Card.from_id("2H"), Card.from_id("3H")]

    # Player 0 siap Tutup Tangan Murni
    p0 = game.players[0]
    p0.melds = []
    p0.hand = [
        Card.from_id("3S"),
        Card.from_id("4S"),
        Card.from_id("5S"),
        Card.from_id("6S"),
        Card.from_id("AS"),
        Card.from_id("AH"),
        Card.from_id("AD"),
        Card.from_id("KC"),
    ]
    game.phase = "TURN_MELD_DISCARD"
    game.current_turn_seat = 0
    game.melds_count_at_turn_start = 0

    ok_tt, msg_tt = game.declare_tutup_tangan(0, "KC")
    assert ok_tt, f"Tutup Tangan harus berhasil: {msg_tt}"
    assert game.phase == "ROUND_OVER"

    # Player 0 mendapat +250
    assert p0.last_round_score == TUTUP_TANGAN_BONUS, f"P0 last round harus +250, got {p0.last_round_score}"
    assert p0.total_score == 100 + TUTUP_TANGAN_BONUS, f"P0 total score harus 350, got {p0.total_score}"

    # Pemain lain skor ronde HARUS 0 (tidak minus dan tidak plus), dan total score tidak berubah!
    for seat in (1, 2, 3):
        p = game.players[seat]
        assert p.last_round_score == 0, f"Pemain {p.name} skor ronde harus 0, got {p.last_round_score}"
        assert not p.burned_last_round, f"Pemain {p.name} tidak boleh berstatus terbakar saat Tutup Tangan Murni!"
        bd = p.last_round_breakdown
        assert bd["round_net"] == 0, f"Breakdown round_net harus 0, got {bd['round_net']}"
        assert bd["meld_points"] == 0, f"Breakdown meld_points harus 0, got {bd['meld_points']}"
        assert bd["dead_penalty"] == 0, f"Breakdown dead_penalty harus 0, got {bd['dead_penalty']}"

    assert game.players[1].total_score == 80, f"P1 total score harus tetap 80, got {game.players[1].total_score}"
    assert game.players[2].total_score == 50, f"P2 total score harus tetap 50, got {game.players[2].total_score}"
    assert game.players[3].total_score == 30, f"P3 total score harus tetap 30, got {game.players[3].total_score}"

    print("[PASS] Tutup Tangan Murni membekukan skor pemain lain menjadi 0 (tidak dihitung plus/minus) Lulus 100%!")


if __name__ == "__main__":
    test_deck_53_and_4_wildcards_from_first_card()
    test_3_tier_separation_rules()
    test_mandatory_seri_min_3_or_burn_all()
    test_feature_2_reverted_auto_meld_and_tutup_tangan_250()
    test_take_discard_for_tris_requires_seri_first_and_ace_exception()
    test_tutup_biasa_discard_times_wildcard()
    test_tris_ace_can_meld_without_seri_and_saves_from_burn()
    test_feeder_penalty_x10_when_discard_is_taken_to_close()
    test_drag_and_drop_reorder_hand()
    test_tutup_tangan_with_single_ace_and_two_wildcards()
    test_taking_discard_avoids_consuming_wildcard_from_hand()
    test_highest_score_player_starts_and_main_terus()
    test_dashboard_match_configuration_and_timer_settings()
    test_auto_next_round_countdown_5_seconds()
    test_closing_after_taking_discard_is_not_250_but_tutup_biasa()
    test_discarded_wildcards_cannot_be_taken_by_other_players()
    test_take_discard_forms_full_sequence_7_to_10()
    test_extend_and_layoff_cards_to_table_melds()
    test_pause_resume_feature()
    test_discard_keeps_cards_in_hand_until_auto_meld_clicked()
    test_pure_tutup_tangan_freezes_other_players_scores_to_zero()
    print("\nSEMUA UNIT TEST REMI INDONESIA v3.4 LULUS 100%!")
