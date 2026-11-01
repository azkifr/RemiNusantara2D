"""
Script Builder untuk menghasilkan file `RemiNusantara2D.blend` dan merender preview 2D (v2.4):
- Menampilkan Kartu Bukaan Pertama (`BUKAAN WILD`) di samping Pak Kartu yang menentukan 3 Wild Card tambahan (+ 1 Joker = 4 Wild Card).
- Menampilkan indikator wajib Kartu Urut (`SERI WAJIB: AMAN` vs `AWAS TERBAKAR!`).
- Mengembalikan tombol `AUTO TURUN (A)` serta perilaku klik kartu buangan langsung otomatis turun.
"""

import os
import sys
import bpy

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import blender_remi_2d
from remi_engine import Card


def build_2d_blend_file():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    blender_remi_2d.register()
    blender_remi_2d.setup_static_2d_table()
    game = blender_remi_2d.CONTROLLER.game
    game.start_new_round(seed=2026)

    # Set contoh Kartu Bukaan Pertama = 6 Hati (sehingga 6S, 6D, 6C + JOKER = 4 Wild Card!)
    game.wildcard_indicator_card = Card.from_id("6H")
    game.wildcard_rank = "6"

    # Buat contoh 8 kartu di tumpukan buangan (7 aktif, 1 locked)
    game.discard_pile = [
        Card.from_id("2C"),
        Card.from_id("4D"),
        Card.from_id("5S"),
        Card.from_id("8H"),
        Card.from_id("10C"),
        Card.from_id("JS"),
        Card.from_id("KD"),
        Card.from_id("AH"),
    ]

    # Simulasi Kartu Jadi di meja (termasuk penggunaan Wild Card '6S' dan 'JOKER')
    game.players[0].melds = [
        [Card.from_id("7S"), Card.from_id("8S"), Card.from_id("9S")],  # Seri Wajib (Aman dari Terbakar!)
        [Card.from_id("JC"), Card.from_id("QC"), Card.from_id("6S")],  # Seri Face dengan Wildcard 6S
    ]
    game.players[1].melds = [
        [Card.from_id("AS"), Card.from_id("AH"), Card.from_id("AD")],  # Hanya Tris (Belum ada Seri -> Awas Terbakar!)
    ]
    game.players[2].melds = [
        [Card.from_id("8D"), Card.from_id("9D"), Card.from_id("10D")],
        [Card.from_id("JH"), Card.from_id("QH"), Card.from_id("KH")],
    ]
    game.players[3].melds = [
        [Card.from_id("2S"), Card.from_id("3S"), Card.from_id("JOKER")],
    ]

    game.players[0].hand = [
        Card.from_id("3H"),
        Card.from_id("4H"),
        Card.from_id("6D"),  # Wildcard dari bukaan 6H!
        Card.from_id("JOKER"),
        Card.from_id("AS"),
        Card.from_id("AD"),
        Card.from_id("KC"),
    ]
    game.phase = "TURN_MELD_DISCARD"
    blender_remi_2d.CONTROLLER.selected_card_ids = {"3H", "4H", "6D"}
    blender_remi_2d.CONTROLLER.feedback_banner = (
        "Bukaan Wild: 6-Hati -> 4 Wild Card = JOKER + Tiga Kartu '6'! Wajib punya min 1 Seri (>=3 kartu) agar tidak TERBAKAR!"
    )
    blender_remi_2d.rebuild_2d_board_objects()

    script_path = os.path.join(SRC_DIR, "blender_remi_2d.py")
    with open(script_path, "r", encoding="utf-8") as f:
        code_text = f.read()

    txt_block = bpy.data.texts.get("remi_2d_autorun.py")
    if txt_block is None:
        txt_block = bpy.data.texts.new("remi_2d_autorun.py")
    txt_block.clear()
    txt_block.write(code_text)
    txt_block.use_module = True

    scn = bpy.context.scene
    scn.render.resolution_x = 1600
    scn.render.resolution_y = 1000
    scn.render.resolution_percentage = 100
    scn.render.engine = "BLENDER_WORKBENCH"
    scn.display.shading.light = "FLAT"
    scn.display.shading.color_type = "OBJECT"
    scn.view_settings.view_transform = "Standard"

    blender_remi_2d.apply_clean_2d_viewport_settings()

    preview_out = os.path.join(PROJECT_ROOT, "preview_remi_2d.png")
    scn.render.filepath = preview_out
    bpy.ops.render.render(write_still=True)
    print(f"[SUCCESS] Preview 2D berhasil dirender ke: {preview_out}")

    # Setelah render preview, reset ke awal Ronde 1 yang siap langsung dimainkan
    game.start_new_round(seed=2026)
    blender_remi_2d.CONTROLLER.selected_card_ids.clear()
    w_card = game.wildcard_indicator_card
    blender_remi_2d.CONTROLLER.feedback_banner = (
        f"Ronde 1 dimulai! Bukaan Wild: {w_card.label} (4 Wild Card = JOKER + 3 kartu '{w_card.rank}'). Wajib >=1 Seri min 3!"
    )
    blender_remi_2d.rebuild_2d_board_objects()

    blend_out = os.path.join(PROJECT_ROOT, "RemiNusantara2D.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_out)
    print(f"[SUCCESS] File Blender 2D tersimpan di: {blend_out}")


if __name__ == "__main__":
    build_2d_blend_file()
