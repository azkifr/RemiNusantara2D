"""
Remi Nusantara 2D - Core Rule Engine & AI Bot (v2.4)
Implementasi penuh aturan PRD terbaru:
1. Maksimal 4 Pemain, 7 Kartu awal di tangan.
2. Deck 53 Kartu & 4 Wild Card (1 Joker + 3 Kartu Bukaan Pertama):
   - Saat ronde dimulai (setelah 7 kartu dibagikan ke tiap pemain), 1 kartu standar dibuka
     dari Pak sebagai KARTU BUKAAN WILDCARD (misal: 6 Hati).
   - Maka 3 kartu angka 6 lainnya (6 Waru, 6 Wajik, 6 Keriting) + 1 Kartu JOKER menjadi
     4 WILD CARD (pengganti kartu apa saja dalam 1 kelompok).
3. Pemisahan 3 Kelompok Kartu (Number 2-10, Face J-Q-K, Ace A berdiri sendiri):
   - Number (2..10): +5/-5 poin. Seri hanya sesama 2..10 sekembang, atau Tris angka sama.
   - Face Card (J, Q, K): +10/-10 poin. Seri hanya J-Q-K sekembang, atau Tris huruf sama.
   - Kartu As (A): +15/-15 poin. Berdiri sendiri (hanya Tris/Kuartet sesama A).
   - Wild Card (1 Joker + 3 Kartu Bukaan): Mengikuti nilai kelompok yang digantikan; jika mati/terbakar = -25 poin.
4. Aturan Wajib Kartu Urut (Seri Min 3 Kartu) — Jika Tidak Punya, TERBAKAR SEMUA:
   - Saat permainan/ronde berakhir, pemain yang TIDAK memiliki minimal 1 kombinasi Kartu Urut (Seri min 3 kartu)
     TIDAK mendapatkan poin positif sama sekali (0 poin jadi) dan SEMUA kartunya (baik Tris yang sudah turun
     maupun kartu di tangan) menjadi TERBAKAR (dihitung minus semuanya).
5. Ambil Buangan (Maks 7 Kartu Teratas) & Auto-Meld Kembali Seperti Semula:
   - Klik kartu buangan langsung mengambil kartu & otomatis menurunkan kombinasi wajib ke meja.
   - Tombol AUTO TURUN (A) tersedia kembali.
   - Saat buang kartu terakhir, jika sisa kartu di tangan sudah jadi semua (dan punya minimal 1 Seri):
     * Jika belum pernah menurunkan Kartu Jadi sebelumnya -> TUTUP TANGAN (+250 Poin).
     * Jika sudah ada Kartu Jadi di meja sebelumnya -> Tutup Biasa (+0 bonus tutup, hanya poin Kartu Jadi).
6. Target Skor Kemenangan Match = 1.500 Poin.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from itertools import combinations
from typing import List, Optional, Tuple, Dict

SUITS = ["S", "H", "D", "C"]
SUIT_SYMBOLS = {"S": "-Waru", "H": "-Hati", "D": "-Wajik", "C": "-Krtg", "J": ""}
SUIT_NAMES_ID = {"S": "Waru", "H": "Hati", "D": "Wajik", "C": "Keriting", "J": "Joker"}

NUMBER_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10"]
FACE_RANKS = ["J", "Q", "K"]
ACE_RANKS = ["A"]
ALL_STANDARD_RANKS = NUMBER_RANKS + FACE_RANKS + ACE_RANKS

RANK_ORDER = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    "J": 11, "Q": 12, "K": 13, "A": 14, "JOKER": 99
}

TARGET_WIN_SCORE = 1500
TUTUP_TANGAN_BONUS = 250
MAX_DISCARD_TAKE_DEPTH = 7
INITIAL_HAND_SIZE = 7
MAX_PLAYERS = 4


@dataclass(frozen=True)
class Card:
    id: str          # "2S", "10H", "KD", "AC", "JOKER"
    rank: str        # "2".."10", "J", "Q", "K", "A", "JOKER"
    suit: str        # "S", "H", "D", "C", atau "J"

    @property
    def is_joker(self) -> bool:
        return self.rank == "JOKER"

    def is_wildcard(self, wildcard_rank: Optional[str] = None) -> bool:
        """True jika kartu ini adalah Joker murni ATAU satu dari 3 kartu se-angka Kartu Bukaan."""
        if self.is_joker:
            return True
        if wildcard_rank and self.rank == wildcard_rank:
            return True
        return False

    @property
    def group(self) -> str:
        if self.is_joker:
            return "JOKER"
        if self.rank in NUMBER_RANKS:
            return "NUMBER"
        if self.rank in FACE_RANKS:
            return "FACE"
        return "ACE"

    @property
    def base_points(self) -> int:
        if self.is_joker:
            return 25
        if self.rank in NUMBER_RANKS:
            return 5
        if self.rank in FACE_RANKS:
            return 10
        return 15

    def get_deadwood_penalty(self, wildcard_rank: Optional[str] = None) -> int:
        if self.is_wildcard(wildcard_rank):
            return 25
        return self.base_points

    @property
    def deadwood_penalty(self) -> int:
        return self.base_points

    @property
    def label(self) -> str:
        if self.is_joker:
            return "JOKER"
        return f"{self.rank}{SUIT_SYMBOLS[self.suit]}"

    def sort_key(self) -> Tuple[int, int]:
        suit_idx = {"S": 0, "H": 1, "D": 2, "C": 3, "J": 4}.get(self.suit, 9)
        return (RANK_ORDER.get(self.rank, 99), suit_idx)

    def to_dict(self, wildcard_rank: Optional[str] = None) -> dict:
        return {
            "id": self.id,
            "rank": self.rank,
            "suit": self.suit,
            "label": self.label,
            "is_wild": self.is_wildcard(wildcard_rank),
        }

    @staticmethod
    def from_id(card_id: str) -> "Card":
        if card_id == "JOKER":
            return Card(id="JOKER", rank="JOKER", suit="J")
        suit = card_id[-1]
        rank = card_id[:-1]
        return Card(id=card_id, rank=rank, suit=suit)


def create_deck_53(seed: Optional[int] = None) -> List[Card]:
    deck: List[Card] = []
    for suit in SUITS:
        for rank in ALL_STANDARD_RANKS:
            deck.append(Card(id=f"{rank}{suit}", rank=rank, suit=suit))
    deck.append(Card(id="JOKER", rank="JOKER", suit="J"))
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck


@dataclass
class MeldValidationResult:
    valid: bool
    meld_type: str = ""      # "SERI_NUMBER", "SERI_FACE", "TRIS_NUMBER", "TRIS_FACE", "TRIS_ACE"
    group: str = ""          # "NUMBER", "FACE", "ACE"
    points: int = 0
    reason: str = ""
    ordered_cards: List[Card] = field(default_factory=list)
    wildcards_as_substitute: int = 0

    @property
    def is_seri(self) -> bool:
        return self.meld_type.startswith("SERI_")


def validate_meld(cards: List[Card], wildcard_rank: Optional[str] = None) -> MeldValidationResult:
    """
    Memvalidasi kombinasi kartu (minimal 3 kartu) dengan dukungan 4 Wild Card:
    - 1 kartu JOKER + 3 kartu yang memiliki `rank == wildcard_rank`.
    - Tetap menjaga pemisahan Number (2-10), Face (J-Q-K), dan Ace (A berdiri sendiri).
    - Jika kartu `rank == wildcard_rank` berada di kembang & urutan aslinya dalam Seri
      (sebagai regular card dengan serinya), kartu tersebut diperlakukan sebagai kartu
      reguler di posisi urutannya (wildcards_as_substitute = 0).
    """
    if len(cards) < 3:
        return MeldValidationResult(False, reason="Kombinasi minimal harus 3 kartu.")

    raw_wilds = [c for c in cards if c.is_wildcard(wildcard_rank)]
    raw_normals = [c for c in cards if not c.is_wildcard(wildcard_rank)]

    # Jika semuanya adalah Wildcard (misal 3 Wildcard dikumpulkan jadi Tris Wildcard)
    if not raw_normals:
        if len(cards) <= 4:
            pts = len(cards) * 15
            return MeldValidationResult(
                valid=True,
                meld_type="TRIS_ACE",
                group="ACE",
                points=pts,
                reason=f"Tris Wildcard sah (+{pts} poin)",
                ordered_cards=list(cards),
                wildcards_as_substitute=len(cards),
            )
        return MeldValidationResult(False, reason="Kombinasi khusus Wildcard maksimal 4 kartu.")

    groups = {c.group for c in raw_normals}
    if len(groups) > 1:
        return MeldValidationResult(
            False,
            reason="Kartu Angka (2-10), Face Card (J-Q-K), dan As (A) tidak boleh digabung!"
        )

    group = raw_normals[0].group
    group_point_per_card = {"NUMBER": 5, "FACE": 10, "ACE": 15}[group]
    total_points = len(cards) * group_point_per_card

    # Cek apakah ada Rank-Wildcard yang berfungsi sebagai REGULAR CARD pada kembang & urutan Seri-nya
    wilds = list(raw_wilds)
    normals = list(raw_normals)
    if (
        group in ("NUMBER", "FACE")
        and len({c.suit for c in raw_normals}) == 1
        and len({c.rank for c in raw_normals}) == len(raw_normals)
    ):
        target_suit = raw_normals[0].suit
        matching_rw = [
            c for c in raw_wilds
            if not c.is_joker and c.group == group and c.suit == target_suit
        ]
        if matching_rw:
            rw = matching_rw[0]
            cand_normals = sorted(raw_normals + [rw], key=lambda c: RANK_ORDER[c.rank])
            cand_wilds = [c for c in raw_wilds if c.id != rw.id]
            r_vals = [RANK_ORDER[c.rank] for c in cand_normals]
            span = r_vals[-1] - r_vals[0] + 1
            gaps = span - len(cand_normals)
            valid_len = (len(cards) == 3) if group == "FACE" else (len(cards) <= 9)
            if valid_len and gaps <= len(cand_wilds):
                normals = cand_normals
                wilds = cand_wilds

    # 1. Cek TRIS / KUARTET (Sama Rank, Beda Suit, atau 1 Kartu Asli + Wildcard)
    ranks = {c.rank for c in normals}
    suits = [c.suit for c in normals]
    if len(ranks) == 1 and len(cards) <= 4 and len(set(suits)) == len(suits):
        ordered = sorted(normals, key=lambda c: c.sort_key()) + wilds
        return MeldValidationResult(
            valid=True,
            meld_type=f"TRIS_{group}",
            group=group,
            points=total_points,
            reason=f"Tris {group} sah (+{total_points} poin)",
            ordered_cards=ordered,
            wildcards_as_substitute=len(wilds),
        )

    # 2. Cek SERI / KARTU URUT SEKEMBANG (Minimal 2 kartu asli untuk menentukan urutan & kembang)
    if len(normals) < 2:
        return MeldValidationResult(
            False,
            reason="Kombinasi Seri (Kartu Urut) membutuhkan minimal 2 kartu asli untuk menentukan urutan."
        )
    if group == "ACE":
        return MeldValidationResult(
            False,
            reason="Kartu As (A) berdiri sendiri dan hanya bisa dikombinasikan sesama As (Tris/Kuartet A)."
        )

    if len(set(suits)) != 1:
        return MeldValidationResult(
            False,
            reason="Kombinasi Seri (Urut) harus memiliki kembang (suit) yang sama."
        )

    if len(ranks) != len(normals):
        return MeldValidationResult(False, reason="Kombinasi Seri tidak boleh memiliki angka kembar.")

    sorted_normals = sorted(normals, key=lambda c: RANK_ORDER[c.rank])
    rank_values = [RANK_ORDER[c.rank] for c in sorted_normals]

    if group == "FACE":
        if len(cards) != 3:
            return MeldValidationResult(False, reason="Seri Face Card hanya berlaku untuk 3 kartu (J-Q-K).")
        span = rank_values[-1] - rank_values[0] + 1
        gaps = span - len(normals)
        if gaps <= len(wilds):
            ordered = _build_ordered_run(sorted_normals, wilds, 11, 13)
            return MeldValidationResult(
                valid=True,
                meld_type="SERI_FACE",
                group="FACE",
                points=total_points,
                reason=f"Seri Face Card (J-Q-K) sah (+{total_points} poin)",
                ordered_cards=ordered,
                wildcards_as_substitute=len(wilds),
            )
        return MeldValidationResult(False, reason="Urutan Face Card tidak berurutan.")

    if group == "NUMBER":
        if len(cards) > 9:
            return MeldValidationResult(False, reason="Seri Number Card maksimal 9 kartu (2 s/d 10).")
        span = rank_values[-1] - rank_values[0] + 1
        gaps = span - len(normals)
        if gaps <= len(wilds):
            ordered = _build_ordered_run(sorted_normals, wilds, 2, 10)
            return MeldValidationResult(
                valid=True,
                meld_type="SERI_NUMBER",
                group="NUMBER",
                points=total_points,
                reason=f"Seri Angka sah (+{total_points} poin)",
                ordered_cards=ordered,
                wildcards_as_substitute=len(wilds),
            )
        return MeldValidationResult(False, reason="Kartu angka tidak berurutan.")

    return MeldValidationResult(False, reason="Kombinasi tidak valid.")


def _build_ordered_run(sorted_normals: List[Card], wilds: List[Card], min_val: int, max_val: int) -> List[Card]:
    if not wilds:
        return sorted_normals
    rem_wilds = list(wilds)
    result: List[Card] = [sorted_normals[0]]
    for i in range(1, len(sorted_normals)):
        prev_v = RANK_ORDER[sorted_normals[i - 1].rank]
        curr_v = RANK_ORDER[sorted_normals[i].rank]
        gap = curr_v - prev_v - 1
        while gap > 0 and rem_wilds:
            result.append(rem_wilds.pop(0))
            gap -= 1
        result.append(sorted_normals[i])
    cur_top = RANK_ORDER[sorted_normals[-1].rank]
    cur_bot = RANK_ORDER[sorted_normals[0].rank]
    while rem_wilds:
        if cur_top < max_val:
            result.append(rem_wilds.pop(0))
            cur_top += 1
        elif cur_bot > min_val:
            result.insert(0, rem_wilds.pop(0))
            cur_bot -= 1
        else:
            result.append(rem_wilds.pop(0))
    return result


def has_valid_seri_meld(melds: List[List[Card]], wildcard_rank: Optional[str] = None) -> bool:
    """Mengecek apakah daftar kombinasi memiliki minimal 1 Kartu Urut / Seri (minimal 3 kartu)."""
    for m in melds:
        res = validate_meld(m, wildcard_rank=wildcard_rank)
        if res.valid and res.is_seri and len(m) >= 3:
            return True
    return False


def has_valid_seri_or_ace_meld(melds: List[List[Card]], wildcard_rank: Optional[str] = None) -> bool:
    """
    Mengecek apakah daftar kombinasi memiliki minimal 1 Kartu Urut / Seri (minimal 3 kartu)
    ATAU minimal 1 kombinasi Tris/Kuartet As (A-A-A / A-A-A-A).
    Keduanya memberikan status AMAN dari penalti terbakar dan membuka izin turun Tris lainnya!
    """
    for m in melds:
        res = validate_meld(m, wildcard_rank=wildcard_rank)
        if res.valid and (res.is_seri or res.meld_type in ("TRIS_ACE", "KUARTET_ACE")) and len(m) >= 3:
            return True
    return False


def find_best_melds_in_hand(
    hand: List[Card],
    must_include: Optional[Card] = None,
    wildcard_rank: Optional[str] = None,
    already_has_seri: bool = False,
) -> Tuple[List[List[Card]], List[Card]]:
    """
    Mencari susunan kombinasi sah terbaik dari kartu di tangan, dengan memprioritaskan
    terbentuknya minimal 1 Kartu Urut (Seri min 3 kartu) agar pemain tidak terbakar!
    """
    candidate_melds: List[Tuple[int, bool, List[Card]]] = []
    n = len(hand)
    max_sz = min(n, 7)
    for sz in range(3, max_sz + 1):
        for comb in combinations(hand, sz):
            comb_list = list(comb)
            res = validate_meld(comb_list, wildcard_rank=wildcard_rank)
            if res.valid:
                saved_deadwood = sum(c.get_deadwood_penalty(wildcard_rank) for c in comb_list)
                # Wild Card sangat berharga untuk disimpan di tangan (fleksibilitas & potensi Tutup Tangan).
                # Beri penalti jika mengonsumsi Wild Card agar kombinasi natural (0 Wild Card) selalu diprioritaskan!
                wildcard_cost = sum(50 for c in comb_list if c.is_wildcard(wildcard_rank))
                score_gain = res.points + saved_deadwood - wildcard_cost
                candidate_melds.append((score_gain, res.is_seri, res.ordered_cards))

    best_score = -999999
    best_melds: List[List[Card]] = []
    best_remaining: List[Card] = list(hand)

    def backtrack(idx: int, used_ids: set, current_melds: List[List[Card]], has_seri_now: bool):
        nonlocal best_score, best_melds, best_remaining
        if must_include is not None:
            has_required = any(must_include.id in {c.id for c in m} for m in current_melds)
        else:
            has_required = True

        if has_required:
            meld_pts = sum(validate_meld(m, wildcard_rank=wildcard_rank).points for m in current_melds)
            rem = [c for c in hand if c.id not in used_ids]
            dead_pts = sum(c.get_deadwood_penalty(wildcard_rank) for c in rem)
            
            # Mendukung Seri Urut ATAU Tris As sebagai pembuka sah
            has_opener = has_seri_now or already_has_seri or any(
                validate_meld(m, wildcard_rank=wildcard_rank).is_seri or
                validate_meld(m, wildcard_rank=wildcard_rank).meld_type in ("TRIS_ACE", "KUARTET_ACE")
                for m in current_melds
            )
            opener_bonus = 500 if has_opener else 0

            # Prioritas tertinggi: Tutup tangan lengkap (0 kartu sisa = 5000 poin bonus)
            if len(rem) == 0 and len(current_melds) > 0 and has_opener:
                close_bonus = 5000
            elif len(rem) == 1 and len(current_melds) > 0 and has_opener:
                close_bonus = 1000
            else:
                close_bonus = 0

            # Wildcard penalty hanya saat TIDAK menutup tangan (len(rem) > 1).
            # Saat kartu bisa ditutup lengkap (len(rem) <= 1), wildcard harus digunakan maksimal!
            wildcards_in_melds = sum(1 for m in current_melds for c in m if c.is_wildcard(wildcard_rank))
            wc_pen = (wildcards_in_melds * 10) if len(rem) > 1 else 0
            net = meld_pts - dead_pts + opener_bonus + close_bonus - wc_pen
            if net > best_score:
                best_score = net
                best_melds = [list(m) for m in current_melds]
                best_remaining = rem

        for i in range(idx, len(candidate_melds)):
            _, is_s, m_cards = candidate_melds[i]
            m_ids = {c.id for c in m_cards}
            if m_ids.isdisjoint(used_ids):
                backtrack(i + 1, used_ids | m_ids, current_melds + [m_cards], has_seri_now or is_s)

    backtrack(0, set(), [], False)
    return best_melds, best_remaining


@dataclass
class PlayerState:
    seat: int
    name: str
    is_bot: bool = False
    is_ready: bool = True
    connected: bool = True
    afk_strikes: int = 0
    auto_pilot: bool = False
    player_id: str = ""
    last_seen: float = 0.0
    hand: List[Card] = field(default_factory=list)
    melds: List[List[Card]] = field(default_factory=list)
    total_score: int = 0
    last_round_score: int = 0
    burned_last_round: bool = False
    last_round_breakdown: Dict[str, int] = field(default_factory=dict)

    def sort_hand(self, by_suit: bool = False):
        if by_suit:
            suit_order = {"S": 0, "H": 1, "D": 2, "C": 3, "J": 4}
            self.hand.sort(key=lambda c: (suit_order.get(c.suit, 9), RANK_ORDER.get(c.rank, 99)))
        else:
            self.hand.sort(key=lambda c: c.sort_key())

    def reorder_hand(self, source_cid: str, target_cid: str) -> bool:
        """Memindahkan posisi kartu source_cid ke posisi target_cid untuk fitur drag and drop kartu di tangan."""
        if source_cid == target_cid:
            return False
        src_idx = next((i for i, c in enumerate(self.hand) if c.id == source_cid), None)
        tgt_idx = next((i for i, c in enumerate(self.hand) if c.id == target_cid), None)
        if src_idx is None or tgt_idx is None:
            return False
        card = self.hand.pop(src_idx)
        tgt_idx = next((i for i, c in enumerate(self.hand) if c.id == target_cid), None)
        if tgt_idx is None:
            self.hand.append(card)
        else:
            self.hand.insert(tgt_idx, card)
        return True


class RemiGameMatch:
    """
    State Machine penuh untuk 1 meja permainan Remi Nusantara (Maksimal 4 Pemain, Target 1500 Poin).
    """

    def __init__(
        self,
        room_code: str = "RM1500",
        num_players: int = 4,
        turn_timer_sec: int = 25,
        target_score: int = TARGET_WIN_SCORE,
        bot_delay_sec: float = 0.85,
    ):
        self.room_code = room_code
        self.max_players = min(max(2, num_players), MAX_PLAYERS)
        self.turn_timer_sec = max(0, turn_timer_sec)
        self.target_score = max(100, target_score)
        self.bot_delay_sec = max(0.2, min(3.0, bot_delay_sec))

        self.players: List[PlayerState] = [
            PlayerState(seat=0, name="Anda (Player 1)", is_bot=False, is_ready=True),
            PlayerState(seat=1, name="Bot Budi", is_bot=True, is_ready=True),
            PlayerState(seat=2, name="Bot Siti", is_bot=True, is_ready=True),
            PlayerState(seat=3, name="Bot Agus", is_bot=True, is_ready=True),
        ][:self.max_players]

        self.round_number: int = 0
        self.starter_seat: int = 0
        self.current_turn_seat: int = 0
        self.phase: str = "LOBBY"
        self.draw_pile: List[Card] = []
        self.discard_pile: List[Card] = []
        # Kartu Bukaan Pertama saat ronde dimulai (menentukan 3 kartu se-angka sebagai Wildcard!)
        self.wildcard_indicator_card: Optional[Card] = None
        self.wildcard_rank: Optional[str] = None
        self.forbidden_discard_card_id: Optional[str] = None
        self.melds_count_at_turn_start: int = 0
        self.round_closer_seat: Optional[int] = None
        self.last_round_closer_seat: Optional[int] = None  # Pemain terakhir yang berhasil tutup tangan
        self.highest_score_seat: int = 0  # Pemain dengan total skor tertinggi yang memegang hak mulai (main terus)
        self.round_over_timer: Optional[float] = None
        self.round_closed_by_tutup_tangan: bool = False
        self.match_winner_seat: Optional[int] = None
        self.status_message: str = "Di Dashboard / Lobby - Atur konfigurasi & klik 'MULAI PERMAINAN'!"
        self.turn_remaining_sec: float = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        self.is_paused: bool = False
        # Pelacakan kartu buangan dan pembuangnya (untuk penalti umpan tutup x10)
        self.card_discarder: Dict[str, int] = {}
        self.turn_taken_discard_card: Optional[Card] = None
        self.turn_taken_discarder_seat: Optional[int] = None
        self.must_close_this_turn: bool = False

    def configure_match(
        self,
        num_players: Optional[int] = None,
        turn_timer_sec: Optional[int] = None,
        target_score: Optional[int] = None,
        player_name: Optional[str] = None,
        bot_delay_sec: Optional[float] = None,
    ) -> dict:
        """Mengatur konfigurasi meja dari Dashboard sebelum atau saat bermain."""
        if target_score is not None:
            self.target_score = max(100, int(target_score))
        if turn_timer_sec is not None:
            self.turn_timer_sec = max(0, int(turn_timer_sec))
            self.turn_remaining_sec = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        if bot_delay_sec is not None:
            self.bot_delay_sec = max(0.2, min(3.0, float(bot_delay_sec)))
        if num_players is not None:
            n = min(max(2, int(num_players)), MAX_PLAYERS)
            self.max_players = n
            default_names = ["Anda (Player 1)", "Bot Budi", "Bot Siti", "Bot Agus"]
            if player_name:
                default_names[0] = player_name
            new_players = []
            for seat in range(n):
                if seat < len(self.players):
                    p = self.players[seat]
                    if seat == 0 and player_name:
                        p.name = player_name
                    new_players.append(p)
                else:
                    new_players.append(
                        PlayerState(seat=seat, name=default_names[seat], is_bot=True, is_ready=True)
                    )
            self.players = new_players
        elif player_name and len(self.players) > 0:
            self.players[0].name = player_name

        timer_txt = f"{self.turn_timer_sec}s" if self.turn_timer_sec > 0 else "Unlimited"
        self.status_message = (
            f"Pengaturan Dashboard Disimpan: {len(self.players)} Pemain | "
            f"Waktu: {timer_txt} | Target: {self.target_score} Poin."
        )
        return {
            "num_players": len(self.players),
            "turn_timer_sec": self.turn_timer_sec,
            "target_score": self.target_score,
            "player_name": self.players[0].name if self.players else "Anda",
            "bot_delay_sec": self.bot_delay_sec,
        }

    def reset_match(self):
        """Mereset skor dan memulai pertandingan baru dari Ronde 1."""
        for p in self.players:
            p.total_score = 0
            p.hand = []
            p.melds = []
            p.last_round_score = 0
            p.burned_last_round = False
            p.last_round_breakdown = {}
        self.round_number = 0
        self.starter_seat = 0
        self.highest_score_seat = 0
        self.round_over_timer = None
        self.current_turn_seat = 0
        self.last_round_closer_seat = None
        self.round_closer_seat = None
        self.round_closed_by_tutup_tangan = False
        self.match_winner_seat = None
        self.draw_pile = []
        self.discard_pile = []
        self.phase = "LOBBY"
        self.is_paused = False
        self.status_message = "Match di-reset. Siap bermain dari Ronde 1!"

    def toggle_pause(self) -> Tuple[bool, str]:
        """Menjeda atau melanjutkan permainan (pause/resume)."""
        if self.phase == "LOBBY":
            return False, "Permainan belum dimulai."
        self.is_paused = not getattr(self, "is_paused", False)
        if self.is_paused:
            self.status_message = "⏸️ PERMAINAN DIJEDA (PAUSED). Timer dan giliran bot dihentikan sementara."
        else:
            self.status_message = "▶️ PERMAINAN DILANJUTKAN (RESUMED)."
        return True, self.status_message

    def is_wildcard(self, card: Card) -> bool:
        return card.is_wildcard(self.wildcard_rank)

    # ------------------------------------------------------------------
    # Siklus Ronde, Pembagian 7 Kartu, & Pembukaan Kartu Wildcard Pertama
    # ------------------------------------------------------------------
    def start_new_round(self, seed: Optional[int] = None):
        if self.phase == "MATCH_OVER":
            for p in self.players:
                p.total_score = 0
            self.round_number = 0
            self.match_winner_seat = None
            self.last_round_closer_seat = None
            self.starter_seat = 0
            self.highest_score_seat = 0

        self.round_number += 1
        self.round_over_timer = None
        self.is_paused = False
        # Aturan Baru: Pemain yang memiliki skor total tertinggi yang seharusnya main terus menerus (mulai pertama di setiap ronde)!
        if self.round_number == 1:
            self.starter_seat = 0
            self.highest_score_seat = 0
        else:
            highest_score = max(p.total_score for p in self.players)
            leaders = [p for p in self.players if p.total_score == highest_score]
            if not any(p.seat == self.starter_seat for p in leaders):
                self.starter_seat = leaders[0].seat
            self.highest_score_seat = self.starter_seat

        self.draw_pile = create_deck_53(seed)
        self.discard_pile = []
        self.card_discarder = {}
        self.turn_taken_discard_card = None
        self.turn_taken_discarder_seat = None
        self.must_close_this_turn = False
        self.forbidden_discard_card_id = None
        self.round_closer_seat = None
        self.round_closed_by_tutup_tangan = False

        for p in self.players:
            p.hand = []
            p.melds = []
            p.last_round_score = 0
            p.burned_last_round = False
            p.last_round_breakdown = {}

        # Bagikan 7 kartu ke setiap pemain
        for _ in range(INITIAL_HAND_SIZE):
            for p in self.players:
                p.hand.append(self.draw_pile.pop())

        # Buka 1 kartu pertama dari Pak sebagai penentu 3 Wildcard tambahan!
        # Jika kebetulan yang terambil adalah JOKER murni, masukkan kembali ke tengah pak dan ambil kartu standar.
        opened = self.draw_pile.pop()
        if opened.is_joker and self.draw_pile:
            self.draw_pile.insert(len(self.draw_pile) // 2, opened)
            opened = self.draw_pile.pop()
        self.wildcard_indicator_card = opened
        self.wildcard_rank = opened.rank

        for p in self.players:
            p.sort_hand(by_suit=False)

        self.current_turn_seat = self.starter_seat
        self.melds_count_at_turn_start = len(self.players[self.current_turn_seat].melds)
        self.phase = "TURN_DRAW"
        self.turn_remaining_sec = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        cur_p = self.players[self.current_turn_seat]
        closer_suffix = ""
        if self.round_number > 1:
            closer_suffix = f" [Pembuka Ronde: {cur_p.name} - Pemimpin Skor ({cur_p.total_score} Poin) (MAIN TERUS)]"
        elif self.last_round_closer_seat is not None:
            closer_suffix = f" [Pembuka Ronde: {cur_p.name} - Penutup Ronde Lalu]"
        self.status_message = (
            f"Ronde {self.round_number} dimulai! Kartu Bukaan: {opened.id} "
            f"(3 kartu '{opened.rank}' lainnya + 1 JOKER = 4 WILD CARD!).{closer_suffix} Giliran {cur_p.name}."
        )

    # ------------------------------------------------------------------
    # Tahap 1: Ambil Kartu dari Pak (Draw Pile)
    # ------------------------------------------------------------------
    def draw_from_deck(self, seat: int) -> Tuple[bool, str]:
        if self.phase != "TURN_DRAW" or seat != self.current_turn_seat:
            return False, "Bukan giliran Anda untuk mengambil kartu."
        if not self.draw_pile:
            self._finish_round(closer_seat=None, is_tutup_tangan=False, reason="Pak habis!")
            return False, "Pak kartu sudah habis."

        player = self.players[seat]
        self.melds_count_at_turn_start = len(player.melds)
        self.turn_taken_discard_card = None
        self.turn_taken_discarder_seat = None
        self.must_close_this_turn = False
        card = self.draw_pile.pop()
        player.hand.append(card)
        self.forbidden_discard_card_id = None
        self.phase = "TURN_MELD_DISCARD"
        self.turn_remaining_sec = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        wild_tag = " [WILD CARD!]" if card.is_wildcard(self.wildcard_rank) else ""
        self.status_message = (
            f"{player.name} mengambil {card.id}{wild_tag} dari Pak. Silakan susun/turunkan atau buang 1 kartu."
        )
        return True, self.status_message

    def _can_close_with_remaining_pool(
        self,
        existing_melds: List[List[Card]],
        new_meld: Optional[List[Card]],
        rem_pool: List[Card],
        forbidden_discard_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Mengecek apakah sisa kartu `rem_pool` (setelah `new_meld` diturunkan bersama `existing_melds`)
        memungkinkan pemain langsung MENUTUP KARTU pada giliran ini (menyisakan tepat 1 kartu buang
        dan seluruh kartu lainnya jadi kombinasi sah dengan minimal 1 Seri / Tris As).
        """
        if not rem_pool:
            return False, None

        base_melds = [list(m) for m in existing_melds]
        if new_meld is not None:
            base_melds.append(list(new_meld))

        already_safe = has_valid_seri_or_ace_meld(base_melds, self.wildcard_rank)
        valid_closing_discards: List[Tuple[bool, int, str]] = []

        for cand_disc in rem_pool:
            if forbidden_discard_id and cand_disc.id == forbidden_discard_id:
                continue
            other_cards = [c for c in rem_pool if c.id != cand_disc.id]
            if not other_cards:
                if base_melds and already_safe:
                    is_wild = cand_disc.is_wildcard(self.wildcard_rank)
                    valid_closing_discards.append((is_wild, cand_disc.base_points, cand_disc.id))
                continue

            melds, rem = find_best_melds_in_hand(
                other_cards,
                wildcard_rank=self.wildcard_rank,
                already_has_seri=already_safe,
            )
            combined_melds = [list(m) for m in base_melds] + [list(m) for m in melds]
            rem_list = list(rem)
            if combined_melds and rem_list:
                changed = True
                while changed and rem_list:
                    changed = False
                    for c in list(rem_list):
                        for m_idx in range(len(combined_melds)):
                            test_m = combined_melds[m_idx] + [c]
                            val_m = validate_meld(test_m, wildcard_rank=self.wildcard_rank)
                            if val_m.valid:
                                combined_melds[m_idx] = val_m.ordered_cards
                                rem_list.remove(c)
                                changed = True
                                break

            if (
                len(rem_list) == 0
                and len(combined_melds) > 0
                and (already_safe or has_valid_seri_or_ace_meld(combined_melds, self.wildcard_rank))
            ):
                is_wild = cand_disc.is_wildcard(self.wildcard_rank)
                valid_closing_discards.append((is_wild, cand_disc.base_points, cand_disc.id))

        if valid_closing_discards:
            valid_closing_discards.sort(key=lambda x: (x[0], x[1]))
            return True, valid_closing_discards[0][2]
        return False, None

    # ------------------------------------------------------------------
    # Tahap 1 Alternatif: Ambil dari Tumpukan Buangan (Maksimal 7 Kartu)
    # ------------------------------------------------------------------
    def can_take_discard(
        self,
        seat: int,
        discard_index: int,
        allow_wildcards_from_hand: bool = False,
    ) -> Tuple[bool, str, Optional[List[Card]]]:
        if self.phase != "TURN_DRAW" or seat != self.current_turn_seat:
            return False, "Bukan tahap ambil kartu pada giliran Anda.", None
        if discard_index < 0 or discard_index >= len(self.discard_pile):
            return False, "Indeks kartu buangan tidak valid.", None

        depth_from_top = len(self.discard_pile) - discard_index
        if depth_from_top > MAX_DISCARD_TAKE_DEPTH:
            return (
                False,
                f"Maksimal hanya boleh mengambil 7 kartu dari tumpukan buangan (kartu ini urutan ke-{depth_from_top}).",
                None,
            )

        target_card = self.discard_pile[discard_index]
        taken_cards = self.discard_pile[discard_index:]

        # ATURAN KHUSUS WILDCARD:
        # Jika kartu buangan yang diambil adalah Wild Card, atau irisan kartu yang terambil
        # mengandung Wild Card, pengambilan TIDAK DIIZINKAN (Wild Card buangan tidak boleh diambil pemain lain).
        if target_card.is_wildcard(self.wildcard_rank):
            return (
                False,
                f"Kartu {target_card.id} adalah Wild Card! Wild Card yang dibuang tidak dapat diambil oleh pemain lain.",
                None,
            )
        wilds_in_taken = [c for c in taken_cards if c.is_wildcard(self.wildcard_rank)]
        if wilds_in_taken:
            return (
                False,
                f"Tumpukan buangan ini mengandung Wild Card ({wilds_in_taken[0].id})! Wild Card yang dibuang tidak dapat diambil oleh pemain lain.",
                None,
            )

        player = self.players[seat]
        if len(player.hand) < 2:
            return (
                False,
                "Minimal harus mempunyai 2 kartu di tangan untuk mengambil kartu dari tumpukan buangan!",
                None,
            )

        combined_pool = player.hand + taken_cards
        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)
        forbidden_id = target_card.id if len(taken_cards) == 1 else None

        # SYARAT UTAMA:
        # 1. Pemain wajib mempunyai MINIMAL 2 KARTU DI TANGAN (player.hand) untuk membentuk kombinasi dengan target_card
        #    (contoh: punya kartu 2 dan 3 di tangan baru bisa mengambil kartu 4 dari buangan).
        # 2. Mengambil kartu buangan dengan Wild Card:
        #    - Jika Wild Card dipakai sebagai PENGGANTI (wildcard substitute), HANYA BISA dilakukan saat pemain
        #      akan MENUTUP KARTU pada giliran ini (dan dihitung sebagai Tutup Biasa, BUKAN Tutup Tangan Murni +250).
        #    - Selain itu (saat belum menutup kartu), Wild Card di tangan HANYA bisa ikut mengambil buangan jika
        #      Wild Card tersebut berfungsi sebagai REGULAR CARD sesuai angka & kembang Seri-nya (wildcards_as_substitute == 0).
        others = list(player.hand)
        valid_candidates: List[Tuple[int, int, int, int, int, List[Card], str]] = []
        saw_wildcard_substitute_without_close = False

        for sz in range(2, min(len(others), 6) + 1):
            for comb in combinations(others, sz):
                cand = list(comb) + [target_card]
                if len(combined_pool) - len(cand) < 1:
                    continue
                res = validate_meld(cand, wildcard_rank=self.wildcard_rank)
                if not res.valid:
                    continue

                is_tris_ace = res.meld_type in ("TRIS_ACE", "KUARTET_ACE")
                if not already_safe and not res.is_seri and not is_tris_ace:
                    continue

                sub_wilds = res.wildcards_as_substitute

                # Khusus kartu As ('A') saat tidak menutup dengan wildcard: wajib minimal 2 kartu As asli di tangan
                if target_card.rank == "A" and sub_wilds == 0:
                    aces_in_comb = [c for c in comb if c.rank == "A"]
                    if len(aces_in_comb) < 2:
                        continue

                cand_ids = {c.id for c in cand}
                rem_pool = [c for c in combined_pool if c.id not in cand_ids]
                can_close_now, _ = self._can_close_with_remaining_pool(
                    player.melds,
                    res.ordered_cards,
                    rem_pool,
                    forbidden_discard_id=forbidden_id,
                )

                # Jika memakai Wild Card sebagai pengganti (bukan regular card dengan serinya),
                # WAJIB hanya boleh dilakukan saat pemain akan menutup kartu pada giliran ini!
                if sub_wilds > 0 and not can_close_now:
                    saw_wildcard_substitute_without_close = True
                    continue

                hand_cards_used = len(comb)
                meld_sz = len(cand)

                rem_melds, rem_dead = find_best_melds_in_hand(
                    rem_pool,
                    wildcard_rank=self.wildcard_rank,
                    already_has_seri=already_safe or res.is_seri or is_tris_ace,
                )
                total_meld_pts = res.points + sum(
                    validate_meld(m, wildcard_rank=self.wildcard_rank).points for m in rem_melds
                )
                total_dead_penalty = sum(
                    c.get_deadwood_penalty(self.wildcard_rank) for c in rem_dead
                )
                can_close_bonus = 1000 if can_close_now else (500 if len(rem_dead) <= 1 else 0)
                net_score = total_meld_pts - total_dead_penalty + can_close_bonus

                valid_candidates.append((
                    sub_wilds,
                    0 if can_close_now else 1,
                    -net_score,
                    -meld_sz,
                    -hand_cards_used,
                    res.ordered_cards,
                    res.meld_type,
                ))

        if not valid_candidates:
            if saw_wildcard_substitute_without_close:
                return (
                    False,
                    f"Kartu buangan {target_card.id} hanya bisa diambil dengan Wild Card saat Anda akan menutup kartu "
                    f"(Tutup Biasa), atau jika Wild Card tersebut berfungsi sebagai kartu biasa (regular card) dengan serinya!",
                    None,
                )
            if target_card.rank == "A":
                return (
                    False,
                    "Khusus kartu As ('A'), Anda minimal harus mempunyai 2 kartu As di tangan untuk mengambilnya dari buangan "
                    "(kecuali menggunakan Wild Card saat langsung menutup kartu)!",
                    None,
                )
            if not already_safe:
                return (
                    False,
                    f"Belum punya Kartu Urut (Seri min 3) atau Tris As di meja! Kartu buangan {target_card.id} hanya boleh diambil "
                    f"jika Anda minimal punya 2 kartu di tangan yang langsung membentuk Seri/Straight.",
                    None,
                )
            return (
                False,
                f"Kartu buangan {target_card.id} tidak bisa langsung menjadi kombinasi sah (minimal punya 2 kartu pasangan di tangan Anda)!",
                None,
            )

        # Prioritaskan kombinasi regular (sub_wilds == 0), lalu yang bisa langsung tutup, lalu net_score & panjang seri
        regular_candidates = [c for c in valid_candidates if c[0] == 0]
        if regular_candidates:
            regular_candidates.sort(key=lambda x: (x[1], x[2], x[3], x[4]))
            chosen = regular_candidates[0]
            seri_str = "Seri" if "SERI" in chosen[6] else chosen[6]
            return True, f"Kartu {target_card.id} dapat diambil dan langsung turun sebagai {seri_str}!", chosen[5]

        # Hanya tersisa kandidat yang menggunakan Wild Card sebagai pengganti untuk langsung MENUTUP KARTU (Tutup Biasa)
        valid_candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
        chosen = valid_candidates[0]
        return (
            True,
            f"Kartu {target_card.id} diambil dengan Wild Card untuk menutup kartu (Tutup Biasa, bukan Tutup Tangan Murni)!",
            chosen[5],
        )

    def take_from_discard(
        self,
        seat: int,
        discard_index: int,
        explicit_meld_card_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Mengambil kartu buangan (maksimal 7 kartu dari atas) dan langsung menurunkan
        kombinasi wajib ke meja (KARTU JADI).
        """
        if self.phase != "TURN_DRAW" or seat != self.current_turn_seat:
            return False, "Bukan tahap ambil kartu pada giliran Anda."
        if discard_index < 0 or discard_index >= len(self.discard_pile):
            return False, "Indeks kartu buangan tidak valid."

        player = self.players[seat]
        target_card = self.discard_pile[discard_index]
        taken_cards = self.discard_pile[discard_index:]

        # Filter explicit_meld_card_ids agar hanya menghitung kartu yang benar-benar ada di tangan pemain
        hand_id_set = {c.id for c in player.hand}
        explicit_in_hand = [
            cid for cid in (explicit_meld_card_ids or [])
            if cid in hand_id_set and cid != target_card.id
        ]
        has_explicit = len(explicit_in_hand) >= 2

        ok, msg, auto_meld = self.can_take_discard(
            seat,
            discard_index,
            allow_wildcards_from_hand=has_explicit,
        )

        # ATURAN KHUSUS WILDCARD BUANGAN (WILD MATI):
        if target_card.is_wildcard(self.wildcard_rank):
            return False, f"Kartu {target_card.id} adalah Wild Card! Wild Card yang dibuang tidak dapat diambil oleh pemain lain."
        wilds_in_taken = [c for c in taken_cards if c.is_wildcard(self.wildcard_rank)]
        if wilds_in_taken:
            return False, f"Tumpukan buangan ini mengandung Wild Card ({wilds_in_taken[0].id})! Wild Card yang dibuang tidak dapat diambil oleh pemain lain."

        combined_pool = player.hand + taken_cards
        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)
        forbidden_id = target_card.id if len(taken_cards) == 1 else None

        chosen_meld: Optional[List[Card]] = None
        if has_explicit:
            id_set = set(explicit_in_hand)
            cand_from_hand = [c for c in player.hand if c.id in id_set]
            cand = cand_from_hand + [target_card]
            val = validate_meld(cand, wildcard_rank=self.wildcard_rank)
            if val.valid:
                is_tris_ace = val.meld_type in ("TRIS_ACE", "KUARTET_ACE")
                if not already_safe and not val.is_seri and not is_tris_ace:
                    if not ok:
                        return (
                            False,
                            "Belum punya Kartu Urut (Seri min 3) atau Tris As di meja! Ambil buangan untuk Tris/Kembar 3 baru boleh setelah punya Seri / Tris As.",
                        )
                elif len(combined_pool) - len(cand) < 1:
                    if not ok:
                        return False, "Harus menyisakan minimal 1 kartu untuk dibuang."
                else:
                    sub_wilds = val.wildcards_as_substitute
                    cand_ids = {c.id for c in cand}
                    rem_pool = [c for c in combined_pool if c.id not in cand_ids]
                    can_close_now, _ = self._can_close_with_remaining_pool(
                        player.melds,
                        val.ordered_cards,
                        rem_pool,
                        forbidden_discard_id=forbidden_id,
                    )
                    if sub_wilds > 0 and not can_close_now:
                        if not ok:
                            return (
                                False,
                                f"Kartu buangan {target_card.id} hanya bisa diambil dengan Wild Card saat Anda akan menutup kartu "
                                f"(Tutup Biasa), atau jika Wild Card berfungsi sebagai kartu biasa (regular card) dengan serinya!",
                            )
                    else:
                        chosen_meld = val.ordered_cards
            elif not ok:
                return False, f"Kombinasi pilihan tidak sah: {val.reason}"

        if chosen_meld is None:
            if not ok or auto_meld is None:
                return False, msg
            chosen_meld = auto_meld

        self.melds_count_at_turn_start = len(player.melds)
        del self.discard_pile[discard_index:]
        player.hand = combined_pool
        meld_ids = {c.id for c in chosen_meld}
        player.hand = [c for c in player.hand if c.id not in meld_ids]
        player.melds.append(chosen_meld)
        player.sort_hand()

        val_chosen = validate_meld(chosen_meld, wildcard_rank=self.wildcard_rank)
        self.must_close_this_turn = (val_chosen.wildcards_as_substitute > 0)
        self.forbidden_discard_card_id = forbidden_id
        self.turn_taken_discard_card = target_card
        self.turn_taken_discarder_seat = self.card_discarder.get(target_card.id)
        self.phase = "TURN_MELD_DISCARD"
        self.turn_remaining_sec = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        meld_str = "-".join(c.id for c in chosen_meld)
        close_note = " (Wajib langsung Tutup Biasa giliran ini)" if self.must_close_this_turn else ""
        self.status_message = (
            f"{player.name} mengambil {len(taken_cards)} kartu buangan ({target_card.id}) "
            f"& langsung menurunkan [{meld_str}]{close_note}!"
        )
        return True, self.status_message

    # ------------------------------------------------------------------
    # Tahap 2: Menurunkan Kombinasi (Meld) dari Tangan & Auto-Turun
    # ------------------------------------------------------------------
    def meld_from_hand(self, seat: int, card_ids: List[str]) -> Tuple[bool, str]:
        if self.phase != "TURN_MELD_DISCARD" or seat != self.current_turn_seat:
            return False, "Anda harus mengambil kartu terlebih dahulu sebelum menurunkan kombinasi!"

        player = self.players[seat]
        id_set = set(card_ids)
        selected = [c for c in player.hand if c.id in id_set]
        if len(selected) != len(card_ids):
            return False, "Kartu yang dipilih tidak ditemukan di tangan."

        if len(player.hand) - len(selected) < 1:
            return False, "Wajib menyisakan minimal 1 kartu di tangan untuk dibuang di akhir giliran!"

        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)

        # 1. Coba sebagai kombinasi baru berdiri sendiri (>= 3 kartu)
        val = validate_meld(selected, wildcard_rank=self.wildcard_rank)
        if val.valid:
            # Syarat buka meja / turun kartu:
            # Jika belum punya Seri atau Tris As di meja, kombinasi yang diturunkan haruslah Seri atau Tris As!
            if not already_safe:
                is_seri = val.is_seri
                is_tris_ace = val.meld_type in ("TRIS_ACE", "KUARTET_ACE")
                if not is_seri and not is_tris_ace:
                    return (
                        False,
                        f"Belum bisa menurunkan {val.meld_type}! Untuk membuka meja, Anda harus memiliki/menurunkan Kartu Urut (Seri min 3) "
                        f"atau Tris As (A-A-A) terlebih dahulu sebelum bisa menurunkan Tris lainnya.",
                    )

            player.hand = [c for c in player.hand if c.id not in id_set]
            player.melds.append(val.ordered_cards)
            meld_str = "-".join(c.id for c in val.ordered_cards)
            self.status_message = f"{player.name} menurunkan [{meld_str}] ({val.reason})."
            return True, self.status_message

        # 2. Jika bukan kombinasi berdiri sendiri (misal 1 atau 2 kartu), cek apakah bisa menyambung (extend) ke meja
        if player.melds:
            for m_idx, existing_meld in enumerate(player.melds):
                test_meld = existing_meld + selected
                val_ext = validate_meld(test_meld, wildcard_rank=self.wildcard_rank)
                if val_ext.valid:
                    player.hand = [c for c in player.hand if c.id not in id_set]
                    player.melds[m_idx] = val_ext.ordered_cards
                    meld_str = "-".join(c.id for c in val_ext.ordered_cards)
                    added_str = "-".join(c.id for c in selected)
                    self.status_message = f"{player.name} menyambung kartu [{added_str}] ke kombinasi meja menjadi [{meld_str}]!"
                    return True, self.status_message

        return False, val.reason

    def auto_meld_all_valid(self, seat: int) -> Tuple[bool, str]:
        """Menurunkan seluruh kombinasi sah dari tangan secara otomatis & menyambung ke meja (menyisakan >= 1 kartu buang)."""
        if self.phase != "TURN_MELD_DISCARD" or seat != self.current_turn_seat:
            return False, "Bukan tahap susun kartu pada giliran Anda."

        player = self.players[seat]
        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)
        melds, rem = find_best_melds_in_hand(
            player.hand,
            wildcard_rank=self.wildcard_rank,
            already_has_seri=already_safe,
        )

        if not already_safe and melds:
            has_opener = any(
                validate_meld(m, wildcard_rank=self.wildcard_rank).is_seri
                or validate_meld(m, wildcard_rank=self.wildcard_rank).meld_type in ("TRIS_ACE", "KUARTET_ACE")
                for m in melds
            )
            if not has_opener:
                melds = []

        if len(rem) == 0 and melds:
            adjusted = False
            for i, m in enumerate(melds):
                if len(m) >= 4:
                    sub_val = validate_meld(m[:-1], wildcard_rank=self.wildcard_rank)
                    if sub_val.valid:
                        rem = [m[-1]]
                        melds[i] = sub_val.ordered_cards
                        adjusted = True
                        break
                    sub_val2 = validate_meld(m[1:], wildcard_rank=self.wildcard_rank)
                    if sub_val2.valid:
                        rem = [m[0]]
                        melds[i] = sub_val2.ordered_cards
                        adjusted = True
                        break
            if not adjusted:
                rem = melds.pop()

        # Terapkan melds baru ke meja jika ada
        if melds:
            for m in melds:
                player.melds.append(m)
            player.hand = rem

        # Coba sambung sisa kartu di tangan ke kombinasi di meja (harus menyisakan >= 1 kartu untuk dibuang)
        extended_count = 0
        if player.melds and len(player.hand) >= 2:
            changed = True
            while changed and len(player.hand) >= 2:
                changed = False
                for c in list(player.hand):
                    if len(player.hand) < 2:
                        break
                    for m_idx in range(len(player.melds)):
                        test_m = player.melds[m_idx] + [c]
                        val_m = validate_meld(test_m, wildcard_rank=self.wildcard_rank)
                        if val_m.valid:
                            player.melds[m_idx] = val_m.ordered_cards
                            player.hand.remove(c)
                            extended_count += 1
                            changed = True
                            break

        player.sort_hand()

        if melds and extended_count > 0:
            self.status_message = f"Berhasil menurunkan {len(melds)} kombinasi & menyambung {extended_count} kartu ke meja! Sisa {len(player.hand)} kartu di tangan."
            return True, self.status_message
        elif melds:
            self.status_message = f"Berhasil menurunkan {len(melds)} kombinasi! Sisa {len(player.hand)} kartu di tangan."
            return True, self.status_message
        elif extended_count > 0:
            self.status_message = f"Berhasil menyambung {extended_count} kartu ke kombinasi meja! Sisa {len(player.hand)} kartu di tangan."
            return True, self.status_message

        if not already_safe:
            return (
                False,
                "Untuk membuka meja, Anda harus memiliki/menurunkan Kartu Urut (Seri min 3) "
                "atau Tris As (A-A-A) terlebih dahulu sebelum bisa menurunkan Tris lainnya.",
            )
        return False, "Belum ada kombinasi sah atau kartu sambungan di tangan Anda."

    def reorder_player_hand(self, seat: int, source_cid: str, target_cid: str) -> Tuple[bool, str]:
        """Menata ulang posisi kartu di tangan pemain berdasarkan drag and drop."""
        if seat < 0 or seat >= len(self.players):
            return False, "Kursi pemain tidak valid."
        ok = self.players[seat].reorder_hand(source_cid, target_cid)
        if ok:
            return True, f"Posisi kartu {source_cid} berhasil dipindahkan."
        return False, "Gagal mengubah urutan kartu."

    def check_can_close_round(self, seat: int, preferred_discard_id: Optional[str] = None) -> Tuple[bool, bool, Optional[str]]:
        """
        Mengecek apakah pemain saat ini dapat menutup ronde (Tutup Tangan Murni atau Tutup Biasa).
        Returns: (can_close, is_tutup_tangan_murni, closing_discard_id)
        """
        if self.phase != "TURN_MELD_DISCARD" or seat != self.current_turn_seat:
            return False, False, None

        player = self.players[seat]
        if not player.hand:
            return False, False, None

        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)
        valid_closing_discards: List[Tuple[bool, int, str]] = []

        for cand in player.hand:
            if self.forbidden_discard_card_id and cand.id == self.forbidden_discard_card_id:
                continue
            others = [c for c in player.hand if c.id != cand.id]
            if not others:
                if len(player.melds) > 0 and already_safe:
                    is_wild = cand.is_wildcard(self.wildcard_rank)
                    valid_closing_discards.append((is_wild, cand.base_points, cand.id))
                continue

            melds, rem = find_best_melds_in_hand(
                others,
                wildcard_rank=self.wildcard_rank,
                already_has_seri=already_safe,
            )
            combined_melds = [list(m) for m in player.melds] + [list(m) for m in melds]
            if combined_melds and rem:
                changed = True
                while changed and rem:
                    changed = False
                    for c in list(rem):
                        for m_idx in range(len(combined_melds)):
                            test_m = combined_melds[m_idx] + [c]
                            val_m = validate_meld(test_m, wildcard_rank=self.wildcard_rank)
                            if val_m.valid:
                                combined_melds[m_idx] = val_m.ordered_cards
                                rem.remove(c)
                                changed = True
                                break

            if (
                len(rem) == 0
                and len(combined_melds) > 0
                and (already_safe or has_valid_seri_or_ace_meld(combined_melds, self.wildcard_rank))
            ):
                is_wild = cand.is_wildcard(self.wildcard_rank)
                valid_closing_discards.append((is_wild, cand.base_points, cand.id))

        if not valid_closing_discards:
            return False, False, None

        total_melded_cards = sum(len(m) for m in player.melds) + (len(player.hand) - 1)
        is_tutup_tangan_murni = (
            self.melds_count_at_turn_start == 0
            and self.turn_taken_discard_card is None
            and total_melded_cards >= INITIAL_HAND_SIZE
        )
        if preferred_discard_id and any(x[2] == preferred_discard_id for x in valid_closing_discards):
            return True, is_tutup_tangan_murni, preferred_discard_id

        if is_tutup_tangan_murni:
            # Untuk Tutup Tangan Murni (+250), pilih kartu buangan terkecil (jangan buang Wild Card)
            valid_closing_discards.sort(key=lambda x: (x[0], x[1]))
        else:
            # Untuk Tutup Biasa, pilih kartu buangan dengan nilai tertinggi (agar bonus x Wild Card maksimal), tapi hindari buang Wild jika tidak perlu
            valid_closing_discards.sort(key=lambda x: (not x[0], x[1]), reverse=True)

        return True, is_tutup_tangan_murni, valid_closing_discards[0][2]

    def check_can_declare_tutup_tangan(self, seat: int) -> Tuple[bool, Optional[str]]:
        """Mengecek apakah pemain saat ini dapat langsung melakukan Tutup Tangan (+250 Poin) dan kartu apa yang dibuang."""
        can_close, is_tt_murni, discard_id = self.check_can_close_round(seat)
        if can_close and is_tt_murni:
            return True, discard_id
        return False, None

    def declare_tutup_tangan(self, seat: int, discard_card_id: Optional[str] = None) -> Tuple[bool, str]:
        """Menutup langsung dari tangan tanpa Kartu Jadi sebelumnya (+250 Poin, wajib ada >=1 Seri min 3 atau Tris As) atau Tutup Biasa jika ambil buangan."""
        if self.phase != "TURN_MELD_DISCARD" or seat != self.current_turn_seat:
            return False, "Bukan tahap susun/buang pada giliran Anda."

        can_close, is_tt_murni, best_discard_id = self.check_can_close_round(seat, preferred_discard_id=discard_card_id)
        if not can_close:
            if self.turn_taken_discard_card is not None:
                return False, "Tutup Tangan Murni (+250 Poin) tidak berlaku jika Anda mengambil kartu dari tempat pembuangan! Selesaikan semua kombinasi hingga sisa 1 kartu buang untuk Tutup Biasa."
            if self.melds_count_at_turn_start > 0:
                return False, "Tutup Tangan (+250 Poin) hanya berlaku jika Anda belum pernah menurunkan Kartu Jadi di ronde/giliran sebelumnya!"
            return False, "Belum memenuhi syarat Tutup Tangan Murni (wajib minimal 1 Seri Urut atau Tris As min 3 kartu & sisa 1 kartu buang)."

        if best_discard_id:
            return self.discard_card(seat, best_discard_id)

        return False, "Belum memenuhi syarat Tutup Tangan Murni (wajib minimal 1 Seri Urut atau Tris As min 3 kartu & sisa 1 kartu buang)."

    # ------------------------------------------------------------------
    # Tahap 3: Membuang 1 Kartu & Evaluasi Tutup Tangan (+250) vs Tutup Biasa
    # ------------------------------------------------------------------
    def discard_card(self, seat: int, card_id: Optional[str] = None) -> Tuple[bool, str]:
        if self.phase != "TURN_MELD_DISCARD" or seat != self.current_turn_seat:
            return False, "Anda harus mengambil kartu terlebih dahulu sebelum membuang kartu!"

        player = self.players[seat]
        if not player.hand:
            return False, "Tidak ada kartu di tangan untuk dibuang."

        already_safe = has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank)
        can_close_round, _, closing_cid = self.check_can_close_round(seat)

        # 1. Tentukan kartu buangan (target)
        if not card_id:
            if can_close_round and closing_cid:
                target = next((c for c in player.hand if c.id == closing_cid), None)
            else:
                target = None

            if target is None:
                # Otomatis pilih kartu buangan terbaik dari sisa kartu mati di tangan
                _, deadwood = find_best_melds_in_hand(
                    player.hand,
                    wildcard_rank=self.wildcard_rank,
                    already_has_seri=already_safe,
                )
                candidates = deadwood if deadwood else list(player.hand)
                if self.forbidden_discard_card_id and len(candidates) > 1:
                    candidates = [c for c in candidates if c.id != self.forbidden_discard_card_id] or candidates

                def discard_priority(c: Card):
                    is_wild = c.is_wildcard(self.wildcard_rank)
                    return (not is_wild, c.base_points)

                candidates.sort(key=discard_priority, reverse=True)
                target = candidates[0]
        else:
            target = next((c for c in player.hand if c.id == card_id), None)
            if target is None:
                return False, "Kartu tidak ditemukan di tangan Anda."

        if self.forbidden_discard_card_id and target.id == self.forbidden_discard_card_id:
            return False, "Tidak boleh membuang kembali kartu yang baru saja diambil dari tumpukan buangan teratas."

        # 2. Evaluasi sisa kartu di tangan:
        # PENTING: Kartu di tangan TIDAK BOLEH otomatis turun ke meja saat buang kartu biasa!
        # Pemain bebas menyimpan kartu di tangan (misal untuk strategi Tutup Tangan +250).
        # Kartu hanya turun jika pemain sengaja klik 'AUTO TURUN (A)' / 'TURUNKAN PILIHAN (M)',
        # KECUALI jika seluruh sisa kartu jadi (len(rem) == 0) yang langsung menutup ronde (Tutup)!
        other_cards = [c for c in player.hand if c.id != target.id]
        can_close = False
        combined_melds = [list(m) for m in player.melds]
        if other_cards:
            melds, rem = find_best_melds_in_hand(
                other_cards,
                wildcard_rank=self.wildcard_rank,
                already_has_seri=already_safe,
            )
            combined_melds = [list(m) for m in player.melds] + melds
            # Coba sambung sisa kartu rem ke combined_melds di meja
            if combined_melds and rem:
                changed = True
                while changed and rem:
                    changed = False
                    for c in list(rem):
                        for m_idx in range(len(combined_melds)):
                            test_m = combined_melds[m_idx] + [c]
                            val_m = validate_meld(test_m, wildcard_rank=self.wildcard_rank)
                            if val_m.valid:
                                combined_melds[m_idx] = val_m.ordered_cards
                                rem.remove(c)
                                changed = True
                                break

            # HANYA otomatis menutup/menurunkan jika seluruh sisa kartu jadi (len(rem) == 0) untuk TUTUP!
            can_close = (
                len(rem) == 0
                and len(combined_melds) > 0
                and (already_safe or has_valid_seri_or_ace_meld(combined_melds, self.wildcard_rank))
            )
        else:
            can_close = len(player.melds) > 0 and already_safe

        # Jika pemain mengambil buangan menggunakan Wild Card pengganti pada giliran ini,
        # pemain WAJIB menutup kartu pada giliran ini!
        if getattr(self, "must_close_this_turn", False) and not can_close:
            if can_close_round and closing_cid:
                return (
                    False,
                    f"Karena Anda mengambil buangan dengan Wild Card pengganti, Anda WAJIB menutup kartu pada giliran ini! Buang kartu {closing_cid} untuk menutup kartu.",
                )

        if can_close and other_cards:
            player.melds = combined_melds
            other_cards = []

        player.hand = other_cards
        self.discard_pile.append(target)
        self.card_discarder[target.id] = seat
        self.must_close_this_turn = False

        # Cek kondisi Tutup (0 kartu tersisa di tangan, punya minimal 1 meld, dan punya minimal 1 Seri min 3 atau Tris As)
        if len(player.hand) == 0 and len(player.melds) > 0:
            if has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank):
                # Tutup Tangan Murni (+250) HANYA jika:
                # 1. Di awal giliran ini belum ada Kartu Jadi di meja (melds_count_at_turn_start == 0)
                # 2. Pemain TIDAK mengambil kartu dari tempat pembuangan pada giliran ini (turn_taken_discard_card is None)!
                # 3. Total kartu di melds minimal INITIAL_HAND_SIZE (7 kartu)
                # Catatan: Pemain tetap berhak Tutup Tangan Murni meskipun menekan 'Auto Turun' terlebih dahulu di giliran yang sama.
                took_discard_this_turn = (self.turn_taken_discard_card is not None)
                total_melded_cards = sum(len(m) for m in player.melds)
                is_tutup_tangan = (
                    self.melds_count_at_turn_start == 0
                    and not took_discard_this_turn
                    and total_melded_cards >= INITIAL_HAND_SIZE
                )
                if is_tutup_tangan:
                    reason = f"TUTUP TANGAN MURNI oleh {player.name} (+{TUTUP_TANGAN_BONUS} Poin)! Nilai pemain lain tidak dihitung (0 Poin)."
                else:
                    bonus = self.compute_tutup_biasa_bonus(target)
                    meld_sum = sum(validate_meld(m, wildcard_rank=self.wildcard_rank).points for m in player.melds)
                    close_source = "ambil buangan" if took_discard_this_turn else "tutup biasa"
                    reason = (
                        f"Tutup Kartu ({close_source}) oleh {player.name}: Poin Kartu Jadi ({meld_sum}) + "
                        f"Bonus Buang {target.id} ({self._closing_card_value(target)}) x Wild '{self.wildcard_rank}' "
                        f"({self._wildcard_value()}) = +{bonus} Poin (Total: +{meld_sum + bonus})!"
                    )

                # PENALTI UMPAN TUTUP x10:
                # Jika pemain yang tutup mengambil kartu buangan pada giliran ini,
                # pemain yang membuang kartu tersebut mendapat penalti nilai kartu x 10!
                feeder_seat: Optional[int] = None
                feeder_card: Optional[Card] = None
                feed_penalty: int = 0
                if self.turn_taken_discard_card is not None and self.turn_taken_discarder_seat is not None:
                    if self.turn_taken_discarder_seat != seat:
                        feeder_seat = self.turn_taken_discarder_seat
                        feeder_card = self.turn_taken_discard_card
                        feed_card_val = self._closing_card_value(feeder_card)
                        feed_penalty = feed_card_val * 10
                        feeder_name = self.players[feeder_seat].name
                        reason += (
                            f" | PENALTI UMPAN TUTUP x10: {feeder_name} terkena -{feed_penalty} Poin "
                            f"karena membuang {feeder_card.id} yang dimakan untuk tutup!"
                        )

                self._finish_round(
                    closer_seat=seat,
                    is_tutup_tangan=is_tutup_tangan,
                    reason=reason,
                    closing_discard=target,
                    feeder_seat=feeder_seat,
                    feeder_card=feeder_card,
                    feed_penalty=feed_penalty,
                )
                return True, self.status_message

        # Cek apakah Pak (Draw Pile) sudah habis
        if len(self.draw_pile) == 0:
            self._finish_round(
                closer_seat=None,
                is_tutup_tangan=False,
                reason="Pak Kartu Habis (Pemain tanpa Kartu Urut / Tris As min 3 otomatis TERBAKAR SEMUA)!",
            )
            return True, self.status_message

        # Lanjut ke pemain berikutnya searah jarum jam
        self.current_turn_seat = (self.current_turn_seat + 1) % len(self.players)
        self.melds_count_at_turn_start = len(self.players[self.current_turn_seat].melds)
        self.phase = "TURN_DRAW"
        self.turn_remaining_sec = float(self.turn_timer_sec) if self.turn_timer_sec > 0 else 999.0
        self.turn_taken_discard_card = None
        self.turn_taken_discarder_seat = None
        self.must_close_this_turn = False
        next_p = self.players[self.current_turn_seat]
        self.status_message = (
            f"{player.name} membuang {target.id}. Sekarang GILIRAN {next_p.name.upper()}!"
        )
        return True, self.status_message

    # ------------------------------------------------------------------
    # Perhitungan Skor Akhir Ronde & Aturan WAJIB KARTU URUT (SERI MIN 3)
    # ------------------------------------------------------------------
    def _closing_card_value(self, card: Card) -> int:
        """Nilai kartu buangan penutup (Angka=5, Face=10, As=15, Wild Card=25)."""
        return card.get_deadwood_penalty(self.wildcard_rank)

    def _wildcard_value(self) -> int:
        """Nilai kelompok Wild Card ronde ini (dari kartu bukaan: Angka=5, Face=10, As=15)."""
        if self.wildcard_rank and self.wildcard_rank != "JOKER":
            return Card(id="X", rank=self.wildcard_rank, suit="S").base_points
        return 0

    def compute_tutup_biasa_bonus(self, closing_discard: Optional[Card]) -> int:
        """Bonus Tutup Biasa = nilai kartu buangan penutup x nilai Wild Card (contoh: K=10 x Wild angka=5 -> +50)."""
        if closing_discard is None:
            return 0
        return self._closing_card_value(closing_discard) * self._wildcard_value()

    def _finish_round(
        self,
        closer_seat: Optional[int],
        is_tutup_tangan: bool,
        reason: str,
        closing_discard: Optional[Card] = None,
        feeder_seat: Optional[int] = None,
        feeder_card: Optional[Card] = None,
        feed_penalty: int = 0,
    ):
        self.round_closer_seat = closer_seat
        self.round_closed_by_tutup_tangan = is_tutup_tangan

        for p in self.players:
            already_safe = has_valid_seri_or_ace_meld(p.melds, self.wildcard_rank)
            if p.hand:
                hand_melds, hand_dead = find_best_melds_in_hand(
                    p.hand,
                    wildcard_rank=self.wildcard_rank,
                    already_has_seri=already_safe,
                )
                candidate_all_melds = p.melds + hand_melds
            else:
                hand_melds = []
                hand_dead = []
                candidate_all_melds = list(p.melds)

            # ATURAN KHUSUS TUTUP TANGAN MURNI:
            # Jika seorang pemain berhasil Tutup Tangan Murni (+250):
            # 1. Pemain yang menutup mendapat skor murni +250 Poin.
            # 2. Nilai pemain lain TIDAK DIHITUNG baik minus atau plus (skor ronde = 0 Poin),
            #    karena ronde selesai seketika dan pemain lain tidak sempat menyelesaikan permainan.
            is_closer_tt = closer_seat is not None and p.seat == closer_seat and is_tutup_tangan
            is_other_in_tt = is_tutup_tangan and (closer_seat is not None and p.seat != closer_seat)

            if is_closer_tt:
                # TUTUP TANGAN MURNI: closer HANYA mendapat +250 Poin (poin kartu tidak dihitung)
                p.burned_last_round = False
                meld_points = 0
                dead_penalty = 0
                tutup_bonus = TUTUP_TANGAN_BONUS
                p_feed_pen = 0
                round_net = TUTUP_TANGAN_BONUS
            elif is_other_in_tt:
                # TUTUP TANGAN MURNI (Pemain Lain): skor TIDAK DIHITUNG baik minus atau plus (0 Poin)
                p.burned_last_round = False
                for m in hand_melds:
                    p.melds.append(m)
                p.hand = hand_dead
                meld_points = 0
                dead_penalty = 0
                tutup_bonus = 0
                p_feed_pen = 0
                round_net = 0
            else:
                # KONDISI TUTUP BIASA ATAU PAK HABIS:
                # ATURAN: Pemain yang memiliki Kartu Urut (Seri min 3) ATAU Tris As (A-A-A)
                # berstatus AMAN dari penalti terbakar!
                if has_valid_seri_or_ace_meld(candidate_all_melds, self.wildcard_rank):
                    p.burned_last_round = False
                    for m in hand_melds:
                        p.melds.append(m)
                    p.hand = hand_dead

                    meld_points = sum(validate_meld(m, wildcard_rank=self.wildcard_rank).points for m in p.melds)
                    dead_penalty = sum(c.get_deadwood_penalty(self.wildcard_rank) for c in p.hand)
                    if closer_seat is not None and p.seat == closer_seat:
                        # TUTUP BIASA: nilai kartu buangan penutup x nilai Wild Card
                        tutup_bonus = self.compute_tutup_biasa_bonus(closing_discard)
                    else:
                        tutup_bonus = 0
                    round_net = meld_points - dead_penalty + tutup_bonus
                else:
                    # TERBAKAR SEMUA! Semua kartu (baik di melds maupun di hand) dihitung minus!
                    p.burned_last_round = True
                    all_burned_cards = [c for m in p.melds for c in m] + list(p.hand)
                    p.melds = []
                    p.hand = all_burned_cards
                    meld_points = 0
                    dead_penalty = sum(c.get_deadwood_penalty(self.wildcard_rank) for c in all_burned_cards)
                    tutup_bonus = 0
                    round_net = -dead_penalty

                # Potong penalti umpan tutup jika pemain ini adalah pembuang kartu yang dimakan untuk tutup
                p_feed_pen = feed_penalty if (feeder_seat is not None and p.seat == feeder_seat) else 0
                round_net -= p_feed_pen

            p.last_round_score = round_net
            p.total_score += round_net
            p.last_round_breakdown = {
                "meld_points": meld_points,
                "dead_penalty": dead_penalty,
                "tutup_bonus": tutup_bonus,
                "feed_penalty": p_feed_pen,
                "burned": p.burned_last_round,
                "round_net": round_net,
                "total_score": p.total_score,
            }

        # Aturan Baru: Pemain yang memiliki total skor tertinggi yang akan main terus menerus (mulai pertama di setiap ronde)!
        # Jika skor seri / sama, starter yang sedang memegang giliran tetap dipertahankan.
        if closer_seat is not None:
            self.last_round_closer_seat = closer_seat

        highest_score = max(p.total_score for p in self.players)
        leaders = [p for p in self.players if p.total_score == highest_score]
        if any(p.seat == self.starter_seat for p in leaders):
            next_starter_seat = self.starter_seat
        else:
            next_starter_seat = leaders[0].seat

        self.starter_seat = next_starter_seat
        self.highest_score_seat = next_starter_seat
        leader_p = self.players[next_starter_seat]
        next_starter_msg = f" | {leader_p.name} SKOR TERTINGGI ({leader_p.total_score} Poin) & akan MAIN TERUS (pembuka ronde berikutnya)!"

        eligible_winners = [p for p in self.players if p.total_score >= self.target_score]
        if eligible_winners:
            winner = max(eligible_winners, key=lambda p: p.total_score)
            self.match_winner_seat = winner.seat
            self.phase = "MATCH_OVER"
            self.status_message = (
                f"[JUARA] PERTANDINGAN SELESAI! {winner.name} menang dengan skor {winner.total_score} / {self.target_score} Poin! ({reason})"
            )
        else:
            self.phase = "ROUND_OVER"
            self.round_over_timer = 5.0
            self.status_message = f"Akhir Ronde {self.round_number}: {reason}{next_starter_msg} (Ronde berikutnya dimulai otomatis dalam 5 detik...)"

    # ------------------------------------------------------------------
    # AI Bot Pintar & Auto-Action saat Turn Timeout
    # ------------------------------------------------------------------
    def execute_bot_or_timeout_step(self, seat: Optional[int] = None) -> str:
        if self.phase not in ("TURN_DRAW", "TURN_MELD_DISCARD"):
            return "Tidak dalam giliran aktif."

        active_seat = self.current_turn_seat if seat is None else seat
        player = self.players[active_seat]

        if self.phase == "TURN_DRAW":
            best_discard_idx = None
            best_gain = 10

            total_disc = len(self.discard_pile)
            min_idx = max(0, total_disc - MAX_DISCARD_TAKE_DEPTH)
            already_seri = has_valid_seri_meld(player.melds, self.wildcard_rank)

            for idx in range(total_disc - 1, min_idx - 1, -1):
                ok, _, req_meld = self.can_take_discard(active_seat, idx)
                if ok and req_meld:
                    taken = self.discard_pile[idx:]
                    pool = player.hand + taken
                    melds, rem = find_best_melds_in_hand(
                        pool,
                        must_include=self.discard_pile[idx],
                        wildcard_rank=self.wildcard_rank,
                        already_has_seri=already_seri,
                    )
                    extra_dead_cost = sum(c.get_deadwood_penalty(self.wildcard_rank) for c in rem) - sum(
                        c.get_deadwood_penalty(self.wildcard_rank) for c in player.hand
                    )
                    meld_pts = sum(validate_meld(m, wildcard_rank=self.wildcard_rank).points for m in melds)
                    net_eval = meld_pts - max(0, extra_dead_cost)
                    if has_valid_seri_meld(melds, self.wildcard_rank) and not already_seri:
                        net_eval += 30  # Prioritaskan dapat Seri wajib agar tidak terbakar!
                    if net_eval > best_gain and len(rem) <= 5:
                        best_gain = net_eval
                        best_discard_idx = idx

            if best_discard_idx is not None:
                _, msg = self.take_from_discard(active_seat, best_discard_idx)
                return msg
            else:
                _, msg = self.draw_from_deck(active_seat)
                return msg

        elif self.phase == "TURN_MELD_DISCARD":
            can_close_round, _, closing_cid = self.check_can_close_round(active_seat)
            if can_close_round and closing_cid:
                _, msg = self.discard_card(active_seat, closing_cid)
                return msg

            already_seri = has_valid_seri_meld(player.melds, self.wildcard_rank)
            melds, rem = find_best_melds_in_hand(
                player.hand,
                wildcard_rank=self.wildcard_rank,
                already_has_seri=already_seri,
            )
            # Bot menyimpan kartu di tangan jika belum pernah turun & berpeluang Tutup Tangan (+250),
            # atau langsung turun jika sudah pernah ambil buangan
            if melds and (len(rem) <= 1 or len(player.melds) > 0):
                self.auto_meld_all_valid(active_seat)
                _, rem = find_best_melds_in_hand(
                    player.hand,
                    wildcard_rank=self.wildcard_rank,
                    already_has_seri=has_valid_seri_meld(player.melds, self.wildcard_rank),
                )

            can_close_round, _, closing_cid = self.check_can_close_round(active_seat)
            if can_close_round and closing_cid:
                _, msg = self.discard_card(active_seat, closing_cid)
                return msg

            _, deadwood = find_best_melds_in_hand(
                player.hand,
                wildcard_rank=self.wildcard_rank,
                already_has_seri=has_valid_seri_or_ace_meld(player.melds, self.wildcard_rank),
            )
            candidates = deadwood if deadwood else list(player.hand)
            if self.forbidden_discard_card_id and len(candidates) > 1:
                candidates = [c for c in candidates if c.id != self.forbidden_discard_card_id] or candidates
            if not candidates:
                return "Tidak ada kartu untuk dibuang."

            def discard_priority(c: Card) -> Tuple[int, int]:
                if c.is_wildcard(self.wildcard_rank):
                    return (-100, -100)
                same_rank = sum(1 for x in player.hand if x.id != c.id and x.rank == c.rank)
                near_suit = sum(
                    1
                    for x in player.hand
                    if x.id != c.id
                    and x.suit == c.suit
                    and x.group == c.group
                    and c.group != "ACE"
                    and abs(RANK_ORDER[x.rank] - RANK_ORDER[c.rank]) <= 2
                )
                usefulness = same_rank * 3 + near_suit * 2
                return (-usefulness, c.get_deadwood_penalty(self.wildcard_rank))

            chosen_discard = max(candidates, key=discard_priority)
            _, msg = self.discard_card(active_seat, chosen_discard.id)
            return msg

        return ""

    # ------------------------------------------------------------------
    # Serialisasi State
    # ------------------------------------------------------------------
    def to_state_dict(self, viewer_seat: Optional[int] = None) -> dict:
        w_rank = self.wildcard_rank
        return {
            "room_code": self.room_code,
            "round_number": self.round_number,
            "target_score": self.target_score,
            "turn_timer_sec": self.turn_timer_sec,
            "max_players": self.max_players,
            "bot_delay_sec": getattr(self, "bot_delay_sec", 0.85),
            "phase": self.phase,
            "current_turn_seat": self.current_turn_seat,
            "starter_seat": self.starter_seat,
            "highest_score_seat": getattr(self, "highest_score_seat", self.starter_seat),
            "last_round_closer_seat": self.last_round_closer_seat,
            "wildcard_indicator": self.wildcard_indicator_card.to_dict(w_rank) if self.wildcard_indicator_card else None,
            "wildcard_rank": w_rank,
            "melds_count_at_turn_start": self.melds_count_at_turn_start,
            "must_close_this_turn": getattr(self, "must_close_this_turn", False),
            "forbidden_discard_card_id": self.forbidden_discard_card_id,
            "round_closer_seat": self.round_closer_seat,
            "round_closed_by_tutup_tangan": self.round_closed_by_tutup_tangan,
            "match_winner_seat": self.match_winner_seat,
            "draw_pile_count": len(self.draw_pile),
            "discard_pile": [c.to_dict(w_rank) for c in self.discard_pile],
            "status_message": self.status_message,
            "turn_remaining_sec": round(self.turn_remaining_sec, 1),
            "is_paused": getattr(self, "is_paused", False),
            "round_over_timer": round(self.round_over_timer, 1) if getattr(self, "round_over_timer", None) is not None else None,
            "players": [
                {
                    "seat": p.seat,
                    "name": p.name,
                    "is_bot": p.is_bot,
                    "player_id": getattr(p, "player_id", ""),
                    "is_ready": p.is_ready,
                    "connected": p.connected,
                    "auto_pilot": p.auto_pilot,
                    "burned_last_round": p.burned_last_round,
                    "has_seri": has_valid_seri_or_ace_meld(p.melds, w_rank),
                    "can_tutup_tangan": (
                        self.check_can_declare_tutup_tangan(p.seat)[0]
                        if (viewer_seat is None or viewer_seat == p.seat)
                        else False
                    ),
                    "tutup_discard_id": (
                        self.check_can_declare_tutup_tangan(p.seat)[1]
                        if (viewer_seat is None or viewer_seat == p.seat)
                        else None
                    ),
                    "can_close_round": (
                        self.check_can_close_round(p.seat)[0]
                        if (viewer_seat is None or viewer_seat == p.seat)
                        else False
                    ),
                    "close_discard_id": (
                        self.check_can_close_round(p.seat)[2]
                        if (viewer_seat is None or viewer_seat == p.seat)
                        else None
                    ),
                    "hand_count": len(p.hand),
                    "hand": [
                        c.to_dict(w_rank)
                        for c in p.hand
                        if (viewer_seat is None or viewer_seat == p.seat or self.phase in ("ROUND_OVER", "MATCH_OVER"))
                    ],
                    "melds": [[c.to_dict(w_rank) for c in m] for m in p.melds],
                    "total_score": p.total_score,
                    "last_round_score": p.last_round_score,
                    "last_round_breakdown": p.last_round_breakdown,
                }
                for p in self.players
            ],
        }
