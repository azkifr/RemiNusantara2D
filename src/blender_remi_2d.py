"""
Remi Nusantara 2D - Blender 3.6 Interactive 2D Card Game (v2.5)
===============================================================
Pembaruan v2.5:
1. Dukungan Penuh Fitur Drag & Drop Interaktif di Meja Blender 2D:
   - Drag kartu tangan ke Area Buangan (y > -0.7): membuang kartu / menutup ronde (+250 / biasa).
   - Drag kartu tangan ke Area Kartu Jadi (-2.5 < y <= -0.7): menurunkan kombinasi (meld).
   - Drag kartu tangan ke atas kartu tangan lain: menata ulang urutan kartu di tangan secara bebas.
   - Drag dari Pak / Tumpukan Buangan ke arah tangan: mengambil kartu.
   - Kartu mengambang (Z +0.35) dan berpindah halus mengikuti kursor saat di-drag.
   - Klik singkat tanpa geser tetap berfungsi normal untuk memilih/toggle kartu.
2. 4 Wild Card (1 Joker + 3 Kartu Bukaan Pertama saat ronde dimulai).
3. Aturan Wajib Kartu Urut (Seri Min 3 Kartu) / Tris As Min 3 — Terhindar dari Terbakar.
4. Penalti Umpan Tutup x10 bagi pemain yang membuang kartu penutup lawan.
"""

from __future__ import annotations
import math
import os
import sys
import time
import bpy
import blf
from bpy_extras import view3d_utils

for candidate_dir in [
    os.path.dirname(os.path.abspath(__file__)),
    os.path.join(os.path.dirname(os.path.abspath(bpy.data.filepath)), "src") if bpy.data.filepath else "",
    r"c:\Project Pribadi\Playing Card\src",
]:
    if candidate_dir and os.path.isdir(candidate_dir) and candidate_dir not in sys.path:
        sys.path.insert(0, candidate_dir)

from remi_engine import (
    Card,
    RemiGameMatch,
    validate_meld,
    MAX_DISCARD_TAKE_DEPTH,
)
from remi_network import RemiTCPServer, RemiTCPClient


# ==============================================================================
# STATE GLOBAL GAME DI BLENDER
# ==============================================================================
class BlenderRemi2DController:
    def __init__(self):
        self.game = RemiGameMatch(room_code="RM1500", num_players=4, turn_timer_sec=25)
        self.selected_card_ids: set[str] = set()
        self.mode: str = "OFFLINE"  # "OFFLINE", "HOST", "CLIENT"
        self.server: RemiTCPServer | None = None
        self.client: RemiTCPClient | None = None
        self.my_seat: int = 0
        self.modal_running: bool = False
        self.draw_handler = None
        self.last_bot_step_time: float = 0.0
        self.last_timer_tick: float = time.time()
        self.feedback_banner: str = "Klik 'PAK KARTU' (Biru) untuk ambil 1 kartu, atau klik kartu di Tumpukan Buangan!"
        self.hitboxes_2d: list[tuple[float, float, float, float, str, str]] = []
        self.drag_state: dict | None = None

    def get_active_state(self) -> dict:
        if self.mode == "CLIENT" and self.client and self.client.connected:
            st = self.client.poll()
            if st:
                self.my_seat = self.client.my_seat
                return st
        return self.game.to_state_dict(viewer_seat=self.my_seat)

    def get_turn_banner_info(self, st: dict) -> tuple[str, str]:
        phase = st["phase"]
        if phase == "ROUND_OVER":
            sec = int(st.get("round_over_timer") or 5)
            return (f"⏱ RONDE SELESAI! Ronde berikutnya dimulai otomatis dalam {sec}s...", "Mat_Btn_Blue")
        if phase == "MATCH_OVER":
            return ("🏆 PERTANDINGAN SELESAI (1500 POIN)!", "Mat_Btn_Purple")

        cur_seat = st["current_turn_seat"]
        cur_name = st["players"][cur_seat]["name"].upper()
        if cur_seat != self.my_seat:
            return (f">> GILIRAN LAWAN: {cur_name} SEDANG JALAN... (Harap Tunggu) <<", "Mat_Btn_Orange")

        if phase == "TURN_DRAW":
            return (
                ">> GILIRAN ANDA SEKARANG! [TAHAP 1: AMBIL KARTU] -> Klik PAK KARTU atau Buangan #1-#7 <<",
                "Mat_Btn_Green",
            )
        return (
            ">> GILIRAN ANDA SEKARANG! [TAHAP 2: SUSUN / BUANG] -> Klik 'TURUNKAN (M)' / 'AUTO TURUN (A)' / 'BUANG (B)' <<",
            "Mat_Btn_Green",
        )

    def start_round(self):
        self.selected_card_ids.clear()
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "START_ROUND"})
        else:
            self.game.start_new_round()
            self.feedback_banner = self.game.status_message
            if self.mode == "HOST" and self.server:
                self.server._broadcast_state()
        rebuild_2d_board_objects()

    def draw_from_deck(self):
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "DRAW_DECK"})
        else:
            ok, msg = self.game.draw_from_deck(self.my_seat)
            self.feedback_banner = msg
        rebuild_2d_board_objects()

    def take_discard(self, discard_idx: int):
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({
                "action": "TAKE_DISCARD",
                "discard_index": discard_idx,
                "meld_card_ids": list(self.selected_card_ids) if self.selected_card_ids else None,
            })
            self.selected_card_ids.clear()
        else:
            ok, msg = self.game.take_from_discard(
                self.my_seat,
                discard_idx,
                list(self.selected_card_ids) if self.selected_card_ids else None,
            )
            self.feedback_banner = msg
            if ok:
                self.selected_card_ids.clear()
        rebuild_2d_board_objects()

    def meld_selected(self):
        if len(self.selected_card_ids) < 3:
            self.feedback_banner = "Pilih minimal 3 kartu di tangan terlebih dahulu!"
            rebuild_2d_board_objects()
            return
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "MELD_HAND", "card_ids": list(self.selected_card_ids)})
            self.selected_card_ids.clear()
        else:
            ok, msg = self.game.meld_from_hand(self.my_seat, list(self.selected_card_ids))
            self.feedback_banner = msg
            if ok:
                self.selected_card_ids.clear()
        rebuild_2d_board_objects()

    def auto_meld(self):
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "AUTO_MELD"})
            self.selected_card_ids.clear()
        else:
            ok, msg = self.game.auto_meld_all_valid(self.my_seat)
            self.feedback_banner = msg
            if ok:
                self.selected_card_ids.clear()
        rebuild_2d_board_objects()

    def discard_selected_or_card(self, card_id: str | None = None):
        cid = card_id
        if cid is None:
            can_tutup, cand_cid = self.game.check_can_declare_tutup_tangan(self.my_seat)
            if can_tutup and cand_cid and len(self.selected_card_ids) == 0:
                cid = cand_cid
            elif len(self.selected_card_ids) == 1:
                cid = next(iter(self.selected_card_ids))
            elif can_tutup and cand_cid:
                cid = cand_cid
            else:
                self.feedback_banner = "Pilih tepat 1 kartu di tangan (atau Klik Kanan pada kartu) untuk membuang!"
                rebuild_2d_board_objects()
                return

        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "DISCARD", "card_id": cid})
            self.selected_card_ids.clear()
        else:
            ok, msg = self.game.discard_card(self.my_seat, cid)
            self.feedback_banner = msg
            if ok:
                self.selected_card_ids.clear()
        rebuild_2d_board_objects()

    def sort_hand(self, by_suit: bool = False):
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({"action": "SORT_HAND", "by_suit": by_suit})
        else:
            self.game.players[self.my_seat].sort_hand(by_suit=by_suit)
            self.feedback_banner = "Kartu diurutkan berdasarkan " + ("Kembang (Suit)." if by_suit else "Angka/Kelompok.")
        rebuild_2d_board_objects()

    def reorder_hand_card(self, source_cid: str, target_cid: str):
        """Menukar/memindahkan posisi kartu source_cid ke target_cid saat di-drag & drop di tangan."""
        if self.mode == "CLIENT" and self.client and self.client.connected:
            self.client.send({
                "action": "REORDER_HAND",
                "source_card_id": source_cid,
                "target_card_id": target_cid,
            })
        else:
            ok, msg = self.game.reorder_player_hand(self.my_seat, source_cid, target_cid)
            self.feedback_banner = msg
        rebuild_2d_board_objects()

    def update_status_banner_text(self, text: str):
        """Memperbarui teks Status_Banner secara realtime tanpa harus rebuild geometri penuh."""
        self.feedback_banner = text
        obj = bpy.data.objects.get("Status_Banner")
        if obj and obj.type == "FONT":
            obj.data.body = text

    def toggle_card_selection(self, card_id: str):
        if card_id in self.selected_card_ids:
            self.selected_card_ids.remove(card_id)
        else:
            self.selected_card_ids.add(card_id)

        st = self.get_active_state()
        w_rank = st.get("wildcard_rank")
        my_hand = [Card.from_id(c["id"]) for c in st["players"][self.my_seat]["hand"]]
        sel_cards = [c for c in my_hand if c.id in self.selected_card_ids]
        if len(sel_cards) >= 3:
            val = validate_meld(sel_cards, wildcard_rank=w_rank)
            if val.valid:
                self.feedback_banner = f"[KOMBINASI SAH] {val.reason} -> Klik 'TURUNKAN PILIHAN (M)' atau simpan di tangan untuk Tutup Tangan (+250)!"
            else:
                self.feedback_banner = f"[BELUM SAH] {val.reason}"
        elif len(sel_cards) == 1:
            self.feedback_banner = (
                f"Kartu dipilih: {sel_cards[0].id} -> Klik 'BUANG / TUTUP +250 (B)' untuk membuang."
            )
        else:
            self.feedback_banner = f"{len(sel_cards)} kartu dipilih."
        rebuild_2d_board_objects()

    def tick(self):
        now = time.time()
        dt = now - self.last_timer_tick
        self.last_timer_tick = now

        if self.mode == "CLIENT":
            prev_msg = self.feedback_banner
            st = self.get_active_state()
            if st and st.get("status_message") != prev_msg:
                self.feedback_banner = st.get("status_message", "")
                rebuild_2d_board_objects()
            return

        if self.game.phase in ("TURN_DRAW", "TURN_MELD_DISCARD"):
            cur_p = self.game.players[self.game.current_turn_seat]
            if cur_p.is_bot or cur_p.auto_pilot:
                if now - self.last_bot_step_time >= 0.80:
                    self.last_bot_step_time = now
                    msg = self.game.execute_bot_or_timeout_step()
                    self.feedback_banner = msg
                    rebuild_2d_board_objects()
            else:
                self.game.turn_remaining_sec = max(0.0, self.game.turn_remaining_sec - dt)
                if self.game.turn_remaining_sec <= 0.0:
                    cur_p.afk_strikes += 1
                    if cur_p.afk_strikes >= 2:
                        cur_p.auto_pilot = True
                    msg = self.game.execute_bot_or_timeout_step()
                    self.feedback_banner = f"[WAKTU HABIS] {msg}"
                    rebuild_2d_board_objects()
        elif self.game.phase == "ROUND_OVER":
            if not hasattr(self.game, "round_over_timer") or self.game.round_over_timer is None:
                self.game.round_over_timer = 5.0
            self.game.round_over_timer = max(0.0, self.game.round_over_timer - dt)
            if self.game.round_over_timer <= 0.0:
                self.game.round_over_timer = None
                self.start_round()
            else:
                rebuild_2d_board_objects()


CONTROLLER = BlenderRemi2DController()


# ==============================================================================
# MATERIAL & GEOMETRI VEKTOR 2D DI BLENDER
# ==============================================================================
def get_or_create_color_material(name: str, rgba: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = 0.9
    mat.diffuse_color = rgba
    return mat


def ensure_materials():
    get_or_create_color_material("Mat_Table_2D", (0.04, 0.24, 0.14, 1.0))
    get_or_create_color_material("Mat_Table_Border", (0.18, 0.09, 0.04, 1.0))
    get_or_create_color_material("Mat_Zone_Slot", (0.06, 0.31, 0.18, 1.0))
    get_or_create_color_material("Mat_Player_Zone", (0.03, 0.20, 0.12, 1.0))
    get_or_create_color_material("Mat_Turn_Glow_Gold", (1.0, 0.82, 0.08, 1.0))
    get_or_create_color_material("Mat_Card_Front", (0.98, 0.97, 0.93, 1.0))
    get_or_create_color_material("Mat_Card_Selected", (1.0, 0.92, 0.50, 1.0))
    get_or_create_color_material("Mat_Card_Joker", (0.95, 0.84, 1.0, 1.0))
    get_or_create_color_material("Mat_Card_Locked", (0.35, 0.35, 0.38, 1.0))
    get_or_create_color_material("Mat_Card_Back", (0.58, 0.10, 0.12, 1.0))
    get_or_create_color_material("Mat_Card_Deck", (0.12, 0.28, 0.62, 1.0))
    get_or_create_color_material("Mat_Text_Red", (0.85, 0.08, 0.10, 1.0))
    get_or_create_color_material("Mat_Text_Black", (0.07, 0.08, 0.10, 1.0))
    get_or_create_color_material("Mat_Text_Gold", (0.98, 0.82, 0.14, 1.0))
    get_or_create_color_material("Mat_Text_White", (0.96, 0.98, 0.96, 1.0))
    get_or_create_color_material("Mat_Btn_Green", (0.10, 0.58, 0.24, 1.0))
    get_or_create_color_material("Mat_Btn_Blue", (0.14, 0.40, 0.72, 1.0))
    get_or_create_color_material("Mat_Btn_Orange", (0.86, 0.42, 0.06, 1.0))
    get_or_create_color_material("Mat_Btn_Purple", (0.52, 0.18, 0.75, 1.0))
    get_or_create_color_material("Mat_Btn_Red", (0.78, 0.14, 0.14, 1.0))


def get_dynamic_collection() -> bpy.types.Collection:
    coll = bpy.data.collections.get("Remi2D_Dynamic")
    if coll is None:
        coll = bpy.data.collections.new("Remi2D_Dynamic")
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_dynamic_objects():
    coll = get_dynamic_collection()
    for obj in list(coll.objects):
        mesh_or_curve = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh_or_curve:
            if isinstance(mesh_or_curve, bpy.types.Mesh) and mesh_or_curve.users == 0:
                bpy.data.meshes.remove(mesh_or_curve)
            elif isinstance(mesh_or_curve, bpy.types.Curve) and mesh_or_curve.users == 0:
                bpy.data.curves.remove(mesh_or_curve)


def create_2d_polygon(
    name: str,
    verts: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    x: float,
    y: float,
    z: float,
    mat_name: str,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, z)
    mat = bpy.data.materials.get(mat_name)
    if mat:
        obj.data.materials.append(mat)
        obj.color = mat.diffuse_color
    collection.objects.link(obj)
    return obj


def create_2d_quad(
    name: str,
    x: float,
    y: float,
    z: float,
    w: float,
    h: float,
    mat_name: str,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    hw, hh = w * 0.5, h * 0.5
    verts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)]
    return create_2d_polygon(name, verts, [(0, 1, 2, 3)], x, y, z, mat_name, collection)


def create_2d_border_frame(
    name: str,
    x: float,
    y: float,
    z: float,
    w: float,
    h: float,
    thickness: float,
    mat_name: str,
    collection: bpy.types.Collection,
):
    hw, hh = w * 0.5, h * 0.5
    iw, ih = hw - thickness, hh - thickness
    verts = [
        (-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0),
        (-iw, -ih, 0.0), (iw, -ih, 0.0), (iw, ih, 0.0), (-iw, ih, 0.0),
    ]
    faces = [
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)


def create_2d_suit_emblem(
    name: str,
    suit: str,
    x: float,
    y: float,
    z: float,
    radius: float,
    mat_name: str,
    collection: bpy.types.Collection,
):
    r = radius
    if suit == "D":
        verts = [(0.0, r, 0.0), (r * 0.72, 0.0, 0.0), (0.0, -r, 0.0), (-r * 0.72, 0.0, 0.0)]
        faces = [(0, 1, 2, 3)]
        create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)

    elif suit == "H":
        verts = [
            (0.0, -r * 0.95, 0.0),
            (r * 0.85, -r * 0.05, 0.0),
            (r * 0.80, r * 0.55, 0.0),
            (r * 0.42, r * 0.85, 0.0),
            (0.0, r * 0.42, 0.0),
            (-r * 0.42, r * 0.85, 0.0),
            (-r * 0.80, r * 0.55, 0.0),
            (-r * 0.85, -r * 0.05, 0.0),
        ]
        faces = [(0, 1, 2, 3, 4), (0, 4, 5, 6, 7)]
        create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)

    elif suit == "S":
        verts = [
            (0.0, r * 0.95, 0.0),
            (r * 0.82, -r * 0.05, 0.0),
            (r * 0.48, -r * 0.52, 0.0),
            (0.0, -r * 0.20, 0.0),
            (-r * 0.48, -r * 0.52, 0.0),
            (-r * 0.82, -r * 0.05, 0.0),
            (-r * 0.28, -r * 0.95, 0.0),
            (r * 0.28, -r * 0.95, 0.0),
        ]
        faces = [(0, 1, 2, 3), (0, 3, 4, 5), (3, 6, 7)]
        create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)

    elif suit == "C":
        verts = [
            (0.0, r * 0.95, 0.0),
            (r * 0.42, r * 0.52, 0.0),
            (0.0, r * 0.12, 0.0),
            (-r * 0.42, r * 0.52, 0.0),
            (r * 0.88, r * 0.05, 0.0),
            (r * 0.48, -r * 0.45, 0.0),
            (-r * 0.48, -r * 0.45, 0.0),
            (-r * 0.88, r * 0.05, 0.0),
            (-r * 0.26, -r * 0.95, 0.0),
            (r * 0.26, -r * 0.95, 0.0),
        ]
        faces = [
            (0, 1, 2, 3),
            (2, 1, 4, 5),
            (2, 6, 7, 3),
            (2, 8, 9),
        ]
        create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)

    else:
        verts = [(0.0, 0.0, 0.0)]
        for i in range(10):
            ang = math.pi * 0.5 + i * (math.pi / 5.0)
            rad = r if i % 2 == 0 else r * 0.42
            verts.append((math.cos(ang) * rad, math.sin(ang) * rad, 0.0))
        faces = []
        for i in range(1, 11):
            nxt = 1 if i == 10 else i + 1
            faces.append((0, i, nxt))
        create_2d_polygon(name, verts, faces, x, y, z, mat_name, collection)


def create_2d_text(
    name: str,
    body: str,
    x: float,
    y: float,
    z: float,
    size: float,
    mat_name: str,
    collection: bpy.types.Collection,
    align_x: str = "CENTER",
    align_y: str = "CENTER",
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name=name + "_Font", type="FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align_x
    curve.align_y = align_y
    obj = bpy.data.objects.new(name, curve)
    obj.location = (x, y, z)
    mat = bpy.data.materials.get(mat_name)
    if mat:
        obj.data.materials.append(mat)
        obj.color = mat.diffuse_color
    collection.objects.link(obj)
    return obj


def spawn_2d_card_visual(
    name: str,
    card_dict: dict | None,
    x: float,
    y: float,
    z: float,
    scale: float,
    face_up: bool,
    selected: bool,
    locked: bool,
    collection: bpy.types.Collection,
    badge_text: str = "",
):
    w = 1.15 * scale
    h = 1.65 * scale
    is_wild = bool(card_dict.get("is_wild", False)) if card_dict else False
    border_mat = "Mat_Btn_Purple" if (face_up and is_wild and not locked) else "Mat_Text_Black"
    create_2d_quad(f"{name}_Border", x, y, z, w + 0.07 * scale, h + 0.07 * scale, border_mat, collection)

    if not face_up or card_dict is None:
        create_2d_quad(name, x, y, z + 0.02, w, h, "Mat_Card_Back", collection)
        create_2d_suit_emblem(f"{name}_BackEmb", "D", x, y + 0.15 * scale, z + 0.04, 0.22 * scale, "Mat_Text_Gold", collection)
        create_2d_text(f"{name}_BackTxt", "REMI", x, y - 0.28 * scale, z + 0.04, 0.22 * scale, "Mat_Text_Gold", collection)
        return

    rank = card_dict["rank"]
    suit = card_dict["suit"]
    is_joker = rank == "JOKER"

    if locked:
        front_mat = "Mat_Card_Locked"
    elif selected:
        front_mat = "Mat_Card_Selected"
    elif is_wild:
        front_mat = "Mat_Card_Joker"
    else:
        front_mat = "Mat_Card_Front"

    create_2d_quad(name, x, y, z + 0.02, w, h, front_mat, collection)

    if suit in ("H", "D") or is_joker:
        txt_mat = "Mat_Text_Red"
    else:
        txt_mat = "Mat_Text_Black"

    suit_short = {"S": "WARU", "H": "HATI", "D": "WAJIK", "C": "KRTG", "J": "WILD"}.get(suit, "")
    top_label = "JKR" if is_joker else rank

    if is_wild:
        grp_label = "WILD JKR"
    elif rank == "A":
        grp_label = "ACE +15"
    elif rank in ("J", "Q", "K"):
        grp_label = "FACE +10"
    else:
        grp_label = "NUM +5"

    create_2d_text(
        f"{name}_TL",
        top_label,
        x - w * 0.38,
        y + h * 0.34,
        z + 0.04,
        0.30 * scale,
        txt_mat,
        collection,
        align_x="LEFT",
    )
    create_2d_text(
        f"{name}_TR",
        suit_short,
        x + w * 0.38,
        y + h * 0.34,
        z + 0.04,
        0.13 * scale,
        txt_mat,
        collection,
        align_x="RIGHT",
    )
    create_2d_suit_emblem(
        f"{name}_SuitMesh",
        suit,
        x,
        y + 0.02 * scale,
        z + 0.04,
        0.30 * scale,
        txt_mat,
        collection,
    )
    create_2d_text(
        f"{name}_Grp",
        badge_text if badge_text else grp_label,
        x,
        y - h * 0.36,
        z + 0.04,
        0.16 * scale,
        "Mat_Text_White" if locked else txt_mat,
        collection,
    )


def apply_clean_2d_viewport_settings():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "SOLID"
                        space.shading.light = "FLAT"
                        space.shading.color_type = "OBJECT"
                        space.show_gizmo = False
                        space.overlay.show_floor = False
                        space.overlay.show_axis_x = False
                        space.overlay.show_axis_y = False
                        space.overlay.show_cursor = False
                        space.overlay.show_extras = False
                        space.overlay.show_relationship_lines = False
                        space.overlay.show_object_origins = False
                        space.overlay.show_outline_selected = False
                        if space.region_3d:
                            space.region_3d.view_perspective = "CAMERA"


def setup_static_2d_table():
    ensure_materials()
    static_coll = bpy.data.collections.get("Remi2D_Static")
    if static_coll is None:
        static_coll = bpy.data.collections.new("Remi2D_Static")
        bpy.context.scene.collection.children.link(static_coll)

    for obj in list(static_coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    create_2d_quad("Table_Border_2D", 0.0, 0.0, -0.15, 22.8, 14.8, "Mat_Table_Border", static_coll)
    create_2d_quad("Table_Canvas_2D", 0.0, 0.0, -0.10, 22.0, 14.0, "Mat_Table_2D", static_coll)

    create_2d_quad("Zone_Top_Player", 0.0, 3.55, -0.06, 11.2, 2.95, "Mat_Player_Zone", static_coll)
    create_2d_quad("Zone_Left_Player", -8.3, 1.70, -0.06, 4.5, 6.65, "Mat_Player_Zone", static_coll)
    create_2d_quad("Zone_Right_Player", 8.3, 1.70, -0.06, 4.5, 6.65, "Mat_Player_Zone", static_coll)
    create_2d_quad("Discard_Zone_2D", 1.35, 0.60, -0.06, 8.5, 2.25, "Mat_Zone_Slot", static_coll)
    create_2d_quad("Zone_Bottom_Melds", 0.0, -1.52, -0.06, 11.2, 1.42, "Mat_Zone_Slot", static_coll)
    create_2d_quad("Zone_Bottom_Player", 0.0, -3.65, -0.07, 11.2, 2.65, "Mat_Player_Zone", static_coll)

    cam_obj = bpy.data.objects.get("Camera_2D")
    if cam_obj is None:
        cam_data = bpy.data.cameras.new("Camera_2D")
        cam_obj = bpy.data.objects.new("Camera_2D", cam_data)
        static_coll.objects.link(cam_obj)
    cam_obj.data.type = "ORTHO"
    cam_obj.data.ortho_scale = 23.0
    cam_obj.data.show_limits = False
    cam_obj.data.show_name = False
    cam_obj.location = (0.0, 0.0, 15.0)
    cam_obj.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.camera = cam_obj

    sun_obj = bpy.data.objects.get("Sun_2D")
    if sun_obj is None:
        light_data = bpy.data.lights.new(name="Sun_2D", type="SUN")
        light_data.energy = 3.5
        sun_obj = bpy.data.objects.new(name="Sun_2D", object_data=light_data)
        static_coll.objects.link(sun_obj)
    sun_obj.location = (0.0, 0.0, 10.0)
    sun_obj.hide_viewport = True


def _draw_meld_groups_in_box(
    prefix: str,
    melds: list[list[dict]],
    box_left_x: float,
    box_top_y: float,
    max_width: float,
    card_scale: float,
    row_step_y: float,
    collection: bpy.types.Collection,
):
    step_x = 0.72 * card_scale / 0.55
    gap_between_melds = 0.38 * card_scale / 0.55
    cur_x = box_left_x
    cur_y = box_top_y
    z_base = 0.05

    for m_idx, meld in enumerate(melds):
        meld_width = len(meld) * step_x
        if cur_x > box_left_x and (cur_x + meld_width - box_left_x) > max_width:
            cur_x = box_left_x
            cur_y -= row_step_y

        for c_idx, c_dict in enumerate(meld):
            spawn_2d_card_visual(
                f"{prefix}_Meld_{m_idx}_{c_idx}",
                c_dict,
                cur_x,
                cur_y,
                z_base + (m_idx * 4 + c_idx) * 0.005,
                card_scale,
                face_up=True,
                selected=False,
                locked=False,
                collection=collection,
            )
            cur_x += step_x
        cur_x += gap_between_melds


def format_timer_text(st: dict) -> str:
    if st.get("phase") not in ("TURN_DRAW", "TURN_MELD_DISCARD"):
        return "TIMER: --"
    if st.get("turn_timer_sec", 25) <= 0:
        return "TIMER: INF"
    return f"TIMER: {int(math.ceil(float(st.get('turn_remaining_sec', 0))))}s"


def update_timer_indicator():
    """Perbarui teks timer di meja tanpa membangun ulang seluruh papan."""
    obj = bpy.data.objects.get("Timer_Txt")
    if obj is None or obj.type != "FONT":
        return
    st = CONTROLLER.get_active_state()
    if not st:
        return
    txt = format_timer_text(st)
    if obj.data.body != txt:
        obj.data.body = txt
        remaining = float(st.get("turn_remaining_sec", 0))
        if txt != "TIMER: --" and remaining <= 5.0:
            obj.color = (1.0, 0.25, 0.25, 1.0)
        else:
            obj.color = (1.0, 1.0, 1.0, 1.0)


def rebuild_2d_board_objects():
    ensure_materials()
    clear_dynamic_objects()
    coll = get_dynamic_collection()
    CONTROLLER.hitboxes_2d.clear()

    st = CONTROLLER.get_active_state()
    my_seat = CONTROLLER.my_seat
    players = st["players"]
    phase = st["phase"]
    current_turn = st["current_turn_seat"]
    w_rank = st.get("wildcard_rank")
    w_ind = st.get("wildcard_indicator")

    # 1. Header & BANNER INDIKATOR GILIRAN BESAR BERWARNA KONTRAS
    header_txt = (
        f"REMI NUSANTARA 2D  |  Room: #{st['room_code']}  |  Ronde: {st['round_number']}  |  "
        f"Target: {st['target_score']} Poin  |  4 Wild Card (1 Joker + 3 Kartu '{w_rank}')"
    )
    create_2d_text("Header_Title", header_txt, 0.0, 6.52, 0.05, 0.30, "Mat_Text_Gold", coll)

    turn_banner_txt, turn_banner_mat = CONTROLLER.get_turn_banner_info(st)
    create_2d_quad("Turn_Banner_Bg", 0.0, 5.95, 0.03, 19.6, 0.56, turn_banner_mat, coll)
    create_2d_text("Turn_Banner_Txt", turn_banner_txt, 0.0, 5.95, 0.06, 0.24, "Mat_Text_White", coll)

    create_2d_text("Status_Banner", CONTROLLER.feedback_banner, 0.0, 5.38, 0.05, 0.23, "Mat_Text_Gold", coll)

    # INDIKATOR TIMER GILIRAN (badge besar di kanan atas, diperbarui live setiap tick)
    create_2d_quad("Timer_Badge_Bg", 8.75, 6.52, 0.03, 2.1, 0.50, "Mat_Card_Deck", coll)
    create_2d_text("Timer_Txt", format_timer_text(st), 8.75, 6.52, 0.06, 0.26, "Mat_Text_White", coll)

    # 2. PAK / DRAW PILE & KARTU BUKAAN WILDCARD PERTAMA
    pak_x, pak_y = -4.95, 0.55
    is_my_draw = (current_turn == my_seat and phase == "TURN_DRAW")
    if is_my_draw:
        create_2d_border_frame("Pak_Glow", pak_x, pak_y, 0.03, 1.48, 1.96, 0.08, "Mat_Turn_Glow_Gold", coll)
    create_2d_quad("Pak_Slot", pak_x, pak_y, 0.02, 1.32, 1.80, "Mat_Card_Deck", coll)
    create_2d_text("Pak_Label", f"PAK\n({st['draw_pile_count']})", pak_x, pak_y + 0.16, 0.06, 0.22, "Mat_Text_Gold", coll)
    create_2d_text("Pak_Hint", "[KLIK AMBIL]", pak_x, pak_y - 0.58, 0.06, 0.16, "Mat_Text_White", coll)
    CONTROLLER.hitboxes_2d.append((pak_x - 0.70, pak_y - 0.95, pak_x + 0.70, pak_y + 0.95, "DRAW_DECK", ""))

    # KARTU BUKAAN WILDCARD (Penentu 3 kartu se-angka yang jadi Wild Card!)
    if w_ind:
        wx, wy = -3.55, 0.42
        create_2d_text("Wild_Title", f"BUKAAN\nWILD={w_rank}", wx, 1.38, 0.05, 0.17, "Mat_Text_Gold", coll)
        spawn_2d_card_visual(
            "Wildcard_Indicator",
            w_ind,
            wx,
            wy,
            0.05,
            0.68,
            face_up=True,
            selected=False,
            locked=False,
            collection=coll,
            badge_text=f"PATOKAN {w_rank}",
        )

    # 3. TUMPUKAN BUANGAN / DISCARD PILE
    disc_list = st["discard_pile"]
    total_disc = len(disc_list)
    create_2d_text(
        "Discard_Title",
        f"TUMPUKAN BUANGAN (Total: {total_disc} Kartu - Maks Ambil 7 Teratas)",
        1.35,
        1.45,
        0.05,
        0.21,
        "Mat_Text_Gold",
        coll,
    )

    visible_disc = list(enumerate(disc_list))[-7:]
    start_x = -2.15
    spacing_x = 1.12

    # Cari index tertinggi Wild Card di tumpukan buangan
    # Wild Card yang dibuang dan kartu-kartu di bawahnya otomatis TERKUNCI (locked)
    highest_wild_idx = -1
    for i in range(total_disc - 1, -1, -1):
        if disc_list[i].get("is_wild", False):
            if i > highest_wild_idx:
                highest_wild_idx = i

    for vis_i, (real_idx, c_dict) in enumerate(visible_disc):
        depth_from_top = total_disc - real_idx
        is_exceed = depth_from_top > MAX_DISCARD_TAKE_DEPTH
        has_wild_in_slice = (highest_wild_idx != -1 and real_idx <= highest_wild_idx)
        locked = is_exceed or has_wild_in_slice

        cx = start_x + vis_i * spacing_x
        cy = 0.42
        if c_dict.get("is_wild", False):
            badge = "WILD MATI"
        elif locked:
            badge = "LOCKED"
        else:
            badge = f"AMBIL #{depth_from_top}"

        spawn_2d_card_visual(
            f"Discard_{real_idx}",
            c_dict,
            cx,
            cy,
            0.05 + vis_i * 0.005,
            0.70,
            face_up=True,
            selected=False,
            locked=locked,
            collection=coll,
            badge_text=badge,
        )
        if not locked:
            CONTROLLER.hitboxes_2d.append(
                (cx - 0.45, cy - 0.65, cx + 0.45, cy + 0.65, "TAKE_DISCARD", str(real_idx))
            )

    # 4. KE-4 PEMAIN DENGAN INDIKATOR GILIRAN MENYALA & STATUS SERI WAJIB
    rel_seats = [(my_seat + offset) % len(players) for offset in range(len(players))]

    for pos_idx, seat_idx in enumerate(rel_seats):
        p = players[seat_idx]
        is_turn = (seat_idx == current_turn) and phase in ("TURN_DRAW", "TURN_MELD_DISCARD")
        closer_seat = st.get("highest_score_seat", st.get("starter_seat"))
        closer_tag = " [👑 SKOR TERTINGGI - MAIN TERUS]" if (closer_seat is not None and seat_idx == closer_seat and (st.get("round_number", 1) > 1 or p.get("total_score", 0) > 0)) else ""
        burn_tag = " [TERBAKAR!]" if p.get("burned_last_round") else ""
        score_str = f"{p['name']}{closer_tag}  |  Skor: {p['total_score']}/{st['target_score']} ({p['last_round_score']:+d}){burn_tag}"

        if pos_idx == 0:
            # ================= PEMAIN UTAMA (ANDA - BAWAH TENGAH) =================
            if is_turn:
                create_2d_border_frame(
                    "Active_Turn_Frame_P0", 0.0, -3.65, 0.01, 11.35, 2.78, 0.11, "Mat_Turn_Glow_Gold", coll
                )
                create_2d_quad("Badge_Turn_P0_Bg", -3.9, -2.55, 0.04, 3.1, 0.42, "Mat_Btn_Green", coll)
                create_2d_text("Badge_Turn_P0_Txt", ">> GILIRAN ANDA! <<", -3.9, -2.55, 0.07, 0.20, "Mat_Text_White", coll)

            seri_status = "SERI WAJIB: AMAN" if p.get("has_seri") else "BELUM ADA SERI MIN 3 (AWAS TERBAKAR!)"
            seri_mat = "Mat_Text_Gold" if p.get("has_seri") else "Mat_Text_White"
            create_2d_text(
                "P0_Meld_Label",
                f"KARTU JADI ANDA\n({seri_status}):",
                -5.35,
                -1.15,
                0.05,
                0.16,
                seri_mat,
                coll,
                align_x="LEFT",
            )
            _draw_meld_groups_in_box(
                prefix="P0",
                melds=p["melds"],
                box_left_x=-2.15,
                box_top_y=-1.52,
                max_width=7.5,
                card_scale=0.52,
                row_step_y=0.75,
                collection=coll,
            )

            create_2d_text(
                "P0_Info",
                score_str,
                0.85 if is_turn else 0.0,
                -2.55,
                0.05,
                0.25,
                "Mat_Text_Gold" if is_turn else "Mat_Text_White",
                coll,
            )

            hand_cards = p["hand"]
            n_hand = len(hand_cards)
            hand_spacing = min(1.24, 10.6 / max(1, n_hand))
            hand_start_x = -((n_hand - 1) * hand_spacing) * 0.5
            for h_idx, c_dict in enumerate(hand_cards):
                cid = c_dict["id"]
                is_sel = cid in CONTROLLER.selected_card_ids
                hx = hand_start_x + h_idx * hand_spacing
                hy = -3.55 if is_sel else -3.95
                spawn_2d_card_visual(
                    f"P0_Hand_{cid}",
                    c_dict,
                    hx,
                    hy,
                    0.08 + h_idx * 0.005,
                    0.95,
                    face_up=True,
                    selected=is_sel,
                    locked=False,
                    collection=coll,
                )
                CONTROLLER.hitboxes_2d.append((hx - 0.55, hy - 0.82, hx + 0.55, hy + 0.82, "SELECT_CARD", cid))

        elif pos_idx == 1:
            # ================= PEMAIN KIRI (BOT BUDI) =================
            if is_turn:
                create_2d_border_frame(
                    "Active_Turn_Frame_P1", -8.3, 1.70, 0.01, 4.65, 6.80, 0.11, "Mat_Turn_Glow_Gold", coll
                )
                create_2d_quad("Badge_Turn_P1_Bg", -8.3, 4.82, 0.04, 3.6, 0.38, "Mat_Btn_Orange", coll)
                create_2d_text("Badge_Turn_P1_Txt", ">> SEDANG JALAN <<", -8.3, 4.82, 0.07, 0.19, "Mat_Text_White", coll)

            create_2d_text(
                "P1_Info",
                f"{p['name']}{closer_tag}{burn_tag}\nSkor: {p['total_score']}/{st['target_score']} ({p['last_round_score']:+d})",
                -8.3,
                4.28,
                0.05,
                0.20,
                "Mat_Text_Gold" if is_turn else "Mat_Text_White",
                coll,
            )
            show_face = phase in ("ROUND_OVER", "MATCH_OVER")
            h_count = p["hand_count"]
            h_space = min(0.55, 3.4 / max(1, h_count))
            h_start_x = -8.3 - ((h_count - 1) * h_space) * 0.5
            for i in range(h_count):
                c_dict = p["hand"][i] if (show_face and i < len(p["hand"])) else None
                spawn_2d_card_visual(
                    f"P1_Hand_{i}",
                    c_dict,
                    h_start_x + i * h_space,
                    3.42,
                    0.05 + i * 0.004,
                    0.42,
                    face_up=show_face,
                    selected=False,
                    locked=False,
                    collection=coll,
                )
            create_2d_text("P1_MeldLbl", "Kartu Jadi:", -10.25, 2.68, 0.05, 0.17, "Mat_Text_Gold", coll, align_x="LEFT")
            _draw_meld_groups_in_box(
                prefix="P1",
                melds=p["melds"],
                box_left_x=-10.0,
                box_top_y=2.00,
                max_width=3.6,
                card_scale=0.42,
                row_step_y=0.82,
                collection=coll,
            )

        elif pos_idx == 2:
            # ================= PEMAIN ATAS (BOT SITI) =================
            if is_turn:
                create_2d_border_frame(
                    "Active_Turn_Frame_P2", 0.0, 3.55, 0.01, 11.35, 3.10, 0.11, "Mat_Turn_Glow_Gold", coll
                )
                create_2d_quad("Badge_Turn_P2_Bg", -3.8, 4.75, 0.04, 3.2, 0.38, "Mat_Btn_Orange", coll)
                create_2d_text("Badge_Turn_P2_Txt", ">> SEDANG JALAN <<", -3.8, 4.75, 0.07, 0.19, "Mat_Text_White", coll)

            create_2d_text(
                "P2_Info",
                score_str,
                0.8 if is_turn else 0.0,
                4.75,
                0.05,
                0.23,
                "Mat_Text_Gold" if is_turn else "Mat_Text_White",
                coll,
            )
            show_face = phase in ("ROUND_OVER", "MATCH_OVER")
            h_count = p["hand_count"]
            start_top_x = -((h_count - 1) * 0.62) * 0.5
            for i in range(h_count):
                c_dict = p["hand"][i] if (show_face and i < len(p["hand"])) else None
                spawn_2d_card_visual(
                    f"P2_Hand_{i}",
                    c_dict,
                    start_top_x + i * 0.62,
                    3.90,
                    0.05 + i * 0.004,
                    0.46,
                    face_up=show_face,
                    selected=False,
                    locked=False,
                    collection=coll,
                )
            _draw_meld_groups_in_box(
                prefix="P2",
                melds=p["melds"],
                box_left_x=-4.8,
                box_top_y=2.68,
                max_width=9.6,
                card_scale=0.45,
                row_step_y=0.78,
                collection=coll,
            )

        elif pos_idx == 3:
            # ================= PEMAIN KANAN (BOT AGUS) =================
            if is_turn:
                create_2d_border_frame(
                    "Active_Turn_Frame_P3", 8.3, 1.70, 0.01, 4.65, 6.80, 0.11, "Mat_Turn_Glow_Gold", coll
                )
                create_2d_quad("Badge_Turn_P3_Bg", 8.3, 4.82, 0.04, 3.6, 0.38, "Mat_Btn_Orange", coll)
                create_2d_text("Badge_Turn_P3_Txt", ">> SEDANG JALAN <<", 8.3, 4.82, 0.07, 0.19, "Mat_Text_White", coll)

            create_2d_text(
                "P3_Info",
                f"{p['name']}{closer_tag}{burn_tag}\nSkor: {p['total_score']}/{st['target_score']} ({p['last_round_score']:+d})",
                8.3,
                4.28,
                0.05,
                0.20,
                "Mat_Text_Gold" if is_turn else "Mat_Text_White",
                coll,
            )
            show_face = phase in ("ROUND_OVER", "MATCH_OVER")
            h_count = p["hand_count"]
            h_space = min(0.55, 3.4 / max(1, h_count))
            h_start_x = 8.3 - ((h_count - 1) * h_space) * 0.5
            for i in range(h_count):
                c_dict = p["hand"][i] if (show_face and i < len(p["hand"])) else None
                spawn_2d_card_visual(
                    f"P3_Hand_{i}",
                    c_dict,
                    h_start_x + i * h_space,
                    3.42,
                    0.05 + i * 0.004,
                    0.42,
                    face_up=show_face,
                    selected=False,
                    locked=False,
                    collection=coll,
                )
            create_2d_text("P3_MeldLbl", "Kartu Jadi:", 6.35, 2.68, 0.05, 0.17, "Mat_Text_Gold", coll, align_x="LEFT")
            _draw_meld_groups_in_box(
                prefix="P3",
                melds=p["melds"],
                box_left_x=6.6,
                box_top_y=2.00,
                max_width=3.6,
                card_scale=0.42,
                row_step_y=0.82,
                collection=coll,
            )

    # 5. TOMBOL AKSI 2D DI BAWAH MEJA (Dikembalikan bersama AUTO TURUN (A))
    can_tutup, cand_cid = CONTROLLER.game.check_can_declare_tutup_tangan(CONTROLLER.my_seat)
    disc_label = f"TUTUP TANGAN +250 (B)" if can_tutup else "BUANG KARTU (B)"
    disc_mat = "Mat_Btn_Green" if can_tutup else "Mat_Btn_Orange"

    buttons = [
        ("Btn_DrawPak", "AMBIL PAK (D)", -6.8, -5.85, 3.2, 0.78, "Mat_Btn_Blue", "DRAW_DECK"),
        ("Btn_MeldSel", "TURUNKAN PILIHAN (M)", -3.2, -5.85, 3.4, 0.78, "Mat_Btn_Green", "ACTION_MELD_SELECTED"),
        ("Btn_AutoMeld", "AUTO TURUN (A)", 0.6, -5.85, 3.2, 0.78, "Mat_Btn_Blue", "ACTION_AUTO_MELD"),
        ("Btn_Discard", disc_label, 4.6, -5.85, 3.8, 0.78, disc_mat, "ACTION_DISCARD"),
        ("Btn_SortRank", "URUT ANGKA (S)", 8.6, -5.45, 2.5, 0.55, "Mat_Btn_Blue", "ACTION_SORT_RANK"),
        ("Btn_SortSuit", "URUT KEMBANG (F)", 8.6, -6.15, 2.5, 0.55, "Mat_Btn_Blue", "ACTION_SORT_SUIT"),
    ]
    for b_name, b_label, bx, by, bw, bh, b_mat, b_act in buttons:
        create_2d_quad(b_name, bx, by, 0.04, bw, bh, b_mat, coll)
        create_2d_text(f"{b_name}_Txt", b_label, bx, by, 0.08, 0.20, "Mat_Text_White", coll)
        CONTROLLER.hitboxes_2d.append((bx - bw * 0.5, by - bh * 0.5, bx + bw * 0.5, by + bh * 0.5, b_act, ""))


# ==============================================================================
# PICKING KOORDINAT 2D DARI MOUSE KE BIDANG MEJA Z=0
# ==============================================================================
def region_mouse_to_table_xy(context, event) -> tuple[float, float] | None:
    region = context.region
    rv3d = context.region_data
    if not region or not rv3d:
        return None
    coord = (event.mouse_region_x, event.mouse_region_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    if abs(direction.z) < 1e-6:
        return (origin.x, origin.y)
    t = -origin.z / direction.z
    hit = origin + direction * t
    return (hit.x, hit.y)


def handle_table_2d_click(x: float, y: float, right_click: bool = False):
    for x1, y1, x2, y2, act, payload in reversed(CONTROLLER.hitboxes_2d):
        if x1 <= x <= x2 and y1 <= y <= y2:
            if right_click:
                if act == "SELECT_CARD":
                    CONTROLLER.discard_selected_or_card(payload)
                    return True
                return False

            if act == "SELECT_CARD":
                CONTROLLER.toggle_card_selection(payload)
            elif act == "DRAW_DECK":
                CONTROLLER.draw_from_deck()
            elif act == "TAKE_DISCARD":
                CONTROLLER.take_discard(int(payload))
            elif act == "ACTION_START_ROUND":
                CONTROLLER.start_round()
            elif act == "ACTION_MELD_SELECTED":
                CONTROLLER.meld_selected()
            elif act == "ACTION_AUTO_MELD":
                CONTROLLER.auto_meld()
            elif act == "ACTION_DISCARD":
                CONTROLLER.discard_selected_or_card()
            elif act == "ACTION_SORT_RANK":
                CONTROLLER.sort_hand(by_suit=False)
            elif act == "ACTION_SORT_SUIT":
                CONTROLLER.sort_hand(by_suit=True)
            return True
    return False


# ==============================================================================
# HUD OVERLAY 2D (BLF FONT OVERLAY DI VIEWPORT)
# ==============================================================================
def draw_2d_hud_callback():
    st = CONTROLLER.get_active_state()
    font_id = 0
    cur_name = st["players"][st["current_turn_seat"]]["name"]
    is_my_turn = st["current_turn_seat"] == CONTROLLER.my_seat
    w_rank = st.get("wildcard_rank", "-")

    blf.size(font_id, 16)
    if is_my_turn:
        blf.color(font_id, 0.25, 1.0, 0.45, 1.0)
        turn_hud = f">> GILIRAN ANDA SEKARANG ({cur_name}) <<"
    else:
        blf.color(font_id, 1.0, 0.72, 0.22, 1.0)
        turn_hud = f">> SEDANG GILIRAN: {cur_name.upper()} <<"

    blf.position(font_id, 20, 52, 0)
    blf.draw(font_id, f"{turn_hud}  |  4 Wildcard: JOKER & Angka '{w_rank}'  |  Timer: {st['turn_remaining_sec']}s")

    blf.size(font_id, 13)
    blf.color(font_id, 0.92, 0.98, 0.92, 1.0)
    blf.position(font_id, 20, 28, 0)
    blf.draw(
        font_id,
        "Aturan Wajib: Harus punya minimal 1 Kartu Urut (Seri min 3 kartu) agar tidak TERBAKAR SEMUA di akhir ronde!",
    )


# ==============================================================================
# BLENDER OPERATORS & MODAL GAME CONTROLLER
# ==============================================================================
class REMI2D_OT_StartModalGame(bpy.types.Operator):
    bl_idname = "remi2d.start_modal_game"
    bl_label = "Mainkan Interaktif 2D (Klik Kartu di Layar)"
    bl_description = "Mengaktifkan kontrol klik langsung 2D pada meja Remi dan timer giliran otomatis"

    _timer = None

    def modal(self, context, event):
        if not CONTROLLER.modal_running:
            self.cancel(context)
            return {"CANCELLED"}

        if event.type == "TIMER":
            CONTROLLER.tick()
            update_timer_indicator()
            if context.area:
                context.area.tag_redraw()
            return {"PASS_THROUGH"}

        # Klik Kanan langsung membuang / menutup kartu yang diklik
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            if context.area and context.area.type == "VIEW_3D":
                if event.mouse_region_x > 0 and event.mouse_region_y > 0:
                    xy = region_mouse_to_table_xy(context, event)
                    if xy and handle_table_2d_click(xy[0], xy[1], right_click=True):
                        context.area.tag_redraw()
                        return {"RUNNING_MODAL"}

        # Klik Kiri TEKAN (PRESS): Deteksi awal drag atau klik tombol/kartu
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if context.area and context.area.type == "VIEW_3D":
                if event.mouse_region_x > 0 and event.mouse_region_y > 0:
                    xy = region_mouse_to_table_xy(context, event)
                    if xy:
                        hit_act = None
                        hit_pld = ""
                        for x1, y1, x2, y2, act, payload in reversed(CONTROLLER.hitboxes_2d):
                            if x1 <= xy[0] <= x2 and y1 <= xy[1] <= y2:
                                hit_act = act
                                hit_pld = payload
                                break

                        if hit_act == "SELECT_CARD":
                            cid = hit_pld
                            coll = bpy.data.collections.get("Remi_2D_Game_Objects")
                            orig_locs = {}
                            if coll:
                                for obj in coll.objects:
                                    if obj.name == f"P0_Hand_{cid}" or obj.name.startswith(f"P0_Hand_{cid}_"):
                                        orig_locs[obj.name] = (obj.location.x, obj.location.y, obj.location.z)
                            CONTROLLER.drag_state = {
                                "active": False,
                                "type": "HAND_CARD",
                                "card_id": cid,
                                "start_screen": (event.mouse_region_x, event.mouse_region_y),
                                "start_table": (xy[0], xy[1]),
                                "orig_locs": orig_locs,
                            }
                            return {"RUNNING_MODAL"}

                        elif hit_act == "DRAW_DECK":
                            CONTROLLER.drag_state = {
                                "active": False,
                                "type": "PAK_DECK",
                                "start_screen": (event.mouse_region_x, event.mouse_region_y),
                                "start_table": (xy[0], xy[1]),
                            }
                            return {"RUNNING_MODAL"}

                        elif hit_act == "TAKE_DISCARD":
                            CONTROLLER.drag_state = {
                                "active": False,
                                "type": "DISCARD_CARD",
                                "discard_idx": int(hit_pld),
                                "start_screen": (event.mouse_region_x, event.mouse_region_y),
                                "start_table": (xy[0], xy[1]),
                            }
                            return {"RUNNING_MODAL"}

                        elif hit_act is not None:
                            # Tombol menu aksi atau lainnya, jalankan langsung
                            if handle_table_2d_click(xy[0], xy[1], right_click=False):
                                context.area.tag_redraw()
                                return {"RUNNING_MODAL"}

        # Gerakan Mouse (MOUSEMOVE): Geser visual kartu mengambang jika sedang drag
        if event.type == "MOUSEMOVE" and CONTROLLER.drag_state:
            ds = CONTROLLER.drag_state
            dist = math.hypot(
                event.mouse_region_x - ds["start_screen"][0],
                event.mouse_region_y - ds["start_screen"][1],
            )
            if dist > 6:
                ds["active"] = True
                xy = region_mouse_to_table_xy(context, event)
                if xy:
                    dx = xy[0] - ds["start_table"][0]
                    dy = xy[1] - ds["start_table"][1]
                    if ds["type"] == "HAND_CARD":
                        cid = ds["card_id"]
                        for name, (ox, oy, oz) in ds.get("orig_locs", {}).items():
                            obj = bpy.data.objects.get(name)
                            if obj:
                                obj.location.x = ox + dx
                                obj.location.y = oy + dy
                                obj.location.z = oz + 0.35  # Mengambang di atas meja
                        if xy[1] > -0.7 and -3.0 <= xy[0] <= 7.0:
                            CONTROLLER.update_status_banner_text(f"[LEPAS DI SINI] Buang / Tutup Kartu {cid}!")
                        elif -2.5 < xy[1] <= -0.7 and -5.0 <= xy[0] <= 6.5:
                            CONTROLLER.update_status_banner_text(f"[LEPAS DI SINI] Turunkan Kartu Jadi (Meld) untuk {cid}!")
                        else:
                            target_cid = None
                            for x1, y1, x2, y2, act, pld in reversed(CONTROLLER.hitboxes_2d):
                                if act == "SELECT_CARD" and pld != cid and x1 <= xy[0] <= x2 and y1 <= xy[1] <= y2:
                                    target_cid = pld
                                    break
                            if target_cid:
                                CONTROLLER.update_status_banner_text(f"[LEPAS DI SINI] Pindahkan posisi {cid} ke {target_cid}")
                            else:
                                CONTROLLER.update_status_banner_text(f"Menyeret kartu {cid}...")
                    elif ds["type"] == "PAK_DECK":
                        if xy[1] < -1.5:
                            CONTROLLER.update_status_banner_text("[LEPAS DI TANGAN] Ambil 1 kartu dari Pak ke tangan Anda!")
                        else:
                            CONTROLLER.update_status_banner_text("Tarik Pak ke bawah (area tangan) untuk mengambil kartu.")
                    elif ds["type"] == "DISCARD_CARD":
                        if xy[1] < -1.5:
                            CONTROLLER.update_status_banner_text(f"[LEPAS DI TANGAN] Ambil kartu buangan #{ds['discard_idx']} ke tangan Anda!")
                        else:
                            CONTROLLER.update_status_banner_text("Tarik kartu buangan ke bawah (area tangan) untuk mengambil.")
                if context.area:
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}

        # Klik Kiri DILEPAS (RELEASE): Eksekusi Drop atau Klik Biasa
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if CONTROLLER.drag_state:
                ds = CONTROLLER.drag_state
                CONTROLLER.drag_state = None
                if ds.get("active"):
                    xy = region_mouse_to_table_xy(context, event)
                    if not xy:
                        xy = ds["start_table"]
                    cur_x, cur_y = xy
                    if ds["type"] == "HAND_CARD":
                        cid = ds["card_id"]
                        # Target 1: Area Buang / Tutup (+250 / biasa)
                        if cur_y > -0.7 and -3.0 <= cur_x <= 7.0:
                            CONTROLLER.discard_selected_or_card(cid)
                        # Target 2: Area Kartu Jadi (Melds)
                        elif -2.5 < cur_y <= -0.7 and -5.0 <= cur_x <= 6.5:
                            if cid not in CONTROLLER.selected_card_ids:
                                CONTROLLER.selected_card_ids.add(cid)
                            if len(CONTROLLER.selected_card_ids) >= 3:
                                CONTROLLER.meld_selected()
                            else:
                                CONTROLLER.feedback_banner = f"Kartu {cid} dipilih untuk kartu jadi. Pilih/tarik minimal 3 kartu lalu turunkan!"
                                rebuild_2d_board_objects()
                        else:
                            # Target 3: Cek apakah dijatuhkan di atas kartu tangan lain (Reorder/Geser urutan tangan)
                            target_cid = None
                            for x1, y1, x2, y2, act, pld in reversed(CONTROLLER.hitboxes_2d):
                                if act == "SELECT_CARD" and pld != cid and x1 <= cur_x <= x2 and y1 <= cur_y <= y2:
                                    target_cid = pld
                                    break
                            if target_cid:
                                CONTROLLER.reorder_hand_card(cid, target_cid)
                            else:
                                rebuild_2d_board_objects()
                    elif ds["type"] == "PAK_DECK":
                        if cur_y < -1.5:
                            CONTROLLER.draw_from_deck()
                        else:
                            rebuild_2d_board_objects()
                    elif ds["type"] == "DISCARD_CARD":
                        if cur_y < -1.5:
                            CONTROLLER.take_discard(ds["discard_idx"])
                        else:
                            rebuild_2d_board_objects()
                    if context.area:
                        context.area.tag_redraw()
                    return {"RUNNING_MODAL"}
                else:
                    # Tidak di-drag (hanya klik singkat di tempat) -> jalankan aksi klik normal
                    start_xy = ds["start_table"]
                    if handle_table_2d_click(start_xy[0], start_xy[1], right_click=False):
                        if context.area:
                            context.area.tag_redraw()
                        return {"RUNNING_MODAL"}

        if event.value == "PRESS":
            if event.type == "SPACE":
                if CONTROLLER.game.phase == "MATCH_OVER":
                    CONTROLLER.start_round()
                return {"RUNNING_MODAL"}
            elif event.type == "D":
                CONTROLLER.draw_from_deck()
                return {"RUNNING_MODAL"}
            elif event.type == "M":
                CONTROLLER.meld_selected()
                return {"RUNNING_MODAL"}
            elif event.type == "A":
                CONTROLLER.auto_meld()
                return {"RUNNING_MODAL"}
            elif event.type == "B":
                CONTROLLER.discard_selected_or_card()
                return {"RUNNING_MODAL"}
            elif event.type == "S":
                CONTROLLER.sort_hand(by_suit=False)
                return {"RUNNING_MODAL"}
            elif event.type == "F":
                CONTROLLER.sort_hand(by_suit=True)
                return {"RUNNING_MODAL"}
            elif event.type == "ESC":
                CONTROLLER.modal_running = False
                self.cancel(context)
                return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def execute(self, context):
        setup_static_2d_table()
        if CONTROLLER.game.phase == "LOBBY":
            CONTROLLER.start_round()
        else:
            rebuild_2d_board_objects()

        apply_clean_2d_viewport_settings()

        if CONTROLLER.draw_handler is None:
            CONTROLLER.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                draw_2d_hud_callback, (), "WINDOW", "POST_PIXEL"
            )

        CONTROLLER.modal_running = True
        CONTROLLER.last_timer_tick = time.time()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.15, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if CONTROLLER.drag_state:
            CONTROLLER.drag_state = None
            rebuild_2d_board_objects()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


class REMI2D_OT_QuickAction(bpy.types.Operator):
    bl_idname = "remi2d.quick_action"
    bl_label = "Aksi Cepat Remi 2D"
    action: bpy.props.StringProperty()
    payload: bpy.props.StringProperty(default="")

    def execute(self, context):
        act = self.action
        if act == "INIT_BOARD":
            setup_static_2d_table()
            rebuild_2d_board_objects()
            apply_clean_2d_viewport_settings()
        elif act == "START_ROUND":
            setup_static_2d_table()
            CONTROLLER.start_round()
            apply_clean_2d_viewport_settings()
        elif act == "DRAW_DECK":
            CONTROLLER.draw_from_deck()
        elif act == "TAKE_DISCARD":
            CONTROLLER.take_discard(int(self.payload))
        elif act == "MELD_SELECTED":
            CONTROLLER.meld_selected()
        elif act == "AUTO_MELD":
            CONTROLLER.auto_meld()
        elif act == "DISCARD":
            CONTROLLER.discard_selected_or_card(self.payload if self.payload else None)
        elif act == "SORT_RANK":
            CONTROLLER.sort_hand(by_suit=False)
        elif act == "SORT_SUIT":
            CONTROLLER.sort_hand(by_suit=True)
        elif act == "TOGGLE_CARD":
            CONTROLLER.toggle_card_selection(self.payload)
        elif act == "BOT_STEP":
            CONTROLLER.game.execute_bot_or_timeout_step()
            rebuild_2d_board_objects()
        elif act == "HOST_SERVER":
            if CONTROLLER.server is None:
                CONTROLLER.server = RemiTCPServer(
                    host="127.0.0.1",
                    port=context.scene.remi2d_port,
                    room_code=context.scene.remi2d_room_code,
                )
            ok, msg = CONTROLLER.server.start()
            CONTROLLER.mode = "HOST"
            CONTROLLER.game = CONTROLLER.server.game
            CONTROLLER.game.players[0].name = context.scene.remi2d_player_name
            CONTROLLER.feedback_banner = msg
            rebuild_2d_board_objects()
        elif act == "JOIN_SERVER":
            if CONTROLLER.client is None:
                CONTROLLER.client = RemiTCPClient()
            ok, msg = CONTROLLER.client.connect(
                host=context.scene.remi2d_host,
                port=context.scene.remi2d_port,
                player_name=context.scene.remi2d_player_name,
            )
            if ok:
                CONTROLLER.mode = "CLIENT"
            CONTROLLER.feedback_banner = msg
            rebuild_2d_board_objects()
        elif act == "OFFLINE_MODE":
            if CONTROLLER.client:
                CONTROLLER.client.disconnect()
            if CONTROLLER.server:
                CONTROLLER.server.stop()
            CONTROLLER.mode = "OFFLINE"
            CONTROLLER.my_seat = 0
            CONTROLLER.feedback_banner = "Mode Offline (1 Pemain vs 3 AI Bot) aktif."
            rebuild_2d_board_objects()
        elif act == "APPLY_SETTINGS_START":
            scn = context.scene
            CONTROLLER.game.configure_match(
                num_players=int(scn.remi2d_num_players),
                turn_timer_sec=int(scn.remi2d_turn_timer),
                target_score=int(scn.remi2d_target_score),
                player_name=scn.remi2d_player_name,
            )
            CONTROLLER.game.reset_match()
            CONTROLLER.start_round()
            timer_txt = f"{scn.remi2d_turn_timer}s" if int(scn.remi2d_turn_timer) > 0 else "Unlimited"
            CONTROLLER.feedback_banner = (
                f"Permainan Dimulai! {scn.remi2d_num_players} Pemain | "
                f"Waktu: {timer_txt} | Target: {scn.remi2d_target_score} Poin."
            )
            rebuild_2d_board_objects()
        elif act == "OPEN_WEB_DASHBOARD":
            import webbrowser
            webbrowser.open("http://localhost:8080")
        return {"FINISHED"}


# ==============================================================================
# PANEL SIDEBAR N-PANEL DI BLENDER 3D VIEWPORT ("Remi 2D")
# ==============================================================================
class REMI2D_PT_MainPanel(bpy.types.Panel):
    bl_label = "Remi Nusantara 2D (1500 Poin)"
    bl_idname = "REMI2D_PT_MainPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Remi 2D"

    def draw(self, context):
        layout = self.layout
        st = CONTROLLER.get_active_state()

        box_top = layout.box()
        box_top.label(text="Kontrol Permainan 2D:", icon="PLAY")
        if not CONTROLLER.modal_running:
            box_top.operator("remi2d.start_modal_game", text="Aktifkan Klik Langsung 2D", icon="RESTRICT_SELECT_OFF")
        else:
            box_top.label(text="Mode Klik 2D Aktif (ESC untuk Stop)", icon="CHECKMARK")

        row = box_top.row(align=True)
        op = row.operator("remi2d.quick_action", text="Mulai / Ronde Baru", icon="FILE_REFRESH")
        op.action = "START_ROUND"
        op2 = row.operator("remi2d.quick_action", text="Jalankan Bot", icon="AUTO")
        op2.action = "BOT_STEP"

        box_score = layout.box()
        cur_p_name = st["players"][st["current_turn_seat"]]["name"]
        box_score.label(text=f"GILIRAN: {cur_p_name.upper()}", icon="TIME")
        box_score.label(text=f"4 Wild Card: JOKER & Angka '{st.get('wildcard_rank', '-')}'", icon="SOLO_ON")
        for p in st["players"]:
            turn_ic = "LAYER_ACTIVE" if p["seat"] == st["current_turn_seat"] else "LAYER_USED"
            box_score.label(
                text=f"{p['name']}: {p['total_score']} pts ({p['last_round_score']:+d}) | {p['hand_count']} kartu",
                icon=turn_ic,
            )

        box_act = layout.box()
        box_act.label(text="Aksi Giliran Anda:", icon="HAND")
        r1 = box_act.row(align=True)
        op_draw = r1.operator("remi2d.quick_action", text=f"Ambil Pak ({st['draw_pile_count']})", icon="IMPORT")
        op_draw.action = "DRAW_DECK"
        op_auto = r1.operator("remi2d.quick_action", text="Auto Turun Jadi (A)", icon="CHECKMARK")
        op_auto.action = "AUTO_MELD"

        r2 = box_act.row(align=True)
        op_meld = r2.operator("remi2d.quick_action", text="Turunkan Pilihan (M)", icon="TRIA_DOWN")
        op_meld.action = "MELD_SELECTED"
        op_disc = r2.operator("remi2d.quick_action", text="Buang / Tutup +250 (B)", icon="EXPORT")
        op_disc.action = "DISCARD"

        r3 = box_act.row(align=True)
        op_sr = r3.operator("remi2d.quick_action", text="Urut Angka")
        op_sr.action = "SORT_RANK"
        op_ss = r3.operator("remi2d.quick_action", text="Urut Kembang")
        op_ss.action = "SORT_SUIT"

        box_disc = layout.box()
        disc_pile = st["discard_pile"]
        box_disc.label(text="Buangan (Maks Ambil 7 Kartu Teratas):", icon="RECOVER_LAST")
        if not disc_pile:
            box_disc.label(text="Belum ada kartu buangan.")
        else:
            total_d = len(disc_pile)
            highest_w = -1
            for i in range(total_d - 1, -1, -1):
                if disc_pile[i].get("is_wild", False):
                    if i > highest_w:
                        highest_w = i
            grid = box_disc.grid_flow(row_major=True, columns=4, even_columns=True)
            for idx in range(total_d - 1, max(-1, total_d - 8), -1):
                depth = total_d - idx
                c = disc_pile[idx]
                has_w = (highest_w != -1 and idx <= highest_w)
                if depth <= MAX_DISCARD_TAKE_DEPTH and not has_w:
                    op_tk = grid.operator("remi2d.quick_action", text=f"#{depth} {c['id']}")
                    op_tk.action = "TAKE_DISCARD"
                    op_tk.payload = str(idx)

        box_hand = layout.box()
        my_p = st["players"][CONTROLLER.my_seat]
        box_hand.label(text=f"Kartu di Tangan Anda ({len(my_p['hand'])}):", icon="VIEW_PAN")
        h_grid = box_hand.grid_flow(row_major=True, columns=4, even_columns=True)
        for c in my_p["hand"]:
            cid = c["id"]
            sel_mark = "* " if cid in CONTROLLER.selected_card_ids else ""
            op_c = h_grid.operator(
                "remi2d.quick_action",
                text=f"{sel_mark}{cid}",
                depress=(cid in CONTROLLER.selected_card_ids),
            )
            op_c.action = "TOGGLE_CARD"
            op_c.payload = cid


class REMI2D_PT_LobbyPanel(bpy.types.Panel):
    bl_label = "Dashboard & Pengaturan Meja"
    bl_idname = "REMI2D_PT_LobbyPanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Remi 2D"

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        box_cfg = layout.box()
        box_cfg.label(text="Pengaturan Permainan:", icon="PREFERENCES")
        box_cfg.prop(scn, "remi2d_turn_timer", text="Waktu Jalan")
        box_cfg.prop(scn, "remi2d_target_score", text="Target Skor")
        box_cfg.prop(scn, "remi2d_num_players", text="Jml Pemain")
        box_cfg.prop(scn, "remi2d_player_name", text="Nama Anda")

        op_start = box_cfg.operator("remi2d.quick_action", text="🎮 Terapkan & Mulai Permainan", icon="PLAY")
        op_start.action = "APPLY_SETTINGS_START"

        op_web = layout.operator("remi2d.quick_action", text="🌐 Buka Dashboard Web (Browser)", icon="URL")
        op_web.action = "OPEN_WEB_DASHBOARD"

        box_net = layout.box()
        box_net.label(text="Multiplayer LAN / Online:", icon="WORLD")
        box_net.label(text=f"Mode: {CONTROLLER.mode} (Kursi #{CONTROLLER.my_seat + 1})")
        box_net.prop(scn, "remi2d_room_code", text="Kode Room")
        box_net.prop(scn, "remi2d_host", text="IP Host")
        box_net.prop(scn, "remi2d_port", text="Port")

        row = box_net.row(align=True)
        op_h = row.operator("remi2d.quick_action", text="Buat Room", icon="OUTLINER_OB_LIGHT")
        op_h.action = "HOST_SERVER"
        op_j = row.operator("remi2d.quick_action", text="Gabung", icon="LINKED")
        op_j.action = "JOIN_SERVER"

        op_off = box_net.operator("remi2d.quick_action", text="Main Offline vs AI", icon="USER")
        op_off.action = "OFFLINE_MODE"


CLASSES = (
    REMI2D_OT_StartModalGame,
    REMI2D_OT_QuickAction,
    REMI2D_PT_MainPanel,
    REMI2D_PT_LobbyPanel,
)


def _auto_start_modal_on_gui_launch():
    if bpy.app.background or CONTROLLER.modal_running:
        return None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with bpy.context.temp_override(window=window, area=area, region=region):
                            bpy.ops.remi2d.start_modal_game("INVOKE_DEFAULT")
                        return None
    return 0.25


def register():
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    bpy.types.Scene.remi2d_player_name = bpy.props.StringProperty(name="Nama Pemain", default="Anda (Player 1)")
    bpy.types.Scene.remi2d_turn_timer = bpy.props.EnumProperty(
        name="Waktu Jalan",
        description="Batas waktu giliran per langkah",
        items=[
            ("15", "⚡ 15s (Blitz / Cepat)", "Waktu cepat 15 detik"),
            ("25", "⏱ 25s (Standar)", "Standar turnamen Remi Nusantara"),
            ("40", "☕ 40s (Santai)", "Waktu santai 40 detik"),
            ("60", "⏳ 60s (Panjang)", "Waktu panjang 60 detik"),
            ("0", "♾️ Bebas (Unlimited)", "Bebas tanpa batas waktu"),
        ],
        default="25",
    )
    bpy.types.Scene.remi2d_target_score = bpy.props.EnumProperty(
        name="Target Skor",
        description="Target akumulasi poin kemenangan",
        items=[
            ("500", "500 Poin (Singkat)", "Match singkat"),
            ("1000", "1.000 Poin (Sedang)", "Match menengah"),
            ("1500", "1.500 Poin (Standar)", "Standar Nusantara"),
        ],
        default="1500",
    )
    bpy.types.Scene.remi2d_num_players = bpy.props.EnumProperty(
        name="Jumlah Pemain",
        description="Jumlah kursi di meja",
        items=[
            ("2", "2 Pemain (Duel 1v1)", "1 vs 1"),
            ("3", "3 Pemain", "Segitiga"),
            ("4", "4 Pemain (Lengkap)", "Meja penuh 4 kursi"),
        ],
        default="4",
    )
    bpy.types.Scene.remi2d_room_code = bpy.props.StringProperty(name="Kode Room", default="RM1500")
    bpy.types.Scene.remi2d_host = bpy.props.StringProperty(name="Server IP", default="127.0.0.1")
    bpy.types.Scene.remi2d_port = bpy.props.IntProperty(name="Port", default=55535, min=1024, max=65535)


def unregister():
    if CONTROLLER.draw_handler is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(CONTROLLER.draw_handler, "WINDOW")
        except Exception:
            pass
        CONTROLLER.draw_handler = None
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
    setup_static_2d_table()
    CONTROLLER.start_round()
    apply_clean_2d_viewport_settings()
    if not bpy.app.background:
        bpy.app.timers.register(_auto_start_modal_on_gui_launch, first_interval=0.3)
