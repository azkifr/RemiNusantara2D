"""Web Game Server for Remi Nusantara 2D Online (Local Browser Edition).
Royale Theme with Responsive Non-Overlapping Layout.
"""

from __future__ import annotations
import http.server
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json
import gzip
import os
import sys
import threading
import time
import socket
import webbrowser

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from remi_engine import RemiGameMatch, validate_meld, Card

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

GAME_LOCK = threading.Lock()
GAME = RemiGameMatch(room_code="RM1500", num_players=4, turn_timer_sec=0)
for p in GAME.players:
    p.player_id = ""
# Server dimulai dalam fase LOBBY agar pemain dapat berkumpul, memilih kursi, dan mengatur nama
_LAST_TICK_TIME = time.time()
_BOT_ACCUM = 0.0


def tick_game_state_locked():
    """Majukan timer giliran & langkah Bot berdasarkan selisih waktu nyata (mendukung Serverless Vercel maupun Thread lokal)."""
    global _LAST_TICK_TIME, _BOT_ACCUM
    now = time.time()
    dt = min(1.5, max(0.0, now - _LAST_TICK_TIME))
    _LAST_TICK_TIME = now
    if dt <= 0.0:
        return

    # Auto ganti pemain yang keluar / terputus (>25 detik tidak aktif) menjadi Bot di semua fase
    for idx, p in enumerate(GAME.players):
        if not p.is_bot and getattr(p, "player_id", ""):
            if (now - getattr(p, "last_seen", now)) > 25.0:
                p.is_bot = True
                p.auto_pilot = True
                p.player_id = ""
                p.connected = True
                bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                p.name = bot_names[idx % len(bot_names)]
                if GAME.phase == "LOBBY":
                    GAME.status_message = f"Kursi {idx + 1} dibuka kembali karena pemain terputus."
                else:
                    GAME.status_message = f"Pemain di Kursi {idx + 1} terputus dan otomatis digantikan oleh {p.name}."

    if getattr(GAME, "is_paused", False) or GAME.phase == "LOBBY":
        return
    if GAME.phase in ("TURN_DRAW", "TURN_MELD_DISCARD"):
        cur_p = GAME.players[GAME.current_turn_seat]
        if cur_p.is_bot or cur_p.auto_pilot:
            _BOT_ACCUM += dt
            delay = getattr(GAME, "bot_delay_sec", 1.0)
            if _BOT_ACCUM >= delay:
                _BOT_ACCUM = 0.0
                GAME.execute_bot_or_timeout_step()
        else:
            _BOT_ACCUM = 0.0
            if GAME.turn_timer_sec > 0:
                GAME.turn_remaining_sec = max(0.0, GAME.turn_remaining_sec - dt)
                if GAME.turn_remaining_sec <= 0.0:
                    GAME.execute_bot_or_timeout_step()
    elif GAME.phase == "ROUND_OVER":
        _BOT_ACCUM = 0.0
        if hasattr(GAME, "round_over_timer") and GAME.round_over_timer is not None:
            GAME.round_over_timer = max(0.0, GAME.round_over_timer - dt)
            if GAME.round_over_timer <= 0.0:
                GAME.start_new_round()


def _bot_background_worker():
    while True:
        time.sleep(0.15)
        try:
            with GAME_LOCK:
                if GAME.phase != "LOBBY":
                    tick_game_state_locked()
        except Exception as exc:
            print(f"[WARN] Background worker error: {exc}")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<title>Remi Nusantara 2D Online - Royale Edition</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  :root {
    --felt-center: #1a633c;
    --felt-mid: #0f4428;
    --felt-dark: #062314;
    --wood-rail: #231309;
    --gold: #facc15;
    --gold-glow: rgba(250, 204, 21, 0.45);
    /* Large, High-Legibility Card Dimensions */
    --hand-card-w: clamp(62px, 5.2vw, 82px);
    --hand-card-h: clamp(90px, 7.5vw, 118px);
    --disc-card-w: clamp(48px, 4.2vw, 60px);
    --disc-card-h: clamp(70px, 6.0vw, 88px);
    --meld-card-w: clamp(34px, 2.8vw, 44px);
    --meld-card-h: clamp(50px, 4.2vw, 64px);
  }

  * { box-sizing: border-box; user-select: none; margin: 0; padding: 0; }
  html, body {
    width: 100%;
    height: 100vh;
    margin: 0;
    padding: 0;
    background: #080402;
    color: #f8fafc;
    font-family: 'Outfit', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* MEJA PERMAINAN ROYALE - 2 ATAS 2 BAWAH ARCHITECTURE (OPTIMAL SPACE DISTRIBUTION) */
  #table {
    flex: 1;
    margin: 2px 6px;
    border: 7px solid var(--wood-rail);
    border-radius: 20px;
    box-shadow: inset 0 0 70px rgba(0,0,0,0.92), 0 10px 30px rgba(0,0,0,0.95);
    outline: 1.5px solid rgba(250, 204, 21, 0.3);
    outline-offset: -4px;
    background: radial-gradient(ellipse at 50% 46%, var(--felt-center) 0%, var(--felt-mid) 50%, var(--felt-dark) 100%);
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    gap: 4px;
    padding: 6px 14px 6px 14px;
    position: relative;
    height: calc(100vh - 8px);
    max-height: calc(100vh - 8px);
    box-sizing: border-box;
    overflow: hidden;
  }

  /* TOP HEADER HUD */
  .header-bar {
    display: flex;
    flex-direction: column;
    gap: 3px;
    background: rgba(4, 22, 14, 0.92);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 4px 12px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    flex-shrink: 0;
  }
  .header-top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }
  .header-brand {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .brand-logo { font-size: 16px; }
  .header-title {
    color: #facc15;
    font-weight: 800;
    font-size: 13px;
    letter-spacing: 0.3px;
    font-variant-numeric: tabular-nums;
  }
  .header-btn-group {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .header-dash-btn {
    background: rgba(255,255,255,0.08);
    color: #f8fafc;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 800;
    cursor: pointer;
    transition: all 0.14s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: inherit;
  }
  .header-dash-btn:hover {
    background: rgba(255,255,255,0.18);
    border-color: rgba(255,255,255,0.35);
    transform: translateY(-1px);
  }

  /* TURN BANNER & STATUS */
  .turn-banner {
    padding: 3px 12px;
    border-radius: 8px;
    font-weight: 800;
    font-size: 11.5px;
    color: #fff;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    text-align: center;
    width: 100%;
    transition: all 0.2s ease;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .turn-my {
    background: linear-gradient(90deg, rgba(21, 128, 61, 0.5) 0%, #15803d 50%, rgba(21, 128, 61, 0.5) 100%);
    border: 1px solid #4ade80;
    box-shadow: 0 0 14px rgba(74, 222, 128, 0.35);
  }
  .turn-opp {
    background: linear-gradient(90deg, rgba(194, 65, 12, 0.5) 0%, #c2410c 50%, rgba(194, 65, 12, 0.5) 100%);
    border: 1px solid #fb923c;
  }
  .status-notif {
    font-size: 11px;
    color: #cbd5e1;
    text-align: center;
    font-weight: 600;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ZONES & PLAYER PODS */
  .zone-box {
    background: rgba(4, 24, 15, 0.78);
    border: 1.5px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    box-shadow: inset 0 2px 8px rgba(0,0,0,0.4);
    position: relative;
    padding: 5px 8px;
    overflow: visible;
  }
  .zone-active {
    border-color: #facc15;
    box-shadow: 0 0 16px rgba(250, 204, 21, 0.35), inset 0 0 10px rgba(250, 204, 21, 0.15);
  }

  /* ======================================================== */
  /* ROYALE ANNOTATED WIREFRAME LAYOUT: LEFT ARENA vs RIGHT OPPONENTS */
  /* ======================================================== */

  .table-main-split {
    display: grid;
    grid-template-columns: minmax(440px, 1.22fr) minmax(360px, 1fr);
    gap: 10px;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    box-sizing: border-box;
    overflow: hidden;
  }

  /* LEFT COLUMN: ARENA (ACTIVE DISCARD, BURIED DISCARD, DECK & WILD) */
  #arena-col {
    display: flex;
    flex-direction: column;
    gap: 7px;
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }

  .arena-bar {
    background: linear-gradient(135deg, rgba(3, 24, 14, 0.94) 0%, rgba(2, 16, 9, 0.98) 100%);
    backdrop-filter: blur(14px);
    border: 1.5px solid rgba(250, 204, 21, 0.35);
    border-radius: 12px;
    padding: 5px 10px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: inset 0 2px 10px rgba(0,0,0,0.55), 0 4px 12px rgba(0,0,0,0.3);
    position: relative;
    overflow: hidden;
    box-sizing: border-box;
  }
  .arena-bar-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding-bottom: 2px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  }
  .bar-hdr-icon { font-size: 13px; }
  .bar-hdr-title {
    font-size: 10px;
    font-weight: 800;
    color: #fde047;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }
  .arena-pill {
    font-size: 9px;
    font-weight: 800;
    color: #94a3b8;
    background: rgba(255, 255, 255, 0.08);
    padding: 1px 6px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.12);
  }

  /* ROW 1: 7 KARTU BUANGAN (AKTIF) */
  #disc-active-bar {
    flex: 1.25 1 0;
    min-height: clamp(82px, 14vh, 106px);
  }
  .disc-active-grid {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
    gap: 6px;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    padding: 3px 0;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
    scrollbar-color: rgba(250, 204, 21, 0.45) transparent;
  }
  .disc-active-grid .card {
    width: var(--disc-card-w);
    height: var(--disc-card-h);
    aspect-ratio: 2.5 / 3.6;
    border-radius: 7px;
    flex-shrink: 0;
    position: relative;
    transition: transform 0.14s ease, box-shadow 0.14s ease;
  }
  .disc-active-grid .card.active-discard {
    border: 2px solid #facc15 !important;
    box-shadow: 0 0 12px rgba(250, 204, 21, 0.5), 0 4px 10px rgba(0,0,0,0.5);
    animation: active-disc-glow 2s infinite alternate ease-in-out;
    cursor: grab;
  }
  .disc-active-grid .card.active-discard:active { cursor: grabbing; }
  .disc-active-grid .card.active-discard:hover {
    transform: translateY(-6px) scale(1.06);
    z-index: 25;
    box-shadow: 0 10px 22px rgba(0,0,0,0.85), 0 0 20px rgba(250, 204, 21, 0.85);
  }
  @keyframes active-disc-glow {
    0% { box-shadow: 0 0 8px rgba(250, 204, 21, 0.35); }
    100% { box-shadow: 0 0 20px rgba(250, 204, 21, 0.8); }
  }
  .disc-active-grid .c-badge-pill {
    position: absolute;
    bottom: 2px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 7.5px;
    padding: 1px 4px;
    background: #facc15;
    color: #0f172a;
    font-weight: 900;
    border: 1px solid #eab308;
    border-radius: 999px;
    white-space: nowrap;
    pointer-events: none;
    z-index: 5;
  }

  /* ROW 2: KARTU BUANGAN LEBIH DARI 7 (TERKUBUR) */
  #disc-buried-bar {
    flex: 0.9 1 0;
    min-height: clamp(52px, 9vh, 68px);
  }
  .disc-buried-scroll {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
    gap: 4px;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    padding: 2px 0;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
    scrollbar-color: rgba(250, 204, 21, 0.3) transparent;
  }
  .disc-buried-scroll .card.buried-grey {
    width: clamp(28px, 2.4vw, 36px) !important;
    height: clamp(40px, 3.4vw, 50px) !important;
    aspect-ratio: 2.5 / 3.6;
    border-radius: 4px !important;
    filter: grayscale(1) opacity(0.42);
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    flex-shrink: 0;
    cursor: default;
    transition: all 0.12s ease;
  }
  .disc-buried-scroll .card.buried-grey:hover {
    filter: grayscale(0.3) opacity(0.85);
    transform: translateY(-2px);
    border-color: rgba(250, 204, 21, 0.45) !important;
    z-index: 10;
  }
  .buried-empty-hint {
    font-size: 9px;
    color: rgba(203, 213, 225, 0.4);
    font-style: italic;
    white-space: nowrap;
  }

  /* ROW 3: PAK KARTU & BUKAAN WILD (SIDE-BY-SIDE) */
  #deck-wild-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    width: 100%;
    flex: 1.1 1 0;
    min-height: clamp(82px, 14vh, 105px);
  }
  #pak-box {
    background: radial-gradient(circle at 40% 30%, #991b1b 0%, #450a0a 100%);
    border: 2px solid #fbbf24;
    border-radius: 12px;
    padding: 4px 8px;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 8px;
    cursor: pointer;
    box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 6px 14px rgba(0,0,0,0.65);
    transition: transform 0.14s ease, box-shadow 0.14s ease;
    user-select: none;
    box-sizing: border-box;
  }
  #pak-box:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 10px 20px rgba(0,0,0,0.75), 0 0 14px rgba(251, 191, 36, 0.4);
  }
  .pak-card-back-visual {
    flex-shrink: 0;
  }
  .pak-mini-deck {
    width: clamp(34px, 3.0vw, 42px) !important;
    height: clamp(48px, 4.2vw, 60px) !important;
    border-radius: 5px !important;
  }
  .pak-info-side {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
  }
  .pak-label {
    font-size: 10px;
    font-weight: 800;
    color: #fef08a;
    letter-spacing: 0.3px;
  }
  .pak-count {
    font-size: 13px;
    font-weight: 900;
    color: #facc15;
  }
  .pak-hint {
    font-size: 8px;
    font-weight: 700;
    color: #cbd5e1;
    opacity: 0.85;
  }

  #wild-box {
    background: radial-gradient(ellipse at center, rgba(88, 28, 135, 0.75) 0%, rgba(38, 10, 60, 0.9) 100%);
    border: 1.5px solid #c084fc;
    border-radius: 12px;
    padding: 4px 8px;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 8px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.5), 0 0 12px rgba(192, 132, 252, 0.3);
    user-select: none;
    box-sizing: border-box;
  }
  .wild-card-holder .card {
    width: clamp(36px, 3.2vw, 44px) !important;
    height: clamp(50px, 4.4vw, 62px) !important;
    border-radius: 5px !important;
    cursor: default;
  }
  .wild-card-holder .card .c-rank { font-size: 12px !important; }
  .wild-card-holder .card .c-suit-mini { font-size: 10px !important; }
  .wild-card-holder .card .c-center { font-size: 24px !important; }
  .wild-info-side {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
  }
  .wild-label {
    font-size: 10px;
    font-weight: 800;
    color: #e9d5ff;
    letter-spacing: 0.3px;
  }
  .wild-sub {
    font-size: 8px;
    font-weight: 700;
    color: #c084fc;
  }

  /* RIGHT COLUMN: 3 OPPONENTS STACKED (JUMLAH KARTU LEFT + KARTU JADI RIGHT) */
  #opponents-col {
    display: flex;
    flex-direction: column;
    gap: 7px;
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }
  .opp-split-pod {
    background: linear-gradient(135deg, rgba(3, 24, 14, 0.88) 0%, rgba(2, 16, 9, 0.94) 100%);
    backdrop-filter: blur(14px);
    border: 1.5px solid rgba(250, 204, 21, 0.22);
    border-radius: 12px;
    padding: 5px 10px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 3px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06);
    flex: 1 1 0;
    min-height: 0;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease;
  }
  .opp-split-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding-bottom: 2px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  }
  .opp-split-body {
    display: grid;
    grid-template-columns: clamp(75px, 8vw, 95px) 1fr;
    gap: 8px;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    align-items: center;
  }
  .opp-count-box {
    background: rgba(0, 0, 0, 0.38);
    border: 1px solid rgba(250, 204, 21, 0.25);
    border-radius: 8px;
    padding: 3px 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 0;
    box-sizing: border-box;
  }
  .opp-hand-count-visual {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .opp-card-back-icon {
    width: 24px !important;
    height: 34px !important;
    border-radius: 4px !important;
    font-size: 8px !important;
    flex-shrink: 0;
  }
  .opp-count-info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    line-height: 1.1;
  }
  .opp-count-num {
    font-size: 14px;
    font-weight: 900;
    color: #facc15;
  }
  .opp-count-txt {
    font-size: 7.5px;
    font-weight: 800;
    color: #94a3b8;
    letter-spacing: 0.3px;
  }
  .opp-melds-box {
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(250, 204, 21, 0.2);
    border-radius: 8px;
    padding: 3px 6px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    height: 100%;
    min-height: 0;
    overflow-x: auto;
    overflow-y: hidden;
    box-sizing: border-box;
  }

  /* BOTTOM: PLAYER STADIUM HERO CONSOLE (ROUNDED STADIUM) */
  .player-stadium-console {
    background: radial-gradient(ellipse at 50% 10%, rgba(4, 28, 17, 0.95) 0%, rgba(2, 16, 10, 0.98) 100%);
    backdrop-filter: blur(16px);
    border: 2px solid rgba(250, 204, 21, 0.45);
    border-radius: 20px;
    padding: 6px 14px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 4px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.08);
    flex: 0 0 clamp(180px, 32vh, 230px);
    width: 100%;
    box-sizing: border-box;
    position: relative;
    overflow: hidden;
    transition: all 0.25s ease;
  }
  #zone-bottom.my-turn-active {
    border-color: #facc15 !important;
    background: radial-gradient(ellipse at 50% 10%, rgba(21, 128, 61, 0.35) 0%, rgba(4, 26, 16, 0.98) 100%) !important;
    box-shadow: 0 0 28px rgba(250, 204, 21, 0.65), 0 4px 24px rgba(0,0,0,0.6), inset 0 0 16px rgba(250, 204, 21, 0.25) !important;
    animation: my-turn-pulse 1.6s infinite alternate ease-in-out;
  }
  .stadium-hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding-bottom: 2px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  }

  /* TOP CENTER BOX: KARTU JADI (MELDS) */
  .player-melds-center-box {
    background: rgba(0, 0, 0, 0.4);
    border: 1.5px solid rgba(250, 204, 21, 0.3);
    border-radius: 9px;
    padding: 2px 8px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: center;
    width: clamp(340px, 60%, 540px);
    margin: 0 auto;
    height: clamp(36px, 6.5vh, 48px);
    flex-shrink: 0;
    box-sizing: border-box;
  }
  .player-melds-hdr {
    font-size: 8px;
    font-weight: 800;
    color: #facc15;
    letter-spacing: 0.3px;
    text-transform: uppercase;
  }
  .player-melds-flow {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 4px;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    overflow-x: auto;
    overflow-y: hidden;
  }

  /* MAIN BOTTOM BOX: KARTU TANGAN (HAND) */
  .player-hand-wide-box {
    background: rgba(0, 0, 0, 0.25);
    border: 1.5px solid rgba(250, 204, 21, 0.35);
    border-radius: 12px;
    padding: 2px 10px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    align-items: center;
    width: 100%;
    flex: 1 1 auto;
    min-height: 0;
    position: relative;
    box-sizing: border-box;
    overflow: visible;
  }
  .player-hand-hdr {
    position: absolute;
    top: 2px;
    left: 10px;
    font-size: 8.5px;
    font-weight: 800;
    color: #38bdf8;
    letter-spacing: 0.3px;
    pointer-events: none;
    z-index: 5;
  }

  #my-hand {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    padding: 10px 4px 2px 4px;
    width: 100%;
    height: 100%;
    position: relative;
    box-sizing: border-box;
    overflow-x: auto;
    overflow-y: visible;
  }
  #my-hand .hand-card-slot {
    width: var(--hand-card-w);
    height: var(--hand-card-h);
    margin-left: calc(var(--hand-card-w) * -0.42);
    position: relative;
    flex-shrink: 0;
    cursor: grab;
    user-select: none;
    transition: z-index 0.15s ease;
  }
  #my-hand .hand-card-slot:active { cursor: grabbing; }
  #my-hand .hand-card-slot:first-child { margin-left: 0 !important; }
  #my-hand .hand-card-slot:hover { z-index: 70; }
  #my-hand .hand-card-slot .card {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 100%;
    margin-left: 0 !important;
    box-shadow: -3px 0 10px rgba(0,0,0,0.45), 0 4px 10px rgba(0,0,0,0.3);
    transition: transform 0.16s ease, box-shadow 0.16s ease;
    pointer-events: none;
    border-radius: 8px;
  }
  #my-hand .hand-card-slot:hover .card {
    transform: translateY(-16px);
    box-shadow: -4px 10px 20px rgba(0,0,0,0.65), 0 0 16px rgba(250, 204, 21, 0.45);
  }
  #my-hand .hand-card-slot.selected-slot .card,
  #my-hand .hand-card-slot .card.selected {
    transform: translateY(-22px) !important;
    border-color: #f59e0b !important;
    box-shadow: 0 0 0 2.5px #f59e0b, 0 12px 24px rgba(245, 158, 11, 0.6) !important;
  }
/* ======================================================== */
  /* PLAYING CARD BASE DESIGN                                 */
  /* ======================================================== */
  .card {
    background: linear-gradient(168deg, #ffffff 0%, #fdfbf7 70%, #f5eee4 100%);
    color: #0f172a;
    border: 1.5px solid #cbd5e1;
    border-radius: 10px;
    position: relative;
    cursor: pointer;
    user-select: none;
    box-shadow: 0 3px 10px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(255,255,255,0.85);
    flex-shrink: 0;
  }
  .card.locked {
    opacity: 0.65;
    cursor: not-allowed;
    filter: grayscale(0.2);
  }
  .card.red {
    color: #e11d48; /* Deep Ruby / Crimson Red for max pop & vibrancy */
  }
  .card.black {
    color: #09090b; /* True Rich Obsidian Black */
  }
  .card.joker {
    background: linear-gradient(168deg, #faf5ff 0%, #f3e8ff 100%);
    border-color: #c084fc;
    color: #7e22ce;
  }

  /* CORNER INDEXES (Top-Left always visible when overlapping!) */
  .c-corner-tl {
    position: absolute;
    top: 5px;
    left: 7px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 0.92;
    pointer-events: none;
  }
  .c-corner-br {
    position: absolute;
    bottom: 5px;
    right: 7px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 0.92;
    transform: rotate(180deg);
    pointer-events: none;
  }
  /* BOLD HIGH-CONTRAST CARD LOGO & RANK */
  .c-rank {
    font-family: 'Outfit', system-ui, -apple-system, sans-serif;
    font-weight: 900;
    font-size: 26px; /* was 18px: +44% much larger & clearer! */
    line-height: 0.92;
    letter-spacing: -0.8px;
  }
  .c-suit-mini {
    font-family: 'Segoe UI Symbol', 'Apple Symbols', 'Outfit', sans-serif;
    font-size: 22px; /* was 14px: +57% clearly visible in hand! */
    font-weight: 900;
    line-height: 0.92;
    margin-top: 2px;
    -webkit-text-stroke: 0.5px currentColor;
  }

  /* PROMINENT CENTER SUIT LOGO (HERO OF THE CARD) */
  .c-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-family: 'Segoe UI Symbol', 'Apple Symbols', 'Outfit', sans-serif;
    font-size: 68px; /* was 40px: +70% giant bold logo! */
    font-weight: 900;
    line-height: 1;
    pointer-events: none;
    -webkit-text-stroke: 0.6px currentColor;
    filter: drop-shadow(0 3px 6px rgba(0,0,0,0.15));
  }

  /* TOP-RIGHT WILD RIBBON */
  .c-wild-ribbon {
    position: absolute;
    top: 5px;
    right: 6px;
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: #fff;
    font-size: 8px;
    font-weight: 900;
    padding: 1px 6px;
    border-radius: 999px;
    letter-spacing: 0.3px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    pointer-events: none;
  }

  /* BOTTOM-LEFT POINT CHIP (Always visible on left 50% when overlapping!) */
  .c-point-pill {
    position: absolute;
    bottom: 5px;
    left: 6px;
    font-size: 9px;
    font-weight: 900;
    padding: 1px 5px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.08);
    border: 1px solid rgba(15, 23, 42, 0.16);
    letter-spacing: 0.2px;
    line-height: 1.1;
    pointer-events: none;
  }
  .card.red .c-point-pill {
    background: rgba(220, 38, 38, 0.08);
    border-color: rgba(220, 38, 38, 0.22);
    color: #dc2626;
  }
  .card.black .c-point-pill {
    background: rgba(15, 23, 42, 0.08);
    border-color: rgba(15, 23, 42, 0.18);
    color: #1e293b;
  }
  .card.joker .c-point-pill {
    background: rgba(147, 51, 234, 0.12);
    border-color: rgba(147, 51, 234, 0.25);
    color: #7e22ce;
  }

  /* ACTION BADGE PILL (Discard Rail) */
  .c-badge-pill {
    position: absolute;
    bottom: 4px;
    left: 50%;
    transform: translateX(-50%);
    background: #facc15;
    color: #0f172a;
    font-size: 8px;
    font-weight: 900;
    padding: 1px 6px;
    border-radius: 999px;
    letter-spacing: 0.2px;
    white-space: nowrap;
    pointer-events: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  }

  /* ======================================================== */
  /* PLAYER HAND: 50% OVERLAPPING FAN WITH DRAGGABLE STATIC SLOTS */
  /* Eliminates 100% of hover vibration & supports HTML5 drag-n-drop */
  /* ======================================================== */
  #my-hand {
    display: flex;
    justify-content: flex-start;
    align-items: flex-end;
    padding: 12px 4px 2px 4px;
    width: 100%;
    height: 100%;
    position: relative;
    box-sizing: border-box;
    overflow-x: auto;
    overflow-y: visible;
  }
  #my-hand .hand-card-slot {
    width: var(--hand-card-w);
    height: var(--hand-card-h);
    margin-left: calc(var(--hand-card-w) * -0.42);
    position: relative;
    flex-shrink: 0;
    cursor: grab;
    user-select: none;
    transition: z-index 0.15s ease;
  }
  #my-hand .hand-card-slot:active {
    cursor: grabbing;
  }
  #my-hand .hand-card-slot:first-child {
    margin-left: 0 !important;
  }
  #my-hand .hand-card-slot:hover {
    z-index: 70;
  }
  #my-hand .hand-card-slot .card {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 100%;
    margin-left: 0 !important;
    box-shadow: -3px 0 10px rgba(0,0,0,0.45), 0 4px 10px rgba(0,0,0,0.3);
    transition: transform 0.16s ease, box-shadow 0.16s ease;
    pointer-events: none;
    border-radius: 8px;
  }
  #my-hand .hand-card-slot:hover .card {
    transform: translateY(-16px);
    box-shadow: -4px 10px 20px rgba(0,0,0,0.65), 0 0 16px rgba(250, 204, 21, 0.45);
  }
  #my-hand .hand-card-slot.selected-slot .card,
  #my-hand .hand-card-slot .card.selected {
    transform: translateY(-22px) !important;
    border-color: #f59e0b !important;
    box-shadow: 0 0 0 2.5px #f59e0b, 0 12px 24px rgba(245, 158, 11, 0.6) !important;
  }
  #my-hand .hand-card-slot.selected-slot {
    z-index: 90 !important;
  }
  #my-hand .hand-card-slot.drop-target-slot {
    transform: scale(1.08) translateY(-14px);
    z-index: 85 !important;
    filter: drop-shadow(0 0 12px #38bdf8);
  }
  #my-hand .hand-card-slot.drop-target-slot .card {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 3px #38bdf8, 0 14px 26px rgba(56, 189, 248, 0.6) !important;
  }
  #my-hand .hand-card-slot.dragging-slot {
    opacity: 0.35;
    transform: scale(0.92);
  }
  /* CARD DEALING ANIMATION */
  @keyframes dealCardAnim {
    0% {
      opacity: 0;
      transform: translateY(-220px) scale(0.35) rotate(12deg);
    }
    65% {
      opacity: 1;
      transform: translateY(10px) scale(1.04) rotate(-2deg);
    }
    100% {
      opacity: 1;
      transform: translateY(0) scale(1) rotate(0deg);
    }
  }
  .hand-card-slot.deal-anim {
    animation: dealCardAnim 0.5s cubic-bezier(0.2, 0.85, 0.3, 1) both;
  }
  .slot-slide-ctrls {
    position: absolute;
    top: -24px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 3px;
    z-index: 100;
    pointer-events: auto;
  }
  .slot-arrow-btn {
    background: #f59e0b;
    color: #0f172a;
    border: 1px solid #fef08a;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 900;
    width: 24px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
    transition: transform 0.1s, background 0.1s;
    padding: 0;
    line-height: 1;
  }
  .slot-arrow-btn:hover {
    background: #facc15;
    transform: scale(1.15);
  }
  .slot-arrow-btn:active {
    transform: scale(0.95);
  }
  .btn-action.btn-slide {
    background: linear-gradient(180deg, #0284c7 0%, #0369a1 100%);
    border-color: #38bdf8;
    color: #f0f9ff;
  }
  .btn-action.btn-slide:hover {
    background: linear-gradient(180deg, #0ea5e9 0%, #0284c7 100%);
    border-color: #7dd3fc;
    box-shadow: 0 0 12px rgba(56, 189, 248, 0.5);
  }

  /* ======================================================== */
  /* PROMINENT MELD CARDS (KARTU JADI DI MEJA)                */
  /* ======================================================== */
  .card.small {
    width: var(--meld-card-w);
    height: var(--meld-card-h);
    border-radius: 7px;
    padding: 0;
    box-shadow: 0 2px 7px rgba(0,0,0,0.35);
  }
  .card.small:hover { transform: none; }
  .card.small .c-mini-top {
    position: absolute;
    top: 3px;
    left: 5px;
    right: 5px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 16px; /* was 13px */
    line-height: 1;
  }
  .card.small .c-mini-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-family: 'Segoe UI Symbol', 'Apple Symbols', 'Outfit', sans-serif;
    font-size: 34px; /* was 22px: +54% bigger meld logo! */
    font-weight: 900;
    line-height: 1;
    -webkit-text-stroke: 0.4px currentColor;
  }
  .card.small .c-mini-bot {
    position: absolute;
    bottom: 2px;
    left: 3px;
    right: 3px;
    font-size: 8.5px;
    font-weight: 800;
    text-align: center;
    background: rgba(0,0,0,0.08);
    border-radius: 3px;
    padding: 0.5px 0;
  }

  /* ACTION DOCK (ALWAYS 100% VISIBLE AT BOTTOM!) */
  #action-bar {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: rgba(4, 20, 12, 0.96);
    backdrop-filter: blur(14px);
    border: 1.5px solid rgba(250, 204, 21, 0.45);
    border-radius: 999px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.85), inset 0 1px 0 rgba(255,255,255,0.15);
    min-height: 44px;
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    flex-shrink: 0;
    z-index: 100;
    position: relative;
    scrollbar-width: thin;
    scrollbar-color: rgba(250, 204, 21, 0.5) transparent;
  }
  @media (max-width: 1200px) {
    #action-bar {
      justify-content: flex-start;
      border-radius: 12px;
      padding: 4px 8px;
    }
    .btn-action {
      height: 30px;
      padding: 0 9px;
      font-size: 10.5px;
    }
  }
  .btn-action {
    height: 32px;
    padding: 0 11px;
    font-size: 11px;
    font-weight: 800;
    border-radius: 999px;
    border: 1px solid transparent;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    font-family: inherit;
    transition: all 0.14s ease;
    white-space: nowrap;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
    flex-shrink: 0;
  }
  .btn-action:hover {
    transform: translateY(-2px);
    filter: brightness(1.1);
  }
  .btn-action:active {
    transform: translateY(1px);
    filter: brightness(0.95);
  }

  .btn-draw {
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    color: #fff;
    border-color: #38bdf8;
    box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
  }
  .btn-meld {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: #fff;
    border-color: #34d399;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.4);
  }
  .btn-auto {
    background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
    color: #fff;
    border-color: #4ade80;
    box-shadow: 0 2px 8px rgba(22, 163, 74, 0.4);
  }
  .btn-discard {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: #fff;
    border-color: #f87171;
    box-shadow: 0 2px 8px rgba(239, 68, 68, 0.4);
  }
  .btn-tutup {
    background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
    color: #fde047;
    border-color: #c084fc;
    box-shadow: 0 2px 8px rgba(124, 58, 237, 0.4);
  }
  .glow-tutup {
    background: linear-gradient(135deg, #d97706 0%, #b45309 100%) !important;
    border-color: #fbbf24 !important;
    animation: tutup-glow 1.2s infinite alternate ease-in-out !important;
  }
  @keyframes tutup-glow {
    0% { box-shadow: 0 0 6px #f59e0b; transform: scale(0.98); }
    100% { box-shadow: 0 0 20px #fde047, 0 0 35px #f59e0b; transform: scale(1.04); }
  }
  .btn-ceki {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: #fff;
    border-color: #fde047;
    font-weight: 800;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.45);
    transition: all 0.2s ease;
  }
  .btn-ceki:hover:not(:disabled) {
    background: linear-gradient(135deg, #fbbf24 0%, #ea580c 100%);
    box-shadow: 0 0 14px rgba(251, 191, 36, 0.7);
    transform: translateY(-2px);
  }
  .btn-ceki:disabled, .btn-ceki.btn-cooldown {
    opacity: 0.55;
    cursor: not-allowed;
    filter: grayscale(0.5);
    transform: none !important;
  }
  .ceki-bubble {
    position: absolute;
    top: -42px;
    left: 50%;
    transform: translateX(-50%) scale(0);
    background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
    color: #ffffff;
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 20px;
    letter-spacing: 2px;
    padding: 6px 20px;
    border-radius: 25px;
    box-shadow: 0 4px 18px rgba(239, 68, 68, 0.75), 0 0 14px rgba(245, 158, 11, 0.9);
    border: 2px solid #ffffff;
    z-index: 10000;
    pointer-events: none;
    white-space: nowrap;
    animation: cekiPopAnim 2.2s ease-out forwards;
  }
  .ceki-bubble::after {
    content: '';
    position: absolute;
    bottom: -9px;
    left: 50%;
    transform: translateX(-50%);
    border-width: 9px 9px 0;
    border-style: solid;
    border-color: #ef4444 transparent;
    display: block;
    width: 0;
  }
  @keyframes cekiPopAnim {
    0% { transform: translateX(-50%) scale(0.3); opacity: 0; }
    15% { transform: translateX(-50%) scale(1.25); opacity: 1; }
    25% { transform: translateX(-50%) scale(1.0); }
    75% { transform: translateX(-50%) scale(1.0); opacity: 1; }
    100% { transform: translateX(-50%) scale(0.7) translateY(-14px); opacity: 0; }
  }
  .btn-sort {
    background: rgba(255, 255, 255, 0.08);
    color: #cbd5e1;
    border-color: rgba(255, 255, 255, 0.18);
  }
  .btn-sort:hover {
    background: rgba(255, 255, 255, 0.16);
    color: #fff;
    border-color: rgba(255, 255, 255, 0.35);
  }

  .badge-ceki-glow {
    display: inline-block;
    background: linear-gradient(135deg, #ef4444 0%, #f59e0b 100%);
    color: #ffffff;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1px;
    padding: 2px 8px;
    border-radius: 12px;
    border: 1px solid #fde047;
    box-shadow: 0 0 10px rgba(239, 68, 68, 0.8), 0 0 16px rgba(245, 158, 11, 0.6);
    animation: ceki-pulsing 0.9s infinite alternate ease-in-out;
  }
  @keyframes ceki-pulsing {
    0% { transform: scale(0.95); box-shadow: 0 0 6px rgba(239, 68, 68, 0.7); }
    100% { transform: scale(1.08); box-shadow: 0 0 18px rgba(245, 158, 11, 1), 0 0 24px rgba(239, 68, 68, 0.9); }
  }
  .btn-ceki-ready {
    animation: ceki-btn-pulse 1.1s infinite alternate ease-in-out !important;
  }
  @keyframes ceki-btn-pulse {
    0% { transform: scale(0.98); box-shadow: 0 0 8px rgba(245, 158, 11, 0.5); }
    100% { transform: scale(1.04); box-shadow: 0 0 20px rgba(251, 191, 36, 0.9), 0 0 30px rgba(239, 68, 68, 0.7); }
  }
  .spectator-banner {
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid #38bdf8;
    color: #38bdf8;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.2px;
    padding: 3px 12px;
    border-radius: 15px;
    box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
    display: inline-block;
  }

  /* MODALS & OVERLAYS */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.78);
    backdrop-filter: blur(8px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal-card {
    background: #0f172a;
    border: 1.5px solid #fbbf24;
    border-radius: 16px;
    padding: 20px;
    max-width: 540px;
    width: 90%;
    color: #f8fafc;
    box-shadow: 0 20px 45px rgba(0,0,0,0.8);
  }
  .modal-title {
    color: #facc15;
    font-size: 17px;
    font-weight: 800;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .modal-close {
    cursor: pointer;
    background: none;
    border: none;
    color: #94a3b8;
    font-size: 20px;
    font-weight: 800;
  }
  .modal-close:hover { color: #f8fafc; }

  /* OVERLAY COUNTDOWN */
  #round-countdown-overlay {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.95);
    border: 2px solid #facc15;
    border-radius: 999px;
    padding: 8px 24px;
    color: #facc15;
    font-weight: 800;
    font-size: 14px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.7), 0 0 15px rgba(250, 204, 21, 0.4);
    z-index: 999;
    display: none;
  }

  /* WINNER & NEXT ROUND MODAL */
  #winner-modal {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.88);
    backdrop-filter: blur(8px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 16px;
  }
  .winner-card {
    background: linear-gradient(145deg, #0f172a, #032213);
    border: 2px solid #facc15;
    border-radius: 20px;
    width: 100%;
    max-width: 820px;
    padding: 24px;
    text-align: center;
    box-shadow: 0 25px 60px rgba(0,0,0,0.8), 0 0 40px rgba(250, 204, 21, 0.25);
    animation: modalPop 0.35s cubic-bezier(0.2, 0.85, 0.3, 1) both;
  }
  @keyframes modalPop {
    0% { opacity: 0; transform: scale(0.85) translateY(20px); }
    100% { opacity: 1; transform: scale(1) translateY(0); }
  }
  .winner-crown {
    font-size: 50px;
    line-height: 1;
    margin-bottom: 6px;
    animation: crownBounce 1.5s ease-in-out infinite;
  }
  @keyframes crownBounce {
    0%, 100% { transform: translateY(0) rotate(0deg); }
    50% { transform: translateY(-7px) rotate(4deg); }
  }
  .winner-title {
    font-size: 22px;
    font-weight: 900;
    color: #fde047;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }
  .winner-sub {
    font-size: 13px;
    color: #94a3b8;
    margin-bottom: 16px;
  }
  .winner-hero {
    background: rgba(250, 204, 21, 0.1);
    border: 1px solid rgba(250, 204, 21, 0.3);
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 16px;
  }
  .winner-hero-name {
    font-size: 20px;
    font-weight: 900;
    color: #ffffff;
  }
  .winner-hero-score {
    font-size: 14px;
    font-weight: 700;
    color: #4ade80;
    margin-top: 4px;
  }
  .standings-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 16px;
    font-size: 12.5px;
  }
  .standings-table th {
    background: rgba(255,255,255,0.06);
    color: #94a3b8;
    padding: 6px 8px;
    text-align: left;
    font-weight: 700;
  }
  .standings-table td {
    padding: 7px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    color: #e2e8f0;
  }
  .standings-table tr.winner-row td {
    background: rgba(250, 204, 21, 0.12);
    color: #fde047;
    font-weight: 800;
  }
  .hist-card-group {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    padding: 2px 4px;
    margin-right: 5px;
    margin-bottom: 3px;
    vertical-align: middle;
  }
  .card.hist-mini {
    width: 27px !important;
    min-width: 27px !important;
    height: 36px !important;
    border-radius: 4px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.5) !important;
  }
  .card.hist-mini .c-mini-top {
    font-size: 8.5px !important;
    top: 1px !important;
    left: 2px !important;
    right: 2px !important;
  }
  .card.hist-mini .c-mini-center {
    font-size: 15px !important;
  }
  .card.hist-mini .c-mini-bot {
    display: none !important;
  }

  /* HISTORY & SCOREBOARD MODAL */
  #history-modal {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.9);
    backdrop-filter: blur(8px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1001;
    padding: 16px;
  }
  .history-modal-card {
    background: linear-gradient(145deg, #0f172a, #032213);
    border: 2px solid #34d399;
    border-radius: 20px;
    width: 100%;
    max-width: 860px;
    max-height: 88vh;
    padding: 24px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 25px 60px rgba(0,0,0,0.8), 0 0 40px rgba(52, 211, 153, 0.25);
    animation: modalPop 0.3s cubic-bezier(0.2, 0.85, 0.3, 1) both;
  }
  .history-modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 12px;
    margin-bottom: 16px;
  }
  .history-modal-title {
    font-size: 19px;
    font-weight: 900;
    color: #34d399;
    letter-spacing: 0.5px;
  }
  .history-modal-body {
    flex: 1;
    overflow-y: auto;
    padding-right: 6px;
  }
  .history-round-box {
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 14px;
  }
  .history-round-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    font-size: 13px;
    font-weight: 800;
    color: #fde047;
  }
  .btn-next-round {
    background: linear-gradient(135deg, #16a34a, #15803d);
    border: 2px solid #4ade80;
    color: white;
    font-size: 15px;
    font-weight: 900;
    padding: 12px 28px;
    border-radius: 12px;
    cursor: pointer;
    box-shadow: 0 4px 18px rgba(22, 163, 74, 0.45);
    transition: all 0.15s ease;
    width: 100%;
  }
  .btn-next-round:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(74, 222, 128, 0.55);
    background: linear-gradient(135deg, #22c55e, #16a34a);
  }

  /* DASHBOARD PILLS */
  .setting-group { margin-bottom: 12px; }
  .setting-label { font-size: 12px; font-weight: 700; color: #94a3b8; margin-bottom: 6px; }
  .pills-container { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill-btn {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    padding: 6px 12px;
    color: #e2e8f0;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.12s ease;
  }
  .pill-btn:hover { background: rgba(255,255,255,0.14); }
  .pill-btn.active {
    background: #16a34a;
    border-color: #4ade80;
    color: #fff;
    box-shadow: 0 0 10px rgba(74, 222, 128, 0.4);
  }
  .footer-btn {
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 800;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    font-family: inherit;
    transition: all 0.14s ease;
  }
  .btn-primary-start {
    background: linear-gradient(135deg, #16a34a, #15803d);
    color: #fff;
    box-shadow: 0 4px 12px rgba(22, 163, 74, 0.4);
  }
  .btn-primary-start:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn-secondary {
    background: rgba(255,255,255,0.1);
    color: #cbd5e1;
    border: 1px solid rgba(255,255,255,0.2);
  }
  .btn-secondary:hover { background: rgba(255,255,255,0.18); color: #fff; }

  /* ======================================================== */
  /* RUANG LOBBY MULTIPLAYER ROYALE                           */
  /* ======================================================== */
  #lobby-screen {
    width: 100%;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 16px;
    background: radial-gradient(ellipse at 50% 30%, #175432 0%, #0a311b 55%, #04140b 100%);
    overflow-y: auto;
    position: relative;
    box-sizing: border-box;
  }
  .lobby-container {
    width: 100%;
    max-width: 960px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin: auto 0;
  }
  .lobby-header-card {
    background: rgba(4, 22, 14, 0.94);
    backdrop-filter: blur(14px);
    border: 2px solid rgba(250, 204, 21, 0.45);
    border-radius: 16px;
    padding: 16px 22px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.65), inset 0 0 20px rgba(250, 204, 21, 0.08);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .lobby-title-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .lobby-main-title {
    font-size: 22px;
    font-weight: 900;
    color: #facc15;
    letter-spacing: 0.5px;
    display: flex;
    align-items: center;
    gap: 8px;
    text-shadow: 0 2px 10px rgba(250, 204, 21, 0.35);
  }
  .lobby-sub-title {
    font-size: 12.5px;
    color: #cbd5e1;
    font-weight: 600;
  }
  .lobby-header-actions {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .lobby-profile-card {
    background: rgba(15, 23, 42, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .lobby-name-input-box {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 260px;
  }
  .lobby-name-input {
    flex: 1;
    background: #0f172a;
    border: 1.5px solid #475569;
    border-radius: 8px;
    padding: 8px 14px;
    color: #f8fafc;
    font-size: 13.5px;
    font-weight: 700;
    font-family: inherit;
    transition: all 0.15s ease;
  }
  .lobby-name-input:focus {
    outline: none;
    border-color: #facc15;
    box-shadow: 0 0 10px rgba(250, 204, 21, 0.35);
  }
  .lobby-seats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    width: 100%;
  }
  .seat-card {
    background: rgba(4, 24, 15, 0.88);
    border: 1.5px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 10px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.45);
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
  }
  .seat-card.seat-me {
    border-color: #4ade80;
    background: radial-gradient(circle at 50% 20%, rgba(21, 128, 61, 0.45) 0%, rgba(4, 24, 15, 0.95) 80%);
    box-shadow: 0 0 20px rgba(74, 222, 128, 0.3), 0 8px 24px rgba(0,0,0,0.5);
  }
  .seat-card.seat-human {
    border-color: #38bdf8;
    background: radial-gradient(circle at 50% 20%, rgba(2, 132, 199, 0.35) 0%, rgba(4, 24, 15, 0.95) 80%);
  }
  .seat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    font-size: 12px;
    font-weight: 800;
    color: #fde047;
  }
  .seat-avatar {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: rgba(255,255,255,0.08);
    border: 2px solid rgba(255,255,255,0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    margin: 2px 0;
  }
  .seat-name {
    font-size: 14px;
    font-weight: 800;
    color: #f8fafc;
    word-break: break-word;
    max-width: 100%;
  }
  .seat-badge {
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
  }
  .seat-badge-me {
    background: #16a34a;
    color: #fff;
    box-shadow: 0 0 10px rgba(74, 222, 128, 0.5);
  }
  .seat-badge-human {
    background: #0284c7;
    color: #fff;
  }
  .seat-badge-bot {
    background: rgba(255, 255, 255, 0.12);
    color: #94a3b8;
  }
  .lobby-btn {
    width: 100%;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 800;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.14s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .btn-claim {
    background: linear-gradient(135deg, #16a34a, #15803d);
    color: #fff;
    box-shadow: 0 4px 12px rgba(22, 163, 74, 0.35);
  }
  .btn-claim:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn-leave {
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid #ef4444;
    color: #fca5a5;
  }
  .btn-leave:hover { background: rgba(239, 68, 68, 0.35); }
  .btn-switch {
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid #38bdf8;
    color: #bae6fd;
  }
  .btn-switch:hover { background: rgba(56, 189, 248, 0.28); }
  .seat-sub-actions {
    display: flex;
    gap: 4px;
    width: 100%;
  }
  .seat-sub-btn {
    flex: 1;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 6px;
    padding: 4px 6px;
    color: #cbd5e1;
    font-size: 10px;
    font-weight: 700;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.12s ease;
  }
  .seat-sub-btn:hover {
    background: rgba(255,255,255,0.16);
    color: #fff;
  }
  .lobby-config-card {
    background: rgba(4, 22, 14, 0.9);
    border: 1px solid rgba(250, 204, 21, 0.28);
    border-radius: 14px;
    padding: 14px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .lobby-start-box {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 14px;
    padding: 6px 0;
  }
  .btn-lobby-start {
    background: linear-gradient(135deg, #16a34a 0%, #15803d 100%);
    color: #fff;
    border: 2px solid #4ade80;
    border-radius: 12px;
    padding: 12px 40px;
    font-size: 16px;
    font-weight: 900;
    letter-spacing: 0.5px;
    cursor: pointer;
    box-shadow: 0 0 20px rgba(74, 222, 128, 0.4), 0 6px 18px rgba(0,0,0,0.4);
    transition: all 0.16s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: inherit;
  }
  .btn-lobby-start:hover {
    filter: brightness(1.12);
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 0 28px rgba(74, 222, 128, 0.6), 0 8px 22px rgba(0,0,0,0.5);
  }

  /* TOAST NOTIFICATION */
  #toast-notif {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(40px);
    background: rgba(15, 23, 42, 0.95);
    border: 1.5px solid #facc15;
    border-radius: 999px;
    padding: 8px 20px;
    color: #facc15;
    font-size: 13px;
    font-weight: 800;
    box-shadow: 0 8px 24px rgba(0,0,0,0.65), 0 0 15px rgba(250, 204, 21, 0.3);
    z-index: 9999;
    opacity: 0;
    pointer-events: none;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  }
  #toast-notif.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  @media (max-height: 640px) {
    :root {
      --hand-card-w: clamp(48px, 4.2vw, 62px);
      --hand-card-h: clamp(72px, 6.2vw, 90px);
      --disc-card-w: clamp(46px, 4.0vw, 60px);
      --disc-card-h: clamp(68px, 6.0vw, 88px);
      --meld-card-w: clamp(28px, 2.4vw, 36px);
      --meld-card-h: clamp(40px, 3.5vw, 52px);
    }
    #table { padding: 3px 8px; gap: 4px; }
    .table-body-split { gap: 8px; }
    #deck-wild-row { height: 105px; }
    .player-strip { padding: 4px 8px; }
    .c-rank { font-size: 14px !important; }
    .c-suit-mini { font-size: 12px !important; }
    .c-center { font-size: 28px !important; }
    .btn-action { height: 28px; padding: 0 8px; font-size: 10px; }
  }
  @media (max-width: 900px) {
    .table-body-split {
      grid-template-columns: 1fr;
      overflow-y: auto;
    }
    #players-col {
      height: auto;
      min-height: 380px;
    }
    #arena-col {
      height: auto;
      min-height: 280px;
    }
  }

</style>
</head>
<body>

<div id="lobby-screen">
  <div class="lobby-container">
    <!-- HEADER -->
    <div class="lobby-header-card">
      <div class="lobby-title-group">
        <div class="lobby-main-title">
          <span>👑</span> REMI NUSANTARA 2D — RUANG LOBBY
        </div>
        <div class="lobby-sub-title" id="lobby-status-msg">
          Pilih kursi Anda, atur konfigurasi meja, dan ajak teman mabar!
        </div>
      </div>
      <div class="lobby-header-actions">
        <button class="header-dash-btn" onclick="copyLobbyLink()" style="background:rgba(250,204,21,0.18);border-color:#facc15;color:#facc15;">
          📋 SALIN LINK LOBBY
        </button>
        <button id="btn-lobby-spectate" class="header-dash-btn" onclick="spectateGame()" style="display:none;background:rgba(56,189,248,0.2);border-color:#38bdf8;color:#38bdf8;">
          👁️ TONTON PERMAINAN
        </button>
      </div>
    </div>

    <!-- PLAYER PROFILE SETUP -->
    <div class="lobby-profile-card">
      <div class="lobby-name-input-box">
        <span style="font-size:12px;font-weight:800;color:#94a3b8;white-space:nowrap;">NAMA ANDA:</span>
        <input type="text" id="lobby-player-name" class="lobby-name-input" placeholder="Masukkan nama Anda..." onchange="onLobbyNameChange(this.value)">
      </div>
      <div style="font-size:12px;color:#cbd5e1;font-weight:600;">
        Room Code: <span id="lobby-room-code" style="color:#fde047;font-weight:800;">#RM1500</span> • <span id="lobby-player-summary">Menunggu Pemain...</span>
      </div>
    </div>

    <!-- SEAT SELECTION GRID (4 SEATS) -->
    <div class="lobby-seats-grid" id="lobby-seats-grid"></div>

    <!-- ROOM CONFIGURATION (LIVE SYNC) -->
    <div class="lobby-config-card">
      <div style="font-size:13px;font-weight:800;color:#facc15;display:flex;justify-content:space-between;align-items:center;">
        <span>⚙️ PENGATURAN MEJA PERMAINAN</span>
        <span style="font-size:11px;color:#94a3b8;font-weight:600;">Otomatis sinkron ke seluruh pemain</span>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:12px;">
        <div class="setting-group" style="margin-bottom:0;">
          <div class="setting-label">JUMLAH PEMAIN:</div>
          <div id="lobby-players-pills" class="pills-container">
            <button class="pill-btn" onclick="updateLobbyConfig('players', 2)">2 Pemain</button>
            <button class="pill-btn" onclick="updateLobbyConfig('players', 3)">3 Pemain</button>
            <button class="pill-btn active" onclick="updateLobbyConfig('players', 4)">4 Pemain</button>
          </div>
        </div>

        <div class="setting-group" style="margin-bottom:0;">
          <div class="setting-label">TARGET SKOR: <span id="lobby-score-badge" style="color:#facc15;">1500 Poin</span></div>
          <div id="lobby-score-pills" class="pills-container">
            <button class="pill-btn" onclick="updateLobbyConfig('score', 500)">500</button>
            <button class="pill-btn" onclick="updateLobbyConfig('score', 1000)">1000</button>
            <button class="pill-btn active" onclick="updateLobbyConfig('score', 1500)">1500</button>
            <button class="pill-btn" onclick="updateLobbyConfig('score', 2000)">2000</button>
          </div>
        </div>

        <div class="setting-group" style="margin-bottom:0;">
          <div class="setting-label">TIMER GILIRAN: <span id="lobby-timer-badge" style="color:#38bdf8;">Tanpa</span></div>
          <div id="lobby-timer-pills" class="pills-container">
            <button class="pill-btn active" onclick="updateLobbyConfig('timer', 0)">Tanpa</button>
            <button class="pill-btn" onclick="updateLobbyConfig('timer', 15)">15s</button>
            <button class="pill-btn" onclick="updateLobbyConfig('timer', 30)">30s</button>
            <button class="pill-btn" onclick="updateLobbyConfig('timer', 45)">45s</button>
          </div>
        </div>

        <div class="setting-group" style="margin-bottom:0;">
          <div class="setting-label">KECEPATAN BOT:</div>
          <div id="lobby-bot-pills" class="pills-container">
            <button class="pill-btn" onclick="updateLobbyConfig('botDelay', 0.4)">Cepat</button>
            <button class="pill-btn active" onclick="updateLobbyConfig('botDelay', 1.0)">Normal</button>
            <button class="pill-btn" onclick="updateLobbyConfig('botDelay', 1.8)">Santai</button>
          </div>
        </div>
      </div>
    </div>

    <!-- START GAME CTA -->
    <div class="lobby-start-box">
      <button id="btn-start-lobby-game" class="btn-lobby-start" onclick="startLobbyGame()">
        ▶️ MULAI PERMAINAN
      </button>
    </div>
  </div>
</div>

<div id="table">
  <!-- TOP HEADER HUD -->
  <div class="header-bar">
    <div class="header-top-row">
      <div class="header-brand">
        <span class="brand-logo">👑</span>
        <span id="hdr-title" class="header-title">REMI NUSANTARA 2D</span>
      </div>
      <div class="header-btn-group">
        <button id="btn-show-history" onclick="openHistoryModal()" class="header-dash-btn" style="background: rgba(16, 185, 129, 0.2); border-color: #34d399; color: #a7f3d0;" title="Lihat Riwayat Skor & Kartu Permainan (H)">
          📜 RIWAYAT (H)
        </button>
        <button id="btn-to-lobby" onclick="returnToLobby()" class="header-dash-btn" style="background: rgba(239, 68, 68, 0.2); border-color: #f87171; color: #fca5a5;" title="Kembali ke Ruang Lobby (Reset Room)">
          🏠 LOBBY
        </button>
        <button id="btn-leave-table" onclick="leaveTableDuringGame()" class="header-dash-btn" style="background: rgba(245, 158, 11, 0.2); border-color: #f59e0b; color: #fde047;" title="Tinggalkan kursi Anda dan kembali ke Lobby (digantikan Bot)">
          🚪 KELUAR MEJA
        </button>
        <button id="btn-invite" onclick="openInviteModal()" class="header-dash-btn" title="Undang teman bermain via Link atau Room Code">
          👥 UNDANG TEMAN
        </button>
        <button id="btn-pause-header" onclick="togglePause()" class="header-dash-btn" style="background: rgba(2, 132, 199, 0.25); border-color: #38bdf8;">
          ⏸ PAUSE (ESC)
        </button>
        <button id="btn-dash" onclick="openDashboard()" class="header-dash-btn" style="background: rgba(250, 204, 21, 0.15); border-color: #facc15; color: #facc15;">
          ⚙ PENGATURAN (P)
        </button>
      </div>
    </div>
    <div id="hdr-turn-banner" class="turn-banner turn-my">★ MEMUAT STATUS MEJA... ★</div>
    <div id="hdr-status" class="status-notif" style="display:none;"></div>
  </div>

  <!-- MAIN ARENA SPLIT: LEFT (DISCARD & DECK) vs RIGHT (3 OPPONENTS) -->
  <div class="table-main-split">
    <!-- LEFT COLUMN: ARENA (ACTIVE DISCARD, BURIED DISCARD, DECK & WILD) -->
    <div id="arena-col">
      <!-- ROW 1: 7 KARTU BUANGAN (AKTIF) -->
      <div id="disc-active-bar" class="arena-bar" ondragover="onDiscardDragOver(event)" ondragleave="onDiscardDragLeave(event)" ondrop="onDiscardDrop(event)">
        <div class="arena-bar-hdr">
          <div style="display:flex;align-items:center;gap:6px;">
            <span class="bar-hdr-icon">🎴</span>
            <span class="bar-hdr-title">7 KARTU BUANGAN (AKTIF)</span>
          </div>
          <span id="disc-active-pill" class="arena-pill">0/7 Aktif</span>
        </div>
        <div id="disc-active-cards" class="disc-active-grid"></div>
      </div>

      <!-- ROW 2: KARTU BUANGAN LEBIH DARI 7 (TERKUBUR) -->
      <div id="disc-buried-bar" class="arena-bar">
        <div class="arena-bar-hdr">
          <div style="display:flex;align-items:center;gap:6px;">
            <span class="bar-hdr-icon">🗄️</span>
            <span class="bar-hdr-title">KARTU BUANGAN LEBIH DARI 7 (TERKUBUR)</span>
          </div>
          <span id="disc-buried-pill" class="arena-pill">0 Terkubur</span>
        </div>
        <div id="disc-buried-cards" class="disc-buried-scroll">
          <span class="buried-empty-hint">Belum ada kartu buangan lebih dari 7</span>
        </div>
      </div>

      <!-- ROW 3: PAK KARTU & BUKAAN WILD (SIDE-BY-SIDE) -->
      <div id="deck-wild-row">
        <!-- PAK KARTU (WITH DESIGN BELAKANG KARTU) -->
        <div id="pak-box" onclick="sendAction('DRAW_DECK')" draggable="true" ondragstart="onPakDragStart(event)" ondragend="onDragEndClean(event)" title="Klik atau Tarik ke tangan untuk ambil kartu (D)">
          <div class="pak-card-back-visual">
            <div class="card-back pak-mini-deck">
              <span class="card-back-suit">♠</span>
            </div>
          </div>
          <div class="pak-info-side">
            <div class="pak-label">PAK KARTU</div>
            <div id="pak-count" class="pak-count">(24)</div>
            <div class="pak-hint">KLIK / TARIK (D)</div>
          </div>
        </div>

        <!-- BUKAAN WILD (WITH BUKAAN WILD X5) -->
        <div id="wild-box">
          <div id="wild-card-slot" class="wild-card-holder"></div>
          <div class="wild-info-side">
            <div id="wild-title" class="wild-label">BUKAAN WILD</div>
            <div class="wild-sub">PENGALI SKOR</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT COLUMN: 3 OPPONENTS STACKED (JUMLAH KARTU LEFT + KARTU JADI RIGHT) -->
    <div id="opponents-col">
      <!-- OPPONENT 1 (TOP) -->
      <div id="zone-opp-1" class="zone-box opp-split-pod">
        <div class="opp-split-hdr">
          <div class="player-title" id="opp-1-title">Bot Budi</div>
          <div id="opp-1-melds-label" class="opp-melds-label">Kartu Jadi:</div>
        </div>
        <div class="opp-split-body">
          <!-- LEFT: JUMLAH KARTU (NUMBER) -->
          <div class="opp-count-box" id="opp-1-cards">
            <div class="opp-hand-count-visual">
              <div class="card-back opp-card-back-icon"><span>♠</span></div>
              <div class="opp-count-info">
                <span class="opp-count-num">7</span>
                <span class="opp-count-txt">KARTU</span>
              </div>
            </div>
          </div>
          <!-- RIGHT: KARTU JADI (WIDE BOX) -->
          <div class="opp-melds-box meld-container" id="opp-1-melds">
            <div class="meld-empty-hint">Belum ada kartu jadi</div>
          </div>
        </div>
      </div>

      <!-- OPPONENT 2 (MID) -->
      <div id="zone-opp-2" class="zone-box opp-split-pod">
        <div class="opp-split-hdr">
          <div class="player-title" id="opp-2-title">Bot Siti</div>
          <div id="opp-2-melds-label" class="opp-melds-label">Kartu Jadi:</div>
        </div>
        <div class="opp-split-body">
          <!-- LEFT: JUMLAH KARTU (NUMBER) -->
          <div class="opp-count-box" id="opp-2-cards">
            <div class="opp-hand-count-visual">
              <div class="card-back opp-card-back-icon"><span>♠</span></div>
              <div class="opp-count-info">
                <span class="opp-count-num">7</span>
                <span class="opp-count-txt">KARTU</span>
              </div>
            </div>
          </div>
          <!-- RIGHT: KARTU JADI (WIDE BOX) -->
          <div class="opp-melds-box meld-container" id="opp-2-melds">
            <div class="meld-empty-hint">Belum ada kartu jadi</div>
          </div>
        </div>
      </div>

      <!-- OPPONENT 3 (BOTTOM) -->
      <div id="zone-opp-3" class="zone-box opp-split-pod">
        <div class="opp-split-hdr">
          <div class="player-title" id="opp-3-title">Bot Agus</div>
          <div id="opp-3-melds-label" class="opp-melds-label">Kartu Jadi:</div>
        </div>
        <div class="opp-split-body">
          <!-- LEFT: JUMLAH KARTU (NUMBER) -->
          <div class="opp-count-box" id="opp-3-cards">
            <div class="opp-hand-count-visual">
              <div class="card-back opp-card-back-icon"><span>♠</span></div>
              <div class="opp-count-info">
                <span class="opp-count-num">7</span>
                <span class="opp-count-txt">KARTU</span>
              </div>
            </div>
          </div>
          <!-- RIGHT: KARTU JADI (WIDE BOX) -->
          <div class="opp-melds-box meld-container" id="opp-3-melds">
            <div class="meld-empty-hint">Belum ada kartu jadi</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- PLAYER HERO CONSOLE: ROUNDED CASINO STADIUM ACROSS BOTTOM -->
  <div id="zone-bottom" class="zone-box player-stadium-console" ondragover="onHandDragOver(event)" ondragleave="onHandDragLeave(event)" ondrop="onHandDrop(event)">
    <div class="stadium-hdr">
      <div style="display:flex;align-items:center;gap:8px;">
        <span id="my-turn-badge" class="turn-badge" style="display:none;font-size:10.5px;padding:2px 8px;">★ GILIRAN ANDA! ★</span>
        <span id="my-info" class="player-title" style="font-size:12px;color:#facc15;">Anda (Player 1)</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;">
        <span id="my-step-badge" style="display:none;font-size:10px;font-weight:900;padding:2px 8px;border-radius:999px;"></span>
        <span id="my-seri-badge" style="font-size:9.5px;font-weight:800;color:#f87171;background:rgba(0,0,0,0.35);padding:2px 7px;border-radius:999px;">
          BELUM ADA SERI MIN 3 (AWAS TERBAKAR!)
        </span>
      </div>
    </div>

    <!-- TOP CENTER BOX: KARTU JADI (MELDS) -->
    <div id="player-melds-center-box" class="player-melds-center-box">
      <div class="player-melds-hdr">🎴 KARTU JADI ANDA (MELDS DI MEJA)</div>
      <div id="my-melds" class="meld-container player-melds-flow">
        <div class="meld-empty-hint">Belum ada kartu jadi di meja • Wajib min 1 Seri Urut agar aman</div>
      </div>
    </div>

    <!-- MAIN BOTTOM BOX: KARTU TANGAN (HAND) -->
    <div id="player-hand-wide-box" class="player-hand-wide-box">
      <div class="player-hand-hdr">🃏 KARTU TANGAN ANDA</div>
      <div id="my-hand"></div>
    </div>

    <!-- HIDDEN COMPATIBILITY CONTAINERS -->
    <div id="my-melds-left-cards" style="display:none;"></div>
    <div id="my-melds-right-cards" style="display:none;"></div>
    <div id="disc-cards" style="display:none;"></div>
    <div id="disc-buried-tray" style="display:none;"></div>
    <div id="discard-rail" style="display:none;"></div>
  </div>

  <!-- ACTION DOCK (ALWAYS 100% VISIBLE & ACCESSIBLE!) -->
  <div id="action-bar">
    <button class="btn-action btn-draw" onclick="sendAction('DRAW_DECK')" title="Ambil 1 kartu dari Pak Tertutup (D)">
      🃏 AMBIL PAK (D)
    </button>
    <button class="btn-action btn-meld" onclick="meldSelected()" title="Turunkan kartu yang dipilih menjadi Seri atau Kembar (M)">
      ✨ TURUNKAN (M)
    </button>
    <button class="btn-action btn-auto" onclick="sendAction('AUTO_MELD')" title="Otomatis turunkan semua kartu jadi yang ada di tangan (A)">
      ⚡ AUTO TURUN (A)
    </button>
    <button class="btn-action btn-discard" onclick="discardSelected()" title="Buang 1 kartu pilihan ke tumpukan buangan (B)">
      🗑️ BUANG KARTU (B)
    </button>
    <button id="btn-tutup-tangan" class="btn-action btn-tutup" onclick="declareTutupTangan()" title="Tutup Tangan langsung dari tangan (+250 Poin) (T)">
      🏆 TUTUP TANGAN +250 (T)
    </button>
    <button id="btn-ceki" class="btn-action btn-ceki" onclick="triggerCeki()" title="Serukan CEKI! (C) - Cooldown 2 Detik">
      📢 CEKI (C)
    </button>
    <button class="btn-action btn-sort" onclick="sendAction('SORT_RANK')" title="Urutkan kartu tangan berdasarkan Angka (S)">
      🔢 URUT ANGKA (S)
    </button>
    <button class="btn-action btn-sort" onclick="sendAction('SORT_SUIT')" title="Urutkan kartu tangan berdasarkan Kembang / Warna (F)">
      ♠️ URUT KEMBANG (F)
    </button>
    <button class="btn-action btn-slide" onclick="slideSelectedCard(-1)" title="Geser kartu yang dipilih ke Kiri ([)">
      ◀ GESER KIRI ([)
    </button>
    <button class="btn-action btn-slide" onclick="slideSelectedCard(1)" title="Geser kartu yang dipilih ke Kanan (])">
      GESER KANAN (]) ▶
    </button>
  </div>
</div>

<!-- ROUND COUNTDOWN OVERLAY -->
<div id="round-countdown-overlay" style="display:none;">
  ⏳ Ronde berikutnya dimulai dalam: <span id="countdown-sec" style="font-size:18px;color:#fff;">5</span> detik...
</div>

<!-- WINNER & NEXT ROUND MODAL -->
<div id="winner-modal">
  <div class="winner-card">
    <div class="winner-crown">👑</div>
    <div id="winner-title" class="winner-title">RONDE SELESAI!</div>
    <div id="winner-sub" class="winner-sub">Hasil perolehan poin ronde ini</div>
    <div id="winner-hero" class="winner-hero">
      <div id="winner-hero-name" class="winner-hero-name">Pemenang: -</div>
      <div id="winner-hero-score" class="winner-hero-score">+0 Poin Ronde Ini</div>
    </div>
    <div style="overflow-x: auto; margin-bottom: 16px;">
      <table class="standings-table">
        <thead>
          <tr>
            <th style="min-width: 140px;">Pemain</th>
            <th style="min-width: 240px;">Kartu Jadi (Melds)</th>
            <th style="min-width: 160px;">Sisa Kartu Tangan</th>
            <th style="text-align:center; min-width: 80px;">Ronde Ini</th>
            <th style="text-align:right; min-width: 80px;">Total Skor</th>
          </tr>
        </thead>
        <tbody id="winner-table-body"></tbody>
      </table>
    </div>
    <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
      <button id="btn-next-round-action" class="btn-next-round" style="flex:1; min-width:240px;" onclick="nextRoundNow()">
        ▶️ LANJUT KE RONDE BERIKUTNYA
      </button>
      <button class="pill-btn" onclick="openHistoryModal()" style="background:rgba(16,185,129,0.25); border:1px solid #34d399; color:#a7f3d0; font-size:13px; font-weight:800; padding:10px 18px; border-radius:12px; cursor:pointer;">
        📜 RIWAYAT LENGKAP
      </button>
      <button class="pill-btn" onclick="returnToLobby()" style="background:rgba(239,68,68,0.2); border:1px solid #f87171; color:#fca5a5; font-size:13px; font-weight:800; padding:10px 18px; border-radius:12px; cursor:pointer;">
        🏠 KE LOBBY
      </button>
    </div>
  </div>
</div>

<!-- HISTORY & SCOREBOARD MODAL -->
<div id="history-modal">
  <div class="history-modal-card">
    <div class="history-modal-header">
      <div class="history-modal-title">📜 RIWAYAT PERMAINAN & KARTU</div>
      <button onclick="closeHistoryModal()" class="pill-btn" style="background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#cbd5e1; font-weight:800; padding:6px 14px; border-radius:8px; cursor:pointer;">✕ TUTUP</button>
    </div>
    <div id="history-modal-body" class="history-modal-body"></div>
  </div>
</div>

<!-- PAUSE MODAL -->
<div id="pause-modal" class="modal-overlay">
  <div class="modal-card" style="text-align:center;max-width:400px;">
    <div style="font-size:42px;margin-bottom:8px;">⏸️</div>
    <div style="font-size:18px;font-weight:800;color:#facc15;margin-bottom:6px;">PERMAINAN DIHENTIKAN (PAUSED)</div>
    <p style="font-size:12px;color:#94a3b8;margin-bottom:16px;">
      Timer giliran dan aksi bot dibekukan. Anda dapat melanjutkan kapan saja.
    </p>
    <button id="btn-pause-action" onclick="togglePause()" class="footer-btn btn-primary-start" style="padding:10px 24px;font-size:13px;">
      ▶️ LANJUTKAN PERMAINAN (ESC)
    </button>
  </div>
</div>

<!-- INVITE MODAL -->
<div id="invite-modal" class="modal-overlay">
  <div class="modal-card">
    <div class="modal-title">
      <span>👥 MAIN BERSAMA TEMAN</span>
      <button class="modal-close" onclick="closeInviteModal()">✕</button>
    </div>
    <p style="font-size:12px;color:#cbd5e1;margin-bottom:12px;">
      Teman di jaringan WiFi / Hotspot yang sama dapat bergabung ke meja ini:
    </p>
    <div style="margin-bottom:12px;">
      <div class="setting-label">IP ADDRESS / LINK HOST:</div>
      <input type="text" id="invite-host-ip" readonly style="width:100%;padding:8px 12px;background:#1e293b;border:1px solid #475569;border-radius:8px;color:#facc15;font-family:monospace;font-size:12px;" onclick="this.select()">
    </div>
    <div class="setting-label">SLOT KURSI PEMAIN:</div>
    <div id="invite-slots-list" style="display:flex;flex-direction:column;gap:6px;margin-bottom:14px;"></div>
    <div style="text-align:right;">
      <button class="footer-btn btn-secondary" onclick="closeInviteModal()">TUTUP</button>
    </div>
  </div>
</div>

<!-- DASHBOARD & SETTINGS MODAL -->
<div id="dashboard-modal" class="modal-overlay">
  <div class="modal-card">
    <div class="modal-title">
      <span>⚙️ PENGATURAN MEJA & GAMEPLAY</span>
      <button class="modal-close" onclick="closeDashboard()">✕</button>
    </div>
    <div class="setting-group">
      <div class="setting-label">NAMA PEMAIN:</div>
      <input type="text" id="cfg-player-name" placeholder="Masukkan nama Anda..." style="width:100%;padding:8px 12px;background:#1e293b;border:1px solid #475569;border-radius:8px;color:#fff;font-size:13px;font-family:inherit;">
    </div>
    <div class="setting-group">
      <div class="setting-label">JUMLAH PEMAIN:</div>
      <div id="player-pills" class="pills-container">
        <button class="pill-btn" onclick="selectConfig('players', 2)">2 Pemain</button>
        <button class="pill-btn" onclick="selectConfig('players', 3)">3 Pemain</button>
        <button class="pill-btn active" onclick="selectConfig('players', 4)">4 Pemain (Standar)</button>
      </div>
    </div>
    <div class="setting-group">
      <div class="setting-label">TARGET SKOR KEMENANGAN: <span id="score-badge-active" style="color:#facc15;font-weight:800;">1500 Poin</span></div>
      <div id="score-pills" class="pills-container">
        <button class="pill-btn" onclick="selectConfig('score', 500)">500 (Cepat)</button>
        <button class="pill-btn" onclick="selectConfig('score', 1000)">1000 (Sedang)</button>
        <button class="pill-btn active" onclick="selectConfig('score', 1500)">1500 (Standar)</button>
        <button class="pill-btn" onclick="selectConfig('score', 2000)">2000 (Maraton)</button>
      </div>
    </div>
    <div class="setting-group">
      <div class="setting-label">TIMER PER GILIRAN: <span id="timer-badge-active" style="color:#38bdf8;font-weight:800;">Tanpa Timer (Santai)</span></div>
      <div id="timer-pills" class="pills-container">
        <button class="pill-btn active" onclick="selectConfig('timer', 0)">Tanpa Timer (Santai)</button>
        <button class="pill-btn" onclick="selectConfig('timer', 15)">15s (Blitz)</button>
        <button class="pill-btn" onclick="selectConfig('timer', 30)">30s (Standar)</button>
        <button class="pill-btn" onclick="selectConfig('timer', 45)">45s (Cukup)</button>
      </div>
      <div id="timer-explain" style="font-size:10.5px;color:#94a3b8;margin-top:4px;">Auto buang kartu jika waktu habis</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">KECEPATAN BOT (BOT DELAY):</div>
      <div id="bot-pills" class="pills-container">
        <button class="pill-btn" onclick="selectConfig('botDelay', 0.4)">Cepat (0.4s)</button>
        <button class="pill-btn active" onclick="selectConfig('botDelay', 1.0)">Normal (1.0s)</button>
        <button class="pill-btn" onclick="selectConfig('botDelay', 1.8)">Lambat (1.8s)</button>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;">
      <button class="footer-btn btn-secondary" onclick="saveSettingsOnly()">💾 SIMPAN</button>
      <button class="footer-btn btn-primary-start" onclick="saveAndStartGame()">▶️ MULAI BARU</button>
    </div>
  </div>
</div>

<!-- TOAST NOTIFICATION -->
<div id="toast-notif"></div>

<script>
const urlParams = new URLSearchParams(window.location.search);
let mySeat = null;
if (urlParams.has('seat')) {
  const parsedSeat = parseInt(urlParams.get('seat'), 10);
  if (!isNaN(parsedSeat)) {
    mySeat = parsedSeat;
    sessionStorage.setItem('remi_my_seat', String(mySeat));
  }
} else {
  const storedSeat = sessionStorage.getItem('remi_my_seat');
  if (storedSeat !== null && storedSeat !== undefined && storedSeat !== '') {
    const parsedSeat = parseInt(storedSeat, 10);
    if (!isNaN(parsedSeat)) mySeat = parsedSeat;
  }
}
let spectatorMode = false;
let myPlayerId = localStorage.getItem('remi_player_id');
if (!myPlayerId) {
  myPlayerId = 'usr_' + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
  localStorage.setItem('remi_player_id', myPlayerId);
}
let selectedCards = new Set();
let latestState = null;
let currentDrag = null;
let initialClaimDone = false;
let lastHandSig = '';
let lastDiscSig = '';
let lastAnimatedRound = -1;

const SUIT_ICON = { 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' };

let currentConfig = {
  players: 4,
  score: 1500,
  timer: 0,
  botDelay: 1.0,
  playerName: 'Anda (Player 1)'
};

function groupBadge(c) {
  if (c.rank === 'JOKER' || c.is_wild) return 'WILD';
  if (c.rank === 'A') return '+15';
  if (['K','Q','J'].includes(c.rank)) return '+10';
  return '+5';
}

function renderCardHTML(c, opts = {}) {
  const isRed = c.suit === 'H' || c.suit === 'D';
  const isWild = Boolean(c.is_wild || c.rank === 'JOKER');
  const cls = [
    'card',
    isRed ? 'red' : 'black',
    isWild ? 'joker' : '',
    opts.selected ? 'selected' : '',
    opts.locked ? 'locked' : '',
    opts.small ? 'small' : ''
  ].filter(Boolean).join(' ');

  const topRank = c.rank === 'JOKER' ? 'JKR' : c.rank;
  const suitIcon = SUIT_ICON[c.suit] || (c.rank === 'JOKER' ? '★' : '♠');
  const isActionBadge = Boolean(opts.badge);
  const pointText = groupBadge(c);
  const onclick = opts.onclick ? `onclick="${opts.onclick}"` : '';
  const onctx = opts.onrightclick ? `oncontextmenu="${opts.onrightclick}; return false;"` : '';
  const draggable = opts.draggable ? 'draggable="true"' : '';
  const ondragstart = opts.ondragstart ? `ondragstart="${opts.ondragstart}"` : '';
  const ondragend = opts.ondragend ? `ondragend="${opts.ondragend}"` : '';
  const ondragover = opts.ondragover ? `ondragover="${opts.ondragover}"` : '';
  const ondragleave = opts.ondragleave ? `ondragleave="${opts.ondragleave}"` : '';
  const ondrop = opts.ondrop ? `ondrop="${opts.ondrop}"` : '';

  if (opts.small) {
    return `<div class="${cls}" ${onclick} ${onctx} ${draggable} ${ondragstart} ${ondragend} ${ondragover} ${ondragleave} ${ondrop} title="${opts.hint || ''}">
      <div class="c-mini-top"><span>${topRank}</span><span>${isWild && c.rank !== 'JOKER' ? '★' : suitIcon}</span></div>
      <div class="c-mini-center">${suitIcon}</div>
      ${pointText ? `<div class="c-mini-bot">${pointText}</div>` : ''}
    </div>`;
  }

  return `<div class="${cls}" ${onclick} ${onctx} ${draggable} ${ondragstart} ${ondragend} ${ondragover} ${ondragleave} ${ondrop} title="${opts.hint || ''}">
    <div class="c-corner c-corner-tl">
      <span class="c-rank">${topRank}</span>
      <span class="c-suit-mini">${suitIcon}</span>
    </div>
    ${isWild && c.rank !== 'JOKER' ? '<div class="c-wild-ribbon">WILD</div>' : ''}
    <div class="c-center">${c.rank === 'JOKER' ? '★' : suitIcon}</div>
    ${!isWild && pointText && !isActionBadge ? `<div class="c-point-pill">${pointText}</div>` : ''}
    ${isActionBadge ? `<div class="c-badge-pill">${opts.badge}</div>` : ''}
    <div class="c-corner c-corner-br">
      <span class="c-rank">${topRank}</span>
      <span class="c-suit-mini">${suitIcon}</span>
    </div>
  </div>`;
}

function renderMeldsHTML(melds, isOpp = false) {
  if (!melds || !melds.length) {
    if (isOpp) return '<div class="meld-empty-hint">Belum ada kartu jadi</div>';
    return '<div class="meld-empty-hint">Belum ada kartu jadi di meja • Wajib min 1 Seri Urut agar aman</div>';
  }
  return melds.map(m => `<div class="meld-group">${m.map(c => renderCardHTML(c, { small: true })).join('')}</div>`).join('');
}

function renderCardMiniGroup(cardList) {
  if (!cardList || cardList.length === 0) return '';
  return '<div class="hist-card-group">' + cardList.map(c => {
    return renderCardHTML(c, { small: true }).replace('class="card', 'class="card hist-mini');
  }).join('') + '</div>';
}

function renderPlayerMeldsHTML(melds) {
  if (!melds || melds.length === 0) {
    return '<span style="color:#f87171; font-size:11px; font-style:italic;">(Tidak ada kartu jadi)</span>';
  }
  return melds.map(m => renderCardMiniGroup(m)).join('');
}

function renderPlayerHandHTML(hand, isClosed) {
  if (!hand || hand.length === 0) {
    return '<span style="color:#4ade80; font-size:11.5px; font-weight:700;">✓ Habis (Tutup)</span>';
  }
  return '<div style="display:inline-flex; gap:2px; flex-wrap:wrap; align-items:center;">' + hand.map(c => {
    return renderCardHTML(c, { small: true }).replace('class="card', 'class="card hist-mini');
  }).join('') + '</div>';
}

function renderOpponentZone(prefix, p, isTurn, showFace, targetScore, leaderSeat) {
  const zoneEl = document.getElementById(`zone-${prefix}`);
  const titleEl = document.getElementById(`${prefix}-title`);
  const cardsEl = document.getElementById(`${prefix}-cards`);
  const meldsLabelEl = document.getElementById(`${prefix}-melds-label`);
  const meldsEl = document.getElementById(`${prefix}-melds`);

  if (!zoneEl || !p) return;
  const basePodClass = 'zone-box opp-split-pod';
  zoneEl.className = basePodClass + (isTurn ? ' zone-active opponent-turn-active' : '');

  const badgeHTML = isTurn ? `<span class="turn-badge" style="background:#38bdf8;color:#082f49;box-shadow:0 0 10px #38bdf8;">⏳ SEDANG JALAN...</span> ` : '';
  const isLeader = (leaderSeat !== null && leaderSeat !== undefined && p.seat === leaderSeat && (latestState && (latestState.round_number > 1 || p.total_score > 0)));
  const leaderTag = isLeader ? ' <span style="color:#facc15;font-size:0.85em;">[👑 SKOR TERTINGGI]</span>' : '';
  const burnTag = p.burned_last_round ? ' <span style="color:#f87171;">[TERBAKAR!]</span>' : '';
  const cekiTag = p.is_ceki ? ' <span class="badge-ceki-glow">🔥 CEKI!</span>' : '';

  if (titleEl) {
    titleEl.innerHTML = `${badgeHTML}${p.name}${cekiTag}${leaderTag}${burnTag} • Skor: ${p.total_score}/${targetScore} (${p.last_round_score >= 0 ? '+' : ''}${p.last_round_score})`;
  }

  let handHTML = '';
  if (showFace && p.hand && p.hand.length) {
    handHTML = `<div style="display:flex;gap:2px;overflow-x:auto;">` + p.hand.map(c => renderCardHTML(c, { small: true })).join('') + `</div>`;
  } else {
    // Elegant casino card back with "jumlah kartu (number)"
    handHTML = `
      <div class="opp-hand-count-visual" title="${p.name} memegang ${p.hand_count} kartu">
        <div class="card-back opp-card-back-icon"><span>♠</span></div>
        <div class="opp-count-info">
          <span class="opp-count-num">${p.hand_count}</span>
          <span class="opp-count-txt">KARTU</span>
        </div>
      </div>
    `;
  }
  if (cardsEl) cardsEl.innerHTML = handHTML;

  if (meldsLabelEl) {
    const seriTag = p.has_seri
      ? '<span style="color:#4ade80;">(Ada Seri ✓)</span>'
      : '<span style="color:#f87171;">(Belum Ada Seri ⚠)</span>';
    meldsLabelEl.innerHTML = `Kartu Jadi ${seriTag}:`;
  }

  if (meldsEl) {
    meldsEl.innerHTML = renderMeldsHTML(p.melds, true);
  }
}

function updateUI(st) {
  latestState = st;

  // 1. Klaim Kursi Awal: jalankan klaim segera jika kursi ditentukan di URL / session, atau jika meja kosong (pengunjung pertama menjadi Host)
  if (!initialClaimDone) {
    initialClaimDone = true;
    if (mySeat === null && !spectatorMode && st.players && st.players.length > 0) {
      const isAnyHuman = st.players.some(p => !p.is_bot && p.player_id);
      if (!isAnyHuman) {
        mySeat = 0; // Pengunjung pertama otomatis menjadi Host (Kursi 1)
      }
    }
    if (mySeat !== null && st.players && st.players[mySeat]) {
      const curP = st.players[mySeat];
      if (curP.is_bot || !curP.player_id || curP.player_id === myPlayerId) {
        claimSeat(mySeat);
      }
    }
  }

  // 2. Sinkronisasi status kepemilikan kursi dengan server (cegah duplicate seat & race condition)
  if (st.players) {
    const myOwnedSeat = st.players.findIndex(p => !p.is_bot && p.player_id && p.player_id === myPlayerId);
    if (myOwnedSeat >= 0) {
      if (mySeat !== myOwnedSeat) {
        mySeat = myOwnedSeat;
        sessionStorage.setItem('remi_my_seat', String(myOwnedSeat));
        const url = new URL(window.location);
        url.searchParams.set('seat', myOwnedSeat);
        window.history.replaceState({}, '', url);
      }
    } else if (mySeat !== null && initialClaimDone) {
      const curP = st.players[mySeat];
      // Hanya lepas mySeat jika ada pemain manusia lain yang secara aktif memegang kursi ini
      if (curP && !curP.is_bot && curP.player_id && curP.player_id !== myPlayerId) {
        mySeat = null;
        sessionStorage.removeItem('remi_my_seat');
        const url = new URL(window.location);
        url.searchParams.delete('seat');
        window.history.replaceState({}, '', url);
      }
    }
  }

  const isLobby = (st.phase === 'LOBBY');
  const lobbyScreen = document.getElementById('lobby-screen');
  const tableScreen = document.getElementById('table');

  if (isLobby || (mySeat === null && !spectatorMode)) {
    if (lobbyScreen) lobbyScreen.style.display = 'flex';
    if (tableScreen) tableScreen.style.display = 'none';
    renderLobby(st);
    return;
  } else {
    if (lobbyScreen) lobbyScreen.style.display = 'none';
    if (tableScreen) tableScreen.style.display = 'flex';
  }

  const activeSeat = (mySeat !== null) ? mySeat : 0;
  const wRank = st.wildcard_rank || '-';
  const isPaused = Boolean(st.is_paused);
  const pauseSuffix = isPaused ? ' | ⏸️ DIJEDA' : '';

  // Cek siaran seruan CEKI dari server
  if (st.latest_ceki && st.latest_ceki.timestamp && st.latest_ceki.timestamp !== lastHandledCekiTime) {
    lastHandledCekiTime = st.latest_ceki.timestamp;
    if (st.latest_ceki.seat !== mySeat) {
      showCekiBubble(st.latest_ceki.seat);
      playCekiMediaAudio(st.latest_ceki.count || 1);
    }
  }

  document.getElementById('hdr-title').textContent =
    `REMI NUSANTARA 2D | Room: #${st.room_code} | Ronde: ${st.round_number} | WILD: JOKER + '${wRank}' | Target: ${st.target_score}${pauseSuffix}`;

  const btnPauseHdr = document.getElementById('btn-pause-header');
  const btnPauseAct = document.getElementById('btn-pause-action');
  const pauseModal = document.getElementById('pause-modal');
  if (btnPauseHdr) {
    btnPauseHdr.textContent = isPaused ? '▶️ RESUME (ESC)' : '⏸ PAUSE (ESC)';
    btnPauseHdr.style.background = isPaused ? '#16a34a' : 'rgba(2, 132, 199, 0.25)';
    btnPauseHdr.style.borderColor = isPaused ? '#4ade80' : '#38bdf8';
  }
  if (btnPauseAct) {
    btnPauseAct.textContent = isPaused ? '▶️ RESUME (ESC)' : '⏸ PAUSE (ESC)';
    btnPauseAct.style.background = isPaused ? '#16a34a' : '#0284c7';
    btnPauseAct.style.borderColor = isPaused ? '#4ade80' : '#38bdf8';
  }
  if (pauseModal) {
    pauseModal.style.display = isPaused ? 'flex' : 'none';
  }

  const bannerEl = document.getElementById('hdr-turn-banner');
  const isMyTurn = (mySeat !== null) && (st.current_turn_seat === mySeat) && (st.phase === 'TURN_DRAW' || st.phase === 'TURN_MELD_DISCARD');
  const p0 = (st.players && st.players[activeSeat]) ? st.players[activeSeat] : null;

  // Bersihkan pilihan kartu yang sudah tidak ada di tangan (agar tidak macet saat buang kartu)
  if (p0 && p0.hand) {
    const validHandIds = new Set(p0.hand.map(c => c.id));
    for (const cid of Array.from(selectedCards)) {
      if (!validHandIds.has(cid)) {
        selectedCards.delete(cid);
      }
    }
  } else {
    selectedCards.clear();
  }

  const canTutup = Boolean(p0 && p0.can_tutup_tangan);
  const tutupCardId = p0 ? (p0.tutup_discard_id || '') : '';
  const canCloseRound = Boolean(p0 && p0.can_close_round);
  const closeCardId = p0 ? (p0.close_discard_id || '') : '';

  const btnTutup = document.getElementById('btn-tutup-tangan');
  if (btnTutup) {
    if (canTutup && isMyTurn && st.phase === 'TURN_MELD_DISCARD') {
      btnTutup.classList.add('glow-tutup');
      btnTutup.textContent = '🏆 TUTUP TANGAN +250 (T)';
      btnTutup.title = `KARTU LENGKAP! Klik untuk Tutup Tangan (+250 Poin) dengan membuang ${tutupCardId}!`;
    } else if (canCloseRound && isMyTurn && st.phase === 'TURN_MELD_DISCARD') {
      btnTutup.classList.add('glow-tutup');
      btnTutup.textContent = `🏁 TUTUP KARTU (Buang ${closeCardId}) (T)`;
      btnTutup.title = `KARTU LENGKAP! Klik untuk Menutup Kartu (Tutup Biasa) dengan membuang ${closeCardId}!`;
    } else {
      btnTutup.classList.remove('glow-tutup');
      btnTutup.textContent = '🏆 TUTUP TANGAN +250 (T)';
      btnTutup.title = "Tutup Tangan langsung dari tangan (+250 Poin) (T)";
    }
  }

  if (bannerEl) {
    if (isPaused) {
      bannerEl.className = 'turn-banner turn-opp';
      bannerEl.textContent = '⏸️ PERMAINAN DIHENTIKAN SEMENTARA (PAUSED) - TEKAN ESC UNTUK LANJUT ⏸️';
    } else if (st.phase === 'LOBBY') {
      bannerEl.className = 'turn-banner turn-my';
      bannerEl.textContent = '🎲 RUANG LOBBY: PILIH KURSI ATAU ATUR ATURAN, LALU KLIK MULAI PERMAINAN 🎲';
    } else if (st.phase === 'MATCH_OVER' || st.phase === 'GAME_OVER') {
      bannerEl.className = 'turn-banner turn-my';
      bannerEl.textContent = '🏆 PERMAINAN SELESAI! JUARA TARGET SKOR TELAH DITENTUKAN! 🏆';
    } else if (st.phase === 'ROUND_OVER') {
      bannerEl.className = 'turn-banner turn-opp';
      bannerEl.textContent = `🏁 RONDE ${st.round_number} SELESAI! Mempersiapkan ronde berikutnya...`;
    } else if (isMyTurn) {
      bannerEl.className = 'turn-banner turn-my';
      if (st.phase === 'TURN_DRAW') {
        bannerEl.textContent = '★ GILIRAN ANDA! [TAHAP 1: AMBIL KARTU] -> Klik PAK KARTU atau Buangan #1-#7 ★';
      } else {
        if (canTutup) {
          bannerEl.textContent = `★ GILIRAN ANDA! KARTU JADI LENGKAP! KLIK \'TUTUP TANGAN +250 (T)\' (Buang ${tutupCardId})! ★`;
        } else if (canCloseRound) {
          bannerEl.textContent = `★ GILIRAN ANDA! BISA TUTUP KARTU! KLIK \'TUTUP KARTU (T)\' (Buang ${closeCardId})! ★`;
        } else {
          bannerEl.textContent = "★ GILIRAN ANDA! [TAHAP 2: SUSUN / BUANG] -> Klik \'AUTO TURUN (A)\', \'TURUNKAN (M)\', atau \'BUANG (B)\' ★";
        }
      }
    } else {
      bannerEl.className = 'turn-banner turn-opp';
      const currP = (st.players && st.players[st.current_turn_seat]) ? st.players[st.current_turn_seat] : null;
      const currName = currP ? currP.name : `Pemain ${st.current_turn_seat + 1}`;
      bannerEl.textContent = `Giliran ${currName} sedang berjalan... Harap tunggu.`;
    }
  }

  // Render Winner & Next Round Modal saat Ronde / Game Berakhir
  const winnerModal = document.getElementById('winner-modal');
  if (winnerModal) {
    if (st.phase === 'ROUND_OVER' || st.phase === 'MATCH_OVER' || st.phase === 'GAME_OVER') {
      winnerModal.style.display = 'flex';
      const isMatchOver = (st.phase === 'MATCH_OVER' || st.phase === 'GAME_OVER');
      
      const titleEl = document.getElementById('winner-title');
      const subEl = document.getElementById('winner-sub');
      const heroNameEl = document.getElementById('winner-hero-name');
      const heroScoreEl = document.getElementById('winner-hero-score');
      const tbodyEl = document.getElementById('winner-table-body');
      const countEl = document.getElementById('winner-countdown-sec');
      const countTextEl = document.getElementById('winner-countdown-text');
      const btnNext = document.getElementById('btn-next-round-action');

      if (titleEl) titleEl.textContent = isMatchOver ? '🏆 JUARA REMI NUSANTARA! 🏆' : `🏁 RONDE ${st.round_number} SELESAI!`;
      if (subEl) subEl.textContent = isMatchOver ? 'Target skor tercapai! Pertandingan berakhir.' : `Hasil perolehan poin ronde ke-${st.round_number}`;

      // Tentukan pemenang ronde / match
      let winnerPlayer = null;
      if (isMatchOver && st.match_winner_seat !== null && st.players[st.match_winner_seat]) {
        winnerPlayer = st.players[st.match_winner_seat];
      } else if (st.round_closer_seat !== null && st.players[st.round_closer_seat]) {
        winnerPlayer = st.players[st.round_closer_seat];
      } else {
        let best = -99999;
        (st.players || []).forEach(p => {
          if (p.last_round_score > best) {
            best = p.last_round_score;
            winnerPlayer = p;
          }
        });
      }

      if (heroNameEl && winnerPlayer) {
        const tutupTag = st.round_closed_by_tutup_tangan ? ' 🌟 TUTUP TANGAN (+250)' : ' 🏆 PENUTUP KARTU';
        heroNameEl.innerHTML = `👑 ${winnerPlayer.name} ${tutupTag}`;
      }
      if (heroScoreEl && winnerPlayer) {
        heroScoreEl.textContent = `+${winnerPlayer.last_round_score || 0} Poin Ronde Ini (Total: ${winnerPlayer.total_score || 0} Poin)`;
      }

      if (tbodyEl && st.players) {
        tbodyEl.innerHTML = st.players.map(p => {
          const isW = winnerPlayer && p.seat === winnerPlayer.seat;
          const rScore = p.last_round_score || 0;
          const scoreClass = rScore > 0 ? 'color:#4ade80;' : (rScore < 0 ? 'color:#f87171;' : 'color:#94a3b8;');
          const scoreText = rScore > 0 ? `+${rScore}` : `${rScore}`;
          const burnTag = p.burned_last_round ? ' <span style="color:#f87171;font-size:10px;">🔥TERBAKAR</span>' : '';
          const meldsHtml = renderPlayerMeldsHTML(p.melds);
          const handHtml = renderPlayerHandHTML(p.hand, isW);
          return `<tr class="${isW ? 'winner-row' : ''}">
            <td style="font-weight:700;">${isW ? '👑 ' : ''}${p.name}${burnTag}</td>
            <td>${meldsHtml}</td>
            <td>${handHtml}</td>
            <td style="text-align:center;font-weight:800;font-size:13px;${scoreClass}">${scoreText}</td>
            <td style="text-align:right;font-weight:900;font-size:13px;color:#facc15;">${p.total_score}</td>
          </tr>`;
        }).join('');
      }

      if (countTextEl) countTextEl.style.display = 'none';

      if (btnNext) {
        btnNext.textContent = isMatchOver ? '🔄 MAIN LAGI / RESET MATCH' : '▶️ LANJUT KE RONDE BERIKUTNYA';
      }
    } else {
      winnerModal.style.display = 'none';
    }
  }

  // Notifikasi teks atas (#hdr-status) disembunyikan sesuai permintaan untuk menjaga kerahasiaan kartu yang diambil pemain lain

  const deckCount = (st.deck_count !== undefined) ? st.deck_count : (st.draw_pile_count || 0);
  const discards = st.discards || st.discard_pile || [];
  const wildCard = st.wildcard_card || st.wildcard_indicator || null;
  const leaderSeat = (st.leader_seat !== undefined) ? st.leader_seat : (st.highest_score_seat || 0);

  // Render Pak Box
  document.getElementById('pak-count').textContent = `(${deckCount})`;
  const pakBox = document.getElementById('pak-box');
  if (pakBox) {
    if (isMyTurn && st.phase === 'TURN_DRAW') pakBox.classList.add('glow');
    else pakBox.classList.remove('glow');
  }

  // Render Wild Card Slot
  const wildSlot = document.getElementById('wild-card-slot');
  const wildTitleEl = document.getElementById('wild-title');
  if (wildSlot && wildCard) {
    wildSlot.innerHTML = renderCardHTML(wildCard);
    if (wildTitleEl) {
      const mult = st.wildcard_multiplier || 5;
      wildTitleEl.textContent = `BUKAAN WILD (x${mult})`;
    }
  }

  // Render Discard Bars (Row 1: 7 Kartu Buangan Aktif, Row 2: Kartu Buangan > 7 Terkubur)
  const discActiveCardsEl = document.getElementById('disc-active-cards');
  const discBuriedCardsEl = document.getElementById('disc-buried-cards');
  const discActivePill = document.getElementById('disc-active-pill');
  const discBuriedPill = document.getElementById('disc-buried-pill');

  if (discActiveCardsEl && discBuriedCardsEl) {
    const totalDisc = discards.length;
    const MAX_ACTIVE = 7;
    const startIdx = Math.max(0, totalDisc - MAX_ACTIVE);
    const buriedCount = startIdx;
    const activeCount = Math.min(totalDisc, MAX_ACTIVE);

    if (discActivePill) discActivePill.textContent = `${activeCount}/7 Aktif`;
    if (discBuriedPill) discBuriedPill.textContent = `${buriedCount} Terkubur`;

    const discSig = discards.map(c => c.id).join(',') + '|' + isMyTurn + '|' + st.phase;
    if (discSig !== lastDiscSig) {
      lastDiscSig = discSig;

      // 1. ROW 1: 7 KARTU BUANGAN (AKTIF)
      const top7Discards = discards.slice(startIdx);
      let activeHtml = '';
      for (let slot = 0; slot < MAX_ACTIVE; slot++) {
        if (slot < top7Discards.length) {
          const c = top7Discards[slot];
          const actualIndex = startIdx + slot;
          const revIdx = (top7Discards.length - 1) - slot; // 0 for newest (rightmost)
          const sliceToRight = top7Discards.slice(slot);
          const blockedByWild = sliceToRight.some(x => x.is_wild || x.rank === 'JOKER');
          const isWildSelf = Boolean(c.is_wild || c.rank === 'JOKER');
          const badgeText = isWildSelf ? 'WILD MATI' : (blockedByWild ? 'TERKUNCI' : `AMBIL #${revIdx + 1}`);
          const canClick = isMyTurn && (st.phase === 'TURN_DRAW') && !blockedByWild;

          activeHtml += renderCardHTML(c, {
            badge: badgeText,
            locked: blockedByWild,
            onclick: canClick ? `takeDiscard(${actualIndex})` : '',
            draggable: canClick,
            ondragstart: canClick ? `onDiscardDragStart(event, ${actualIndex})` : '',
            ondragend: `onDragEndClean(event)`,
            hint: blockedByWild
              ? `Tidak bisa diambil karena terhalang / merupakan Wild Card buangan`
              : `Ambil kartu #${revIdx + 1} (${c.rank}${c.suit}) & kartu sesudahnya (Otomatis Jadi)! Klik atau tarik ke meja Anda`
          }).replace('class="card', 'class="card active-discard');
        } else {
          // Static Slot Placeholder
          const slotNum = slot + 1;
          activeHtml += `<div class="disc-slot-placeholder" title="Slot Kartu Buangan #${slotNum} (Kosong)">
            <span class="disc-slot-num">SLOT #${slotNum}</span>
            <span class="disc-slot-icon">🂠</span>
          </div>`;
        }
      }
      discActiveCardsEl.innerHTML = activeHtml;

      // 2. ROW 2: KARTU BUANGAN LEBIH DARI 7 (TERKUBUR)
      if (buriedCount === 0) {
        discBuriedCardsEl.innerHTML = '<span class="buried-empty-hint">Belum ada kartu buangan lebih dari 7</span>';
      } else {
        const buriedCards = discards.slice(0, startIdx);
        let buriedHtml = buriedCards.map((c, bi) => {
          return renderCardHTML(c, {
            locked: true,
            hint: `Kartu buangan lama #${bi + 1} (${c.rank}${c.suit}) — Terkubur di bawah 7 kartu aktif`
          }).replace('class="card', 'class="card buried-grey');
        }).join('');
        discBuriedCardsEl.innerHTML = buriedHtml;
        requestAnimationFrame(() => {
          discBuriedCardsEl.scrollLeft = discBuriedCardsEl.scrollWidth;
        });
      }
    }
  }

    // Render Opponents (4 PLAYERS VERTICAL STACK ON LEFT COLUMN)
  const n = st.players.length;
  const isSpec = Boolean(mySeat === null || st.is_spectator || spectatorMode);
  const showOpponentFace = Boolean(isSpec || st.show_bot_hands);
  const zOpp1 = document.getElementById('zone-opp-1');
  const zOpp2 = document.getElementById('zone-opp-2');
  const zOpp3 = document.getElementById('zone-opp-3');

  if (n === 2) {
    if (zOpp1) zOpp1.style.display = 'flex';
    if (zOpp2) zOpp2.style.display = 'none';
    if (zOpp3) zOpp3.style.display = 'none';
    renderOpponentZone('opp-1', st.players[(activeSeat + 1) % n], st.current_turn_seat === (activeSeat + 1) % n, showOpponentFace, st.target_score, leaderSeat);
  } else if (n === 3) {
    if (zOpp1) zOpp1.style.display = 'flex';
    if (zOpp2) zOpp2.style.display = 'flex';
    if (zOpp3) zOpp3.style.display = 'none';
    renderOpponentZone('opp-1', st.players[(activeSeat + 1) % n], st.current_turn_seat === (activeSeat + 1) % n, showOpponentFace, st.target_score, leaderSeat);
    renderOpponentZone('opp-2', st.players[(activeSeat + 2) % n], st.current_turn_seat === (activeSeat + 2) % n, showOpponentFace, st.target_score, leaderSeat);
  } else {
    // 4 Players: 3 Opponents stacked vertically above player!
    if (zOpp1) zOpp1.style.display = 'flex';
    if (zOpp2) zOpp2.style.display = 'flex';
    if (zOpp3) zOpp3.style.display = 'flex';
    renderOpponentZone('opp-1', st.players[(activeSeat + 1) % n], st.current_turn_seat === (activeSeat + 1) % n, showOpponentFace, st.target_score, leaderSeat);
    renderOpponentZone('opp-2', st.players[(activeSeat + 2) % n], st.current_turn_seat === (activeSeat + 2) % n, showOpponentFace, st.target_score, leaderSeat);
    renderOpponentZone('opp-3', st.players[(activeSeat + 3) % n], st.current_turn_seat === (activeSeat + 3) % n, showOpponentFace, st.target_score, leaderSeat);
  }

  // Render Player Zone
  if (p0) {
    const isLeader = (leaderSeat !== null && leaderSeat !== undefined && activeSeat === leaderSeat && (st.round_number > 1 || p0.total_score > 0));
    const leaderTag = isLeader ? ' [👑 SKOR TERTINGGI]' : '';
    const burnTag = p0.burned_last_round ? ' [TERBAKAR!]' : '';
    const cekiTag = p0.is_ceki ? ' <span class="badge-ceki-glow">🔥 CEKI!</span>' : '';
    const specBanner = isSpec ? ` <span class="spectator-banner">👁️ PENONTON (DELAY 1 PUTARAN • SEMUA KARTU TERBUKA)</span>` : '';
    const seatLabel = !isSpec ? `Kursi ${activeSeat + 1}` : `Kursi ${activeSeat + 1} (Mode Penonton)`;
    const editNameSpan = !isSpec ? ` <span style="font-size:10px;color:#38bdf8;cursor:pointer;text-decoration:underline;" onclick="changePlayerNamePrompt()">✎ Ganti Nama</span>` : '';
    document.getElementById('my-info').innerHTML =
      `${seatLabel} | ${p0.name}${cekiTag}${leaderTag}${burnTag}${specBanner} | Skor: ${p0.total_score} / ${st.target_score} (${p0.last_round_score >= 0 ? '+' : ''}${p0.last_round_score})${editNameSpan}`;

    const actBar = document.getElementById('action-bar');
    if (actBar) {
      actBar.style.display = 'flex';
    }

    const myTurnBadge = document.getElementById('my-turn-badge');
    if (myTurnBadge) myTurnBadge.style.display = isMyTurn ? 'inline-block' : 'none';

    const seriBadge = document.getElementById('my-seri-badge');
    if (seriBadge) {
      if (p0.has_seri) {
        seriBadge.textContent = 'SERI WAJIB AMAN ✓';
        seriBadge.style.color = '#4ade80';
        seriBadge.style.background = 'rgba(21, 128, 61, 0.35)';
      } else {
        seriBadge.textContent = 'BELUM ADA SERI MIN 3 (AWAS TERBAKAR!)';
        seriBadge.style.color = '#f87171';
        seriBadge.style.background = 'rgba(185, 28, 28, 0.35)';
      }
    }

    // Render Player Melds (Divided between Left Box and Right Box)
    const myMeldsLeftEl = document.getElementById('my-melds-left-cards');
    const myMeldsRightEl = document.getElementById('my-melds-right-cards');
    const oldMyMeldsEl = document.getElementById('my-melds');

    const pMelds = p0.melds || [];
    if (oldMyMeldsEl) oldMyMeldsEl.innerHTML = renderMeldsHTML(pMelds, false);

    if (myMeldsLeftEl && myMeldsRightEl) {
      if (pMelds.length === 0) {
        myMeldsLeftEl.innerHTML = '<div class="meld-empty-hint">Belum ada seri</div>';
        myMeldsRightEl.innerHTML = '<div class="meld-empty-hint">Belum ada set</div>';
      } else {
        let leftMelds = [];
        let rightMelds = [];

        pMelds.forEach(m => {
          // Detect if Seri (same suit) or Set (different suit / same rank)
          const nonWilds = m.filter(c => !c.is_wild && c.rank !== 'JOKER');
          const isSeri = (nonWilds.length <= 1) || (new Set(nonWilds.map(c => c.suit)).size === 1);
          if (isSeri) {
            if (leftMelds.length === 0) leftMelds.push(m);
            else rightMelds.push(m);
          } else {
            rightMelds.push(m);
          }
        });

        // Balance if needed
        if (leftMelds.length === 0 && rightMelds.length > 1) {
          leftMelds.push(rightMelds.shift());
        } else if (rightMelds.length === 0 && leftMelds.length > 1) {
          rightMelds.push(leftMelds.pop());
        }

        myMeldsLeftEl.innerHTML = leftMelds.length > 0
          ? renderMeldsHTML(leftMelds, false)
          : '<div class="meld-empty-hint">Belum ada seri</div>';
        myMeldsRightEl.innerHTML = rightMelds.length > 0
          ? renderMeldsHTML(rightMelds, false)
          : '<div class="meld-empty-hint">Belum ada set</div>';
      }
    }

        // Indikator Giliran Pemain & Step Badge
    const zoneBottom = document.getElementById('zone-bottom');
    if (zoneBottom) {
      if (isMyTurn) zoneBottom.classList.add('my-turn-active');
      else zoneBottom.classList.remove('my-turn-active');
    }

    const stepBadge = document.getElementById('my-step-badge');
    if (stepBadge) {
      if (isMyTurn) {
        stepBadge.style.display = 'inline-block';
        if (st.phase === 'TURN_DRAW') {
          stepBadge.style.background = 'linear-gradient(90deg, #2563eb, #1d4ed8)';
          stepBadge.style.color = '#fff';
          stepBadge.style.boxShadow = '0 0 12px rgba(37,99,235,0.7)';
          stepBadge.textContent = '👉 TAHAP 1: AMBIL KARTU (PAK / BUANGAN)';
        } else {
          stepBadge.style.background = 'linear-gradient(90deg, #ea580c, #c2410c)';
          stepBadge.style.color = '#fff';
          stepBadge.style.boxShadow = '0 0 12px rgba(234,88,12,0.7)';
          stepBadge.textContent = '👉 TAHAP 2: SUSUN & BUANG 1 KARTU';
        }
      } else {
        stepBadge.style.display = 'none';
      }
    }

    // Render 50% Overlapping Hand with Caching (Zero Hover Jitter & HTML5 Drag)
    const myHandEl = document.getElementById('my-hand');
    if (myHandEl) {
      if (Date.now() - lastLocalReorderTime < 800 && p0.hand && latestState && latestState.players && latestState.players[mySeat]) {
        const localHand = latestState.players[mySeat].hand || [];
        const serverHandIds = new Set((p0.hand || []).map(c => c.id));
        if (localHand.length === p0.hand.length && localHand.every(c => serverHandIds.has(c.id))) {
          p0.hand = [...localHand];
        }
      }
      let isNewRound = false;
      if (st.round_number && st.round_number !== lastAnimatedRound && (st.phase === 'TURN_DRAW' || st.phase === 'TURN_MELD_DISCARD')) {
        lastAnimatedRound = st.round_number;
        isNewRound = true;
        lastHandSig = '';
      }
      const handIds = (p0.hand || []).map(c => c.id).join(',');
      const selIds = Array.from(selectedCards).sort().join(',');
      const handSig = `${handIds}|${selIds}|${isMyTurn}|${st.phase}|${st.forbidden_discard_card_id || ''}|round_${st.round_number}`;
      
      if (handSig !== lastHandSig) {
        lastHandSig = handSig;
        myHandEl.innerHTML = (p0.hand || []).map((c, i) => {
          const isSel = selectedCards.has(c.id);
          const isForbiddenDiscard = Boolean(st.forbidden_discard_card_id && st.forbidden_discard_card_id === c.id);
          const cardHtml = renderCardHTML(c, {
            selected: isSel
          });
          const slideCtrlsHtml = isSel ? `
            <div class="slot-slide-ctrls">
              <button class="slot-arrow-btn" onclick="event.stopPropagation(); slideCardById('${c.id}', -1);" title="Geser Kiri (Shift Left)">◀</button>
              <button class="slot-arrow-btn" onclick="event.stopPropagation(); slideCardById('${c.id}', 1);" title="Geser Kanan (Shift Right)">▶</button>
            </div>` : '';
          const animClass = isNewRound ? 'deal-anim' : '';
          const animDelayStyle = isNewRound ? `style="animation-delay: ${(i * 0.06).toFixed(2)}s;"` : '';
          return `<div class="hand-card-slot ${isSel ? 'selected-slot' : ''} ${animClass}"
                       ${animDelayStyle}
                       data-card-id="${c.id}"
                       draggable="true"
                       ondragstart="onHandCardDragStart(event, '${c.id}')"
                       ondragend="onDragEndClean(event)"
                       ondragover="onHandSlotDragOver(event, '${c.id}')"
                       ondragleave="onHandSlotDragLeave(event, '${c.id}')"
                       ondrop="onHandSlotDrop(event, '${c.id}')"
                       ontouchstart="onHandTouchStart(event, '${c.id}')"
                       ontouchmove="onHandTouchMove(event, '${c.id}')"
                       ontouchend="onHandTouchEnd(event, '${c.id}')"
                       onclick="toggleCard('${c.id}')"
                       oncontextmenu="quickDiscard('${c.id}'); return false;"
                       title="${isForbiddenDiscard ? 'Kartu baru diambil dari buangan teratas (tidak boleh langsung dibuang di giliran ini)' : 'Klik untuk pilih; Tarik / Tombol Panah untuk Geser Posisi; Klik Kanan / Tarik ke Buangan untuk Buang (B)'}">
            ${slideCtrlsHtml}
            ${cardHtml}
          </div>`;
        }).join('');
      }
    }
  }

  // Update Status & Validasi Tombol CEKI
  const btnCeki = document.getElementById('btn-ceki');
  if (btnCeki) {
    const curP0 = (latestState && latestState.players && mySeat !== null) ? latestState.players[mySeat] : (latestState && latestState.players ? latestState.players[0] : null);
    const canCeki = Boolean(curP0 && curP0.is_ceki);
    if (!btnCeki.classList.contains('btn-cooldown')) {
      btnCeki.disabled = !canCeki;
      if (canCeki) {
        btnCeki.title = "Serukan CEKI! (C) - Sisa 1 kartu buangan atau siap menutup tangan";
        btnCeki.style.opacity = '1';
        btnCeki.style.cursor = 'pointer';
        btnCeki.classList.add('btn-ceki-ready');
      } else {
        btnCeki.title = "Tombol CEKI hanya aktif jika kartu buangan sisa satu atau akan menutup tangan!";
        btnCeki.style.opacity = '0.4';
        btnCeki.style.cursor = 'not-allowed';
        btnCeki.classList.remove('btn-ceki-ready');
      }
    }
    const isNowCeki = Boolean(curP0 && curP0.is_ceki);
    if (!isNowCeki && wasCeki) {
      myCekiClickCount = 0;
    }
    wasCeki = isNowCeki;
  }
}

function toggleCard(cardId) {
  if (selectedCards.has(cardId)) selectedCards.delete(cardId);
  else selectedCards.add(cardId);
  lastHandSig = '';
  if (latestState) updateUI(latestState);
}

function quickDiscard(cardId) {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
  if (!isMyTurn) return;
  selectedCards.clear();
  lastHandSig = '';
  lastDiscSig = '';
  sendAction('DISCARD', { card_id: cardId });
}

function meldSelected() {
  if (!selectedCards.size) {
    alert("Pilih minimal 1 kartu (untuk sambung ke meja) atau minimal 3 kartu di tangan untuk diturunkan!");
    return;
  }
  const cids = Array.from(selectedCards);
  selectedCards.clear();
  lastHandSig = '';
  sendAction('MELD_HAND', { card_ids: cids });
}

function discardSelected() {
  if (!latestState) return;
  const p0 = latestState.players ? latestState.players[mySeat] : null;
  let cid = null;
  if (selectedCards.size === 1) {
    cid = Array.from(selectedCards)[0];
  } else if (selectedCards.size === 0 && p0 && p0.hand && p0.hand.length === 1) {
    cid = p0.hand[0].id;
  } else if (selectedCards.size === 0 && p0 && p0.can_close_round && p0.close_discard_id) {
    cid = p0.close_discard_id;
  } else {
    alert("Pilih tepat 1 kartu di tangan untuk dibuang (atau klik kanan pada kartu yang ingin dibuang)!");
    return;
  }
  selectedCards.clear();
  lastHandSig = '';
  lastDiscSig = '';
  sendAction('DISCARD', { card_id: cid });
}

function declareTutupTangan() {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
  if (!isMyTurn) {
    alert("Hanya bisa menutup kartu saat giliran Anda di tahap susun/buang!");
    return;
  }
  const p0 = latestState.players[mySeat];
  if (!p0 || (!p0.can_tutup_tangan && !p0.can_close_round)) {
    alert("Kartu Anda belum memenuhi syarat menutup ronde! Semua sisa kartu di tangan harus bisa disusun menjadi Seri/Kembar valid (dengan sisa 1 kartu buang).");
    return;
  }
  const chosenId = (selectedCards.size === 1) ? Array.from(selectedCards)[0] : (p0.tutup_discard_id || p0.close_discard_id || null);
  selectedCards.clear();
  lastHandSig = '';
  lastDiscSig = '';
  sendAction('TUTUP_TANGAN', { card_id: chosenId });
}

function takeDiscard(idx) {
  const explicitIds = (selectedCards.size >= 2) ? Array.from(selectedCards) : null;
  selectedCards.clear();
  lastHandSig = '';
  lastDiscSig = '';
  sendAction('TAKE_DISCARD', { index: idx, discard_index: idx, card_ids: explicitIds });
}

async function sendAction(action, data = {}) {
  try {
    if (action === 'DRAW_DECK' || action === 'AUTO_MELD') {
      selectedCards.clear();
      lastHandSig = '';
      lastDiscSig = '';
    }
    data.action = action;
    data.seat = (mySeat !== null) ? mySeat : 0;
    data.player_id = myPlayerId;
    const res = await fetch(`/api/action?act=${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const st = await res.json();
    if (st && st.state) {
      lastStateVersion = st.state.state_version || 0;
      lastStateSeat = mySeat;
      updateUI(st.state);
    }
    wakeUpPollingFast();
    return st;
  } catch (e) {
    console.error("Action error:", e);
  }
}

function togglePause() {
  sendAction('TOGGLE_PAUSE');
}

// Fitur Tombol & Bubble CEKI (Cooldown 2 Detik & Audio Berantai)
let lastCekiTime = 0;
let lastHandledCekiTime = 0;
let myCekiClickCount = 0;
let wasCeki = false;

function triggerCeki() {
  const curP0 = (latestState && latestState.players && mySeat !== null) ? latestState.players[mySeat] : (latestState && latestState.players ? latestState.players[0] : null);
  if (curP0 && !curP0.is_ceki) {
    alert("Tombol CEKI hanya bisa diklik jika kartu Anda sisa 1 buangan atau akan menutup tangan!");
    return;
  }
  const now = Date.now();
  if (now - lastCekiTime < 2000) return;
  lastCekiTime = now;

  myCekiClickCount++;
  const activeCount = myCekiClickCount;

  const btn = document.getElementById('btn-ceki');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-cooldown');
    const start = Date.now();
    const interval = setInterval(() => {
      const remaining = Math.max(0, (2000 - (Date.now() - start)) / 1000);
      if (remaining <= 0) {
        clearInterval(interval);
        const checkP0 = (latestState && latestState.players && mySeat !== null) ? latestState.players[mySeat] : null;
        btn.disabled = !Boolean(checkP0 && checkP0.is_ceki);
        btn.classList.remove('btn-cooldown');
        btn.innerHTML = '📢 CEKI (C)';
      } else {
        btn.innerHTML = `⏳ CEKI (${remaining.toFixed(1)}s)`;
      }
    }, 100);
  }

  playCekiMediaAudio(activeCount);
  showCekiBubble(mySeat !== null ? mySeat : 0);
  sendAction('CEKI', { ceki_count: activeCount });
}

// Preload audio CEKI sekali saja (tidak membuat request baru setiap klik)
const CEKI_AUDIO_SRC = ['/audio/main_edit.mp4', '/audio/main_edit_1.mp4'];
const cekiAudioPool = CEKI_AUDIO_SRC.map(src => {
  try {
    const a = new Audio(src);
    a.preload = 'auto';
    a.volume = 1.0;
    a.load();
    return a;
  } catch (e) { return null; }
});

function playCekiMediaAudio(count) {
  const idx = (count <= 1) ? 0 : 1;
  const base = cekiAudioPool[idx];
  try {
    if (!base) { playCekiAudio(); return; }
    base.pause();
    base.currentTime = 0;
    const p = base.play();
    if (p && p.catch) {
      p.catch(err => {
        console.warn('CEKI audio gagal diputar:', err);
        playCekiAudio();
      });
    }
  } catch (e) {
    playCekiAudio();
  }
}

function getZoneElementForSeat(seat) {
  const active = (mySeat !== null) ? mySeat : 0;
  if (seat === active) {
    return document.getElementById('zone-bottom');
  }
  const n = (latestState && latestState.players) ? latestState.players.length : 4;
  if (n === 2) {
    if (seat === (active + 1) % n) return document.getElementById('zone-opp-1');
  } else if (n === 3) {
    if (seat === (active + 1) % n) return document.getElementById('zone-opp-1');
    if (seat === (active + 2) % n) return document.getElementById('zone-opp-2');
  } else {
    if (seat === (active + 1) % n) return document.getElementById('zone-opp-1');
    if (seat === (active + 2) % n) return document.getElementById('zone-opp-2');
    if (seat === (active + 3) % n) return document.getElementById('zone-opp-3');
  }
  return document.getElementById('zone-bottom');
}

function showCekiBubble(seat) {
  const zoneEl = getZoneElementForSeat(seat);
  if (!zoneEl) return;

  const existing = zoneEl.querySelector('.ceki-bubble');
  if (existing) existing.remove();

  const bubble = document.createElement('div');
  bubble.className = 'ceki-bubble';
  bubble.textContent = '📢 CEKI!';
  zoneEl.appendChild(bubble);

  playCekiAudio();

  setTimeout(() => {
    bubble.remove();
  }, 2200);
}

function playCekiAudio() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(540, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
    osc.frequency.exponentialRampToValueAtTime(1175, ctx.currentTime + 0.22);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.32);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.32);
  } catch (e) {}
}

// Drag & Drop (dilengkapi proteksi anti-stuck, reorder manual, & mobile touch gestures)
let lastLocalReorderTime = 0;
let touchDragState = null;

function reorderHandLocally(sourceCardId, targetCardId) {
  if (!latestState || !latestState.players || !latestState.players[mySeat]) return;
  const hand = latestState.players[mySeat].hand || [];
  const srcIdx = hand.findIndex(c => c.id === sourceCardId);
  const tgtIdx = hand.findIndex(c => c.id === targetCardId);
  if (srcIdx === -1 || tgtIdx === -1 || srcIdx === tgtIdx) return;

  lastLocalReorderTime = Date.now();
  const [removed] = hand.splice(srcIdx, 1);
  hand.splice(tgtIdx, 0, removed);
  lastHandSig = '';
  updateUI(latestState);
  sendAction('REORDER_HAND', { source_card_id: sourceCardId, target_card_id: targetCardId });
}

function slideSelectedCard(dir) {
  if (!latestState || !latestState.players || !latestState.players[mySeat]) return;
  const hand = latestState.players[mySeat].hand || [];
  if (hand.length <= 1) return;

  let targetCid = null;
  for (const c of hand) {
    if (selectedCards.has(c.id)) {
      targetCid = c.id;
      break;
    }
  }
  if (!targetCid) {
    targetCid = hand[hand.length - 1].id;
    selectedCards.add(targetCid);
  }
  slideCardById(targetCid, dir);
}

function slideCardById(cardId, dir) {
  if (!latestState || !latestState.players || !latestState.players[mySeat]) return;
  const hand = latestState.players[mySeat].hand || [];
  const idx = hand.findIndex(c => c.id === cardId);
  if (idx === -1) return;
  const targetIdx = idx + dir;
  if (targetIdx < 0 || targetIdx >= hand.length) return;

  const targetCardId = hand[targetIdx].id;
  reorderHandLocally(cardId, targetCardId);
}

function onDragEndClean(e) {
  const dragInfo = currentDrag;
  currentDrag = null;
  const zb = document.getElementById('zone-bottom');
  if (zb) { zb.classList.remove('drop-target-active'); zb.style.borderColor = ''; }
  const dr = document.getElementById('discard-rail');
  if (dr) { dr.classList.remove('drop-target-discard'); dr.style.borderColor = ''; }

  document.querySelectorAll('.dragging-slot').forEach(el => el.classList.remove('dragging-slot'));
  document.querySelectorAll('.drop-target-slot').forEach(el => el.classList.remove('drop-target-slot'));

  // Jika pengguna bermaksud klik namun mouse bergeser sedikit (< 35px) sehingga browser memicu dragstart:
  if (dragInfo && !dragInfo.handled && e) {
    const dx = (e.clientX || 0) - (dragInfo.startX || 0);
    const dy = (e.clientY || 0) - (dragInfo.startY || 0);
    const dist = Math.hypot(dx, dy);
    if (dist < 35) {
      if (dragInfo.type === 'PAK') {
        sendAction('DRAW_DECK');
      } else if (dragInfo.type === 'DISCARD') {
        takeDiscard(dragInfo.idx);
      } else if (dragInfo.type === 'HAND') {
        toggleCard(dragInfo.cardId);
      }
    }
  }
}

window.addEventListener('dragend', onDragEndClean);
window.addEventListener('mouseup', () => { currentDrag = null; });

function onPakDragStart(e) {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_DRAW');
  if (!isMyTurn) { e.preventDefault(); return; }
  currentDrag = { type: 'PAK', startX: e.clientX || 0, startY: e.clientY || 0, handled: false };
  if (e.dataTransfer) {
    e.dataTransfer.setData('text/plain', 'PAK');
    e.dataTransfer.effectAllowed = 'copy';
  }
  const zb = document.getElementById('zone-bottom');
  if (zb) zb.classList.add('drop-target-active');
}

function onDiscardDragStart(e, idx) {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_DRAW');
  if (!isMyTurn) { e.preventDefault(); return; }
  currentDrag = { type: 'DISCARD', idx: idx, startX: e.clientX || 0, startY: e.clientY || 0, handled: false };
  if (e.dataTransfer) {
    e.dataTransfer.setData('text/plain', 'DISCARD_' + idx);
    e.dataTransfer.effectAllowed = 'copy';
  }
  const zb = document.getElementById('zone-bottom');
  if (zb) zb.classList.add('drop-target-active');
}

function onHandCardDragStart(e, cardId) {
  if (!latestState) return;
  currentDrag = { type: 'HAND', cardId: cardId, startX: e.clientX || 0, startY: e.clientY || 0, handled: false };
  if (e.dataTransfer) {
    e.dataTransfer.setData('text/plain', cardId);
    e.dataTransfer.effectAllowed = 'move';
  }
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
  if (isMyTurn) {
    const dr = document.getElementById('discard-rail');
    if (dr) dr.classList.add('drop-target-discard');
  }
  const slot = document.querySelector(`.hand-card-slot[data-card-id="${cardId}"]`);
  if (slot) slot.classList.add('dragging-slot');
}

function onHandSlotDragOver(e, targetCardId) {
  if (currentDrag && currentDrag.type === 'HAND' && currentDrag.cardId !== targetCardId) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const slot = document.querySelector(`.hand-card-slot[data-card-id="${targetCardId}"]`);
    if (slot && !slot.classList.contains('drop-target-slot')) {
      document.querySelectorAll('.drop-target-slot').forEach(el => el.classList.remove('drop-target-slot'));
      slot.classList.add('drop-target-slot');
    }
  }
}

function onHandSlotDragLeave(e, targetCardId) {
  const slot = document.querySelector(`.hand-card-slot[data-card-id="${targetCardId}"]`);
  if (slot) slot.classList.remove('drop-target-slot');
}

function onHandSlotDrop(e, targetCardId) {
  if (currentDrag && currentDrag.type === 'HAND' && currentDrag.cardId !== targetCardId) {
    e.preventDefault();
    e.stopPropagation();
    const srcId = currentDrag.cardId;
    currentDrag.handled = true;
    onDragEndClean(e);
    reorderHandLocally(srcId, targetCardId);
  }
}

function onDiscardDragOver(e) {
  if (currentDrag && currentDrag.type === 'HAND') {
    const isMyTurn = latestState && (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
    if (isMyTurn) {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      const dr = document.getElementById('discard-rail');
      if (dr) dr.classList.add('drop-target-discard');
    }
  }
}

function onDiscardDragLeave(e) {
  // Biarkan visual feedback tetap aktif sampai drop atau dragend
}

function onDiscardDrop(e) {
  e.preventDefault();
  const dragInfo = currentDrag;
  if (dragInfo) dragInfo.handled = true;
  onDragEndClean(e);
  if (dragInfo && dragInfo.type === 'HAND') {
    const isMyTurn = latestState && (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
    if (isMyTurn) {
      const cid = dragInfo.cardId;
      selectedCards.clear();
      lastHandSig = '';
      lastDiscSig = '';
      sendAction('DISCARD', { card_id: cid });
    }
  }
}

// Touch Event Handlers for Mobile (Drag/Swipe Cards on Touchscreen)
function onHandTouchStart(e, cardId) {
  if (!e.touches || e.touches.length === 0) return;
  const t = e.touches[0];
  touchDragState = {
    cardId: cardId,
    startX: t.clientX,
    startY: t.clientY,
    moved: false
  };
}

function onHandTouchMove(e, cardId) {
  if (!touchDragState || !e.touches || e.touches.length === 0) return;
  const t = e.touches[0];
  const dx = t.clientX - touchDragState.startX;
  const dy = t.clientY - touchDragState.startY;
  if (Math.hypot(dx, dy) > 12) {
    touchDragState.moved = true;
    const elem = document.elementFromPoint(t.clientX, t.clientY);
    const targetSlot = elem ? elem.closest('.hand-card-slot') : null;
    document.querySelectorAll('.drop-target-slot').forEach(el => el.classList.remove('drop-target-slot'));
    if (targetSlot && targetSlot.getAttribute('data-card-id') !== touchDragState.cardId) {
      targetSlot.classList.add('drop-target-slot');
    }
  }
}

function onHandTouchEnd(e, cardId) {
  if (!touchDragState) return;
  const st = touchDragState;
  touchDragState = null;
  document.querySelectorAll('.drop-target-slot').forEach(el => el.classList.remove('drop-target-slot'));

  if (st.moved && e.changedTouches && e.changedTouches.length > 0) {
    const t = e.changedTouches[0];
    const elem = document.elementFromPoint(t.clientX, t.clientY);

    const discardRail = elem ? elem.closest('#discard-rail') : null;
    const isMyTurn = latestState && (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
    if (discardRail && isMyTurn) {
      selectedCards.clear();
      lastHandSig = '';
      lastDiscSig = '';
      sendAction('DISCARD', { card_id: st.cardId });
      return;
    }

    const targetSlot = elem ? elem.closest('.hand-card-slot') : null;
    if (targetSlot) {
      const targetCid = targetSlot.getAttribute('data-card-id');
      if (targetCid && targetCid !== st.cardId) {
        reorderHandLocally(st.cardId, targetCid);
      }
    }
  }
}

function enableDragScroll(el) {
  if (!el) return;
  let isDown = false;
  let startX = 0;
  let scrollLeft = 0;
  el.addEventListener('mousedown', (e) => {
    if (e.target.closest('.card') || e.target.closest('.slot-slide-ctrls')) return;
    isDown = true;
    startX = e.pageX - el.offsetLeft;
    scrollLeft = el.scrollLeft;
  });
  window.addEventListener('mouseup', () => { isDown = false; });
  el.addEventListener('mousemove', (e) => {
    if (!isDown) return;
    e.preventDefault();
    const x = e.pageX - el.offsetLeft;
    const walk = (x - startX) * 1.5;
    el.scrollLeft = scrollLeft - walk;
  });
}
window.addEventListener('DOMContentLoaded', () => {
  enableDragScroll(document.getElementById('disc-active-cards'));
enableDragScroll(document.getElementById('disc-buried-cards'));
  enableDragScroll(document.getElementById('my-hand'));
});
enableDragScroll(document.getElementById('disc-active-cards'));
enableDragScroll(document.getElementById('disc-buried-cards'));
enableDragScroll(document.getElementById('my-hand'));

function onHandDragOver(e) {
  if (currentDrag && (currentDrag.type === 'PAK' || currentDrag.type === 'DISCARD')) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    const zb = document.getElementById('zone-bottom');
    if (zb) zb.classList.add('drop-target-active');
  }
}

function onHandDragLeave(e) {
  // Biarkan visual feedback tetap aktif sampai drop atau dragend
}

function onHandDrop(e) {
  e.preventDefault();
  const dragInfo = currentDrag;
  if (dragInfo) dragInfo.handled = true;
  onDragEndClean(e);
  if (dragInfo && dragInfo.type === 'PAK') {
    lastHandSig = '';
    sendAction('DRAW_DECK');
  } else if (dragInfo && dragInfo.type === 'DISCARD') {
    const idx = dragInfo.idx;
    lastHandSig = '';
    takeDiscard(idx);
  }
}

// Invite Modal
function openInviteModal() {
  document.getElementById('invite-modal').style.display = 'flex';
  const host = window.location.host;
  const proto = window.location.protocol;
  document.getElementById('invite-host-ip').value = `${proto}//${host}/?seat=1`;
  if (!latestState) return;
  const slotsDiv = document.getElementById('invite-slots-list');
  slotsDiv.innerHTML = latestState.players.map((p, idx) => {
    if (idx === mySeat) {
      return `<div style="background:#022c16;padding:6px 10px;border-radius:6px;border:1px solid #16a34a;display:flex;justify-content:space-between;align-items:center;">
        <span><strong>Kursi ${idx + 1}:</strong> ${p.name} (Anda)</span>
        <span style="color:#4ade80;font-size:11px;">Aktif</span>
      </div>`;
    }
    const joinUrl = `${proto}//${host}/?seat=${idx}`;
    return `<div style="background:#1e293b;padding:6px 10px;border-radius:6px;border:1px solid #334155;display:flex;justify-content:space-between;align-items:center;">
      <span><strong>Kursi ${idx + 1}:</strong> ${p.name} ${p.is_bot ? '<span style="color:#94a3b8;">(Bot)</span>' : '<span style="color:#38bdf8;">(Manusia)</span>'}</span>
      <button onclick="navigator.clipboard.writeText('${joinUrl}'); alert('Link Kursi ${idx + 1} disalin!');" class="pill-btn" style="padding:3px 8px;font-size:11px;">Salin Link</button>
    </div>`;
  }).join('');
}
function closeInviteModal() {
  document.getElementById('invite-modal').style.display = 'none';
}

// Dashboard Modal
function openDashboard() {
  document.getElementById('dashboard-modal').style.display = 'flex';
  if (latestState) {
    const p0 = latestState.players[mySeat];
    if (p0) document.getElementById('cfg-player-name').value = p0.name;
    selectConfig('players', latestState.players.length);
    selectConfig('score', latestState.target_score);
    selectConfig('timer', latestState.turn_timer_sec);
  }
}
function closeDashboard() {
  document.getElementById('dashboard-modal').style.display = 'none';
}

function selectConfig(type, val) {
  currentConfig[type] = val;
  let containerId = '';
  if (type === 'players') containerId = 'player-pills';
  else if (type === 'score') {
    containerId = 'score-pills';
    document.getElementById('score-badge-active').textContent = `${val} Poin`;
  } else if (type === 'timer') {
    containerId = 'timer-pills';
    document.getElementById('timer-badge-active').textContent = val === 0 ? 'Unlimited' : `${val}s`;
  } else if (type === 'botDelay') {
    containerId = 'bot-pills';
  }
  if (containerId) {
    const btns = document.querySelectorAll(`#${containerId} .pill-btn`);
    btns.forEach(b => {
      if (b.getAttribute('onclick').includes(String(val))) b.classList.add('active');
      else b.classList.remove('active');
    });
  }
}

async function saveSettingsOnly() {
  const name = document.getElementById('cfg-player-name').value.trim() || 'Player 1';
  currentConfig.playerName = name;
  try {
    await sendAction('CONFIGURE_ONLY', {
      turn_timer_sec: currentConfig.timer,
      target_score: currentConfig.score,
      num_players: currentConfig.players,
      player_name: currentConfig.playerName,
      bot_delay_sec: currentConfig.botDelay
    });
    localStorage.setItem('remi_player_name', name);
    closeDashboard();
  } catch (e) {
    console.error(e);
  }
}

async function saveAndStartGame() {
  const name = document.getElementById('cfg-player-name').value.trim() || 'Player 1';
  currentConfig.playerName = name;
  try {
    await sendAction('CONFIGURE_AND_START', {
      turn_timer_sec: currentConfig.timer,
      target_score: currentConfig.score,
      num_players: currentConfig.players,
      player_name: currentConfig.playerName,
      bot_delay_sec: currentConfig.botDelay
    });
    localStorage.setItem('remi_player_name', name);
    closeDashboard();
  } catch (e) {
    console.error(e);
  }
}

function changePlayerNamePrompt() {
  const current = (latestState && mySeat !== null && latestState.players[mySeat]) ? latestState.players[mySeat].name : 'Player 1';
  const newName = prompt("Ganti nama Anda:", current);
  if (newName && newName.trim()) {
    const clean = newName.trim();
    localStorage.setItem('remi_player_name', clean);
    if (mySeat !== null) {
      sendAction('CHANGE_NAME', { seat: mySeat, name: clean });
    }
  }
}

function showToast(msg) {
  const t = document.getElementById('toast-notif');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => {
    t.classList.remove('show');
  }, 2800);
}

function copyLobbyLink() {
  const host = window.location.host;
  const proto = window.location.protocol;
  const link = `${proto}//${host}/`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => {
      showToast("Link Lobby berhasil disalin! Bagikan ke teman.");
    }).catch(() => {
      prompt("Salin Link Lobby ini:", link);
    });
  } else {
    prompt("Salin Link Lobby ini:", link);
  }
}

function copySeatDirectLink(idx) {
  const host = window.location.host;
  const proto = window.location.protocol;
  const link = `${proto}//${host}/?seat=${idx}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(() => {
      showToast(`Link Kursi ${idx + 1} berhasil disalin!`);
    }).catch(() => {
      prompt(`Salin Link Kursi ${idx + 1}:`, link);
    });
  } else {
    prompt(`Salin Link Kursi ${idx + 1}:`, link);
  }
}

function onLobbyNameChange(val) {
  const clean = (val || '').trim();
  if (!clean) return;
  localStorage.setItem('remi_player_name', clean);
  if (mySeat !== null) {
    sendAction('CHANGE_NAME', { seat: mySeat, name: clean });
  }
}

async function claimSeat(idx) {
  const nameInput = document.getElementById('lobby-player-name');
  const name = (nameInput ? nameInput.value.trim() : '') || localStorage.getItem('remi_player_name') || `Pemain ${idx + 1}`;
  localStorage.setItem('remi_player_name', name);

  try {
    const res = await fetch(`/api/action?act=CLAIM_SEAT`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'CLAIM_SEAT',
        seat: idx,
        player_name: name,
        player_id: myPlayerId
      })
    });
    const data = await res.json();
    if (data.success) {
      mySeat = idx;
      sessionStorage.setItem('remi_my_seat', String(idx));
      const url = new URL(window.location);
      url.searchParams.set('seat', idx);
      window.history.replaceState({}, '', url);
      showToast(`✅ Anda berhasil menempati Kursi ${idx + 1}!`);
    } else {
      showToast(`⚠️ ${data.error || 'Kursi ini baru saja diambil oleh pemain lain!'}`);
      if (mySeat === idx) {
        mySeat = null;
        sessionStorage.removeItem('remi_my_seat');
      }
    }
    if (data.state) {
      lastStateVersion = data.state.state_version || 0;
      lastStateSeat = mySeat;
      updateUI(data.state);
    }
    wakeUpPollingFast();
  } catch (e) {
    console.error("Claim error:", e);
    showToast("⚠️ Gagal menghubungi server. Silakan coba lagi.");
  }
}

async function leaveSeat(idx) {
  try {
    const res = await fetch(`/api/action?act=LEAVE_SEAT`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'LEAVE_SEAT',
        seat: idx,
        player_id: myPlayerId
      })
    });
    const data = await res.json();
    sessionStorage.removeItem('remi_my_seat');
    mySeat = null;
    const url = new URL(window.location);
    url.searchParams.delete('seat');
    window.history.replaceState({}, '', url);
    showToast(`Anda meninggalkan Kursi ${idx + 1}.`);
    if (data.state) {
      lastStateVersion = data.state.state_version || 0;
      lastStateSeat = mySeat;
      updateUI(data.state);
    }
    wakeUpPollingFast();
  } catch (e) {
    console.error("Leave seat error:", e);
  }
}

async function toggleSeatBot(idx, isBot) {
  await sendAction('SET_BOT', { seat: idx, is_bot: isBot });
  showToast(isBot ? `Kursi ${idx + 1} diatur sebagai Bot.` : `Kursi ${idx + 1} dibuka untuk pemain lain.`);
}

async function kickSeat(idx) {
  if (confirm(`Kosongkan Kursi ${idx + 1} dan jadikan Bot?`)) {
    await sendAction('SET_BOT', { seat: idx, is_bot: true });
    showToast(`Kursi ${idx + 1} berhasil dikosongkan.`);
  }
}

async function leaveTableDuringGame() {
  if (confirm("Tinggalkan meja permainan? Kursi Anda akan digantikan oleh Bot dan Anda kembali ke Lobby.")) {
    if (mySeat !== null) {
      await leaveSeat(mySeat);
    }
    spectatorMode = false;
    sessionStorage.removeItem('remi_my_seat');
    const url = new URL(window.location);
    url.searchParams.delete('seat');
    window.history.replaceState({}, '', url);
    window.location.reload();
  }
}

async function nextRoundNow() {
  const modal = document.getElementById('winner-modal');
  if (modal) modal.style.display = 'none';
  const isMatchOver = latestState && (latestState.phase === 'MATCH_OVER' || latestState.phase === 'GAME_OVER');
  await sendAction(isMatchOver ? 'START_GAME' : 'START_ROUND');
}

function openHistoryModal() {
  const modal = document.getElementById('history-modal');
  const body = document.getElementById('history-modal-body');
  if (!modal || !body) return;
  const history = (latestState && latestState.round_history) ? latestState.round_history : [];
  if (history.length === 0) {
    body.innerHTML = `
      <div style="text-align:center; padding: 40px 16px; color:#94a3b8;">
        <div style="font-size:36px; margin-bottom:10px;">📜</div>
        <div style="font-size:15px; font-weight:700; color:#cbd5e1;">Belum Ada Riwayat Ronde Selesai</div>
        <div style="font-size:12px; margin-top:6px; color:#64748b;">Riwayat lengkap skor dan susunan kartu setiap pemain akan otomatis dicatat setelah ronde berakhir.</div>
      </div>
    `;
  } else {
    body.innerHTML = history.slice().reverse().map(rh => {
      const wCard = rh.wildcard_indicator ? `${rh.wildcard_indicator.rank}${rh.wildcard_indicator.suit || ''}` : '-';
      const closerText = rh.closer_name ? `Penutup: <b>${rh.closer_name}</b>${rh.closed_by_tutup_tangan ? ' (🌟 Tutup Tangan +250)' : ' (Tutup Biasa)'}` : (rh.reason || 'Selesai');
      return `
        <div class="history-round-box">
          <div class="history-round-header">
            <div>🏁 RONDE ${rh.round_number} <span style="font-size:11px; color:#94a3b8; font-weight:normal; margin-left:8px;">${closerText}</span></div>
            <div style="font-size:11.5px; color:#38bdf8;">WILD: <b>${wCard}</b></div>
          </div>
          <div style="overflow-x:auto;">
            <table class="standings-table" style="margin-bottom:0;">
              <thead>
                <tr>
                  <th style="min-width: 120px;">Pemain</th>
                  <th style="min-width: 220px;">Kartu Jadi (Melds)</th>
                  <th style="min-width: 150px;">Sisa Kartu Tangan</th>
                  <th style="text-align:center; min-width: 70px;">Ronde</th>
                  <th style="text-align:right; min-width: 70px;">Total</th>
                </tr>
              </thead>
              <tbody>
                ${(rh.players || []).map(p => {
                  const isCloser = rh.closer_seat !== null && p.seat === rh.closer_seat;
                  const rScore = p.round_score || 0;
                  const scoreClass = rScore > 0 ? 'color:#4ade80;' : (rScore < 0 ? 'color:#f87171;' : 'color:#94a3b8;');
                  const scoreText = rScore > 0 ? `+${rScore}` : `${rScore}`;
                  const burnTag = p.burned ? ' <span style="color:#f87171;font-size:10px;">🔥TERBAKAR</span>' : '';
                  return `<tr class="${isCloser ? 'winner-row' : ''}">
                    <td style="font-weight:700;">${isCloser ? '👑 ' : ''}${p.name}${burnTag}</td>
                    <td>${renderPlayerMeldsHTML(p.melds)}</td>
                    <td>${renderPlayerHandHTML(p.hand, isCloser)}</td>
                    <td style="text-align:center;font-weight:800;font-size:12.5px;${scoreClass}">${scoreText}</td>
                    <td style="text-align:right;font-weight:900;font-size:12.5px;color:#facc15;">${p.total_score}</td>
                  </tr>`;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }).join('');
  }
  modal.style.display = 'flex';
}

function closeHistoryModal() {
  const modal = document.getElementById('history-modal');
  if (modal) modal.style.display = 'none';
}

function spectateGame() {
  spectatorMode = true;
  const lobbyScreen = document.getElementById('lobby-screen');
  const tableScreen = document.getElementById('table');
  if (lobbyScreen) lobbyScreen.style.display = 'none';
  if (tableScreen) tableScreen.style.display = 'flex';
  showToast("Mode Penonton Aktif!");
}

function returnToLobby() {
  if (confirm("Kembali ke Ruang Lobby? Pertandingan saat ini akan di-reset.")) {
    sendAction('RESET_TO_LOBBY');
  }
}

async function startLobbyGame() {
  if (latestState && latestState.phase !== 'LOBBY') {
    if (mySeat === null) spectatorMode = true;
    const lobbyScreen = document.getElementById('lobby-screen');
    const tableScreen = document.getElementById('table');
    if (lobbyScreen) lobbyScreen.style.display = 'none';
    if (tableScreen) tableScreen.style.display = 'flex';
    return;
  }

  // Jika belum memilih kursi, dudukkan di kursi pertama yang kosong/bot secara atomic
  if (mySeat === null && latestState && latestState.players) {
    const freeIdx = latestState.players.findIndex(p => p.is_bot);
    if (freeIdx >= 0) {
      await claimSeat(freeIdx);
    }
  }

  await sendAction('START_GAME', { seat: (mySeat !== null ? mySeat : 0) });
  showToast("Permainan dimulai!");
}

async function updateLobbyConfig(type, val) {
  currentConfig[type] = val;
  const nameInput = document.getElementById('lobby-player-name');
  const myName = (nameInput ? nameInput.value.trim() : '') || localStorage.getItem('remi_player_name') || 'Pemain 1';

  try {
    await sendAction('CONFIGURE_ONLY', {
      turn_timer_sec: currentConfig.timer,
      target_score: currentConfig.score,
      num_players: currentConfig.players,
      player_name: myName,
      bot_delay_sec: currentConfig.botDelay
    });
    showToast("Pengaturan meja diperbarui!");
  } catch (e) {
    console.error(e);
  }
}

function renderLobby(st) {
  if (!st) return;

  const roomCodeEl = document.getElementById('lobby-room-code');
  if (roomCodeEl) roomCodeEl.textContent = `#${st.room_code || 'RM1500'}`;

  const statusMsgEl = document.getElementById('lobby-status-msg');
  if (statusMsgEl) {
    if (st.phase !== 'LOBBY') {
      statusMsgEl.innerHTML = `<span style="color:#4ade80;font-weight:700;">★ Pertandingan Sedang Berlangsung (Ronde ${st.round_number}) ★</span>`;
    } else {
      statusMsgEl.textContent = st.status_message || 'Pilih kursi Anda, atur konfigurasi meja, dan ajak teman mabar!';
    }
  }

  const nameInput = document.getElementById('lobby-player-name');
  if (nameInput && !nameInput.value) {
    const savedName = localStorage.getItem('remi_player_name') || 'Pemain 1';
    nameInput.value = savedName;
  }

  const players = st.players || [];
  const humanCount = players.filter(p => !p.is_bot).length;
  const botCount = players.filter(p => p.is_bot).length;
  const summaryEl = document.getElementById('lobby-player-summary');
  if (summaryEl) {
    summaryEl.textContent = `${players.length} Kursi (${humanCount} Manusia, ${botCount} Bot)`;
  }

  const spectateBtn = document.getElementById('btn-lobby-spectate');
  if (spectateBtn) {
    spectateBtn.style.display = (st.phase !== 'LOBBY') ? 'inline-flex' : 'none';
  }

  const startBtn = document.getElementById('btn-start-lobby-game');
  if (startBtn) {
    if (st.phase !== 'LOBBY') {
      startBtn.innerHTML = '👁️ MASUK KE MEJA PERMAINAN';
      startBtn.style.background = 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)';
      startBtn.style.borderColor = '#38bdf8';
    } else {
      startBtn.innerHTML = '▶️ MULAI PERMAINAN';
      startBtn.style.background = 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)';
      startBtn.style.borderColor = '#4ade80';
    }
  }

  // Render 4 Seat Cards
  const gridEl = document.getElementById('lobby-seats-grid');
  if (gridEl) {
    gridEl.innerHTML = players.map(p => {
      const isMe = (p.player_id && p.player_id === myPlayerId) || (mySeat === p.seat);
      const isBot = Boolean(p.is_bot);
      const isHost = (p.seat === 0);
      const isOtherHuman = (!isBot && Boolean(p.player_id) && p.player_id !== myPlayerId);
      const isOpen = isBot || !p.player_id;

      let cardClass = 'seat-card';
      if (isMe) cardClass += ' seat-me';
      else if (isOtherHuman) cardClass += ' seat-human';

      let statusBadge = '';
      if (isMe) {
        statusBadge = '<span class="seat-badge seat-badge-me">★ ANDA ★</span>';
      } else if (isOtherHuman) {
        statusBadge = '<span class="seat-badge seat-badge-human">MANUSIA</span>';
      } else if (isBot) {
        statusBadge = '<span class="seat-badge seat-badge-bot">BOT AI</span>';
      } else {
        statusBadge = '<span class="seat-badge seat-badge-bot" style="color:#4ade80;">TERSEDIA</span>';
      }

      let avatar = '👤';
      if (isHost && isMe) avatar = '👑';
      else if (isHost) avatar = '👑';
      else if (isBot) avatar = '🤖';

      let mainBtn = '';
      if (isMe) {
        mainBtn = `<button class="lobby-btn btn-leave" onclick="leaveSeat(${p.seat})">🚪 TINGGALKAN KURSI</button>`;
      } else if (isOtherHuman) {
        mainBtn = `<button class="lobby-btn" disabled style="background:rgba(255,255,255,0.08);color:#94a3b8;cursor:not-allowed;border:1px solid rgba(255,255,255,0.15);">🔒 TERISI (${p.name})</button>`;
      } else if (mySeat === null) {
        mainBtn = `<button class="lobby-btn btn-claim" onclick="claimSeat(${p.seat})">🪑 DUDUK DI SINI ${isHost ? '(Host)' : ''}</button>`;
      } else {
        mainBtn = `<button class="lobby-btn btn-switch" onclick="claimSeat(${p.seat})">🔄 PINDAH KE SINI ${isHost ? '(Host)' : ''}</button>`;
      }

      let subActionBtn = '';
      if (isMe) {
        subActionBtn = `<button class="seat-sub-btn" onclick="leaveSeat(${p.seat})" style="color:#f87171;">🚪 Tinggalkan Kursi</button>`;
      } else if (isBot) {
        subActionBtn = `<button class="seat-sub-btn" onclick="toggleSeatBot(${p.seat}, false)">👤 Buka untuk Teman</button>`;
      } else if (isOpen) {
        subActionBtn = `<span class="seat-sub-btn" style="color:#4ade80;cursor:default;">Tersedia (Bebas)</span>`;
      } else if (mySeat === 0) {
        subActionBtn = `<button class="seat-sub-btn" onclick="kickSeat(${p.seat})" style="color:#fb923c;">⚠️ Kosongkan / Jadikan Bot</button>`;
      } else {
        subActionBtn = `<span class="seat-sub-btn" style="opacity:0.6;cursor:default;">Ditempati (${p.name})</span>`;
      }

      return `<div class="${cardClass}">
        <div class="seat-header">
          <span>Kursi ${p.seat + 1} ${isHost ? '(Host)' : ''}</span>
          ${statusBadge}
        </div>
        <div class="seat-avatar">${avatar}</div>
        <div class="seat-name">${p.name}</div>
        ${mainBtn}
        <div class="seat-sub-actions">
          ${subActionBtn}
          <button class="seat-sub-btn" onclick="copySeatDirectLink(${p.seat})" title="Salin link langsung">🔗 Link</button>
        </div>
      </div>`;
    }).join('');
  }

  syncLobbyConfigPillsUI(st);
}

function syncLobbyConfigPillsUI(st) {
  const n = st.max_players || st.players.length;
  highlightPills('lobby-players-pills', n);

  const score = st.target_score;
  highlightPills('lobby-score-pills', score);
  const scoreBadge = document.getElementById('lobby-score-badge');
  if (scoreBadge) scoreBadge.textContent = `${score} Poin`;

  const timer = st.turn_timer_sec;
  highlightPills('lobby-timer-pills', timer);
  const timerBadge = document.getElementById('lobby-timer-badge');
  if (timerBadge) timerBadge.textContent = timer === 0 ? 'Tanpa' : `${timer}s`;

  const delay = st.bot_delay_sec || 1.0;
  highlightPills('lobby-bot-pills', delay);
}

function highlightPills(containerId, activeVal) {
  const btns = document.querySelectorAll(`#${containerId} .pill-btn`);
  btns.forEach(b => {
    if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(String(activeVal))) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });
}

// Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'Escape') {
    const histModal = document.getElementById('history-modal');
    if (histModal && histModal.style.display === 'flex') {
      closeHistoryModal();
      return;
    }
    togglePause();
  }
  else if (e.key === 'h' || e.key === 'H') {
    const histModal = document.getElementById('history-modal');
    if (histModal && histModal.style.display === 'flex') {
      closeHistoryModal();
    } else {
      openHistoryModal();
    }
  }
  else if (e.key === 'p' || e.key === 'P') openDashboard();
  else if (e.key === 'd' || e.key === 'D') sendAction('DRAW_DECK');
  else if (e.key === 'm' || e.key === 'M') meldSelected();
  else if (e.key === 'a' || e.key === 'A') sendAction('AUTO_MELD');
  else if (e.key === 't' || e.key === 'T') declareTutupTangan();
  else if (e.key === 'b' || e.key === 'B') discardSelected();
  else if (e.key === 's' || e.key === 'S') sendAction('SORT_RANK');
  else if (e.key === 'f' || e.key === 'F') sendAction('SORT_SUIT');
  else if (e.key === 'c' || e.key === 'C') triggerCeki();
  else if (e.key === '[' || e.key === '{') slideSelectedCard(-1);
  else if (e.key === ']' || e.key === '}') slideSelectedCard(1);
  else if (e.key === 'ArrowLeft' && selectedCards.size > 0) { e.preventDefault(); slideSelectedCard(-1); }
  else if (e.key === 'ArrowRight' && selectedCards.size > 0) { e.preventDefault(); slideSelectedCard(1); }
});

// Real-time Polling (Smart Adaptive Heartbeat dengan Versioning, Dynamic Throttling & Fast Wakeup)
let lastStateVersion = 0;
let lastStateSeat = null;
let pollInFlight = false;
let currentPollIntervalMs = 400;
let pollTimer = null;
let consecutiveUnchangedCount = 0;

function computeOptimalPollInterval(st) {
  if (document.hidden) return 2500;
  if (!st) return 600;
  if (st.is_paused) return 1500;
  if (st.phase === 'LOBBY') return 1000;
  if (st.phase === 'ROUND_OVER' || st.phase === 'MATCH_OVER' || st.phase === 'GAME_OVER') return 800;

  const isMyTurn = (mySeat !== null) && (st.current_turn_seat === mySeat) && (st.phase === 'TURN_DRAW' || st.phase === 'TURN_MELD_DISCARD');
  if (isMyTurn) {
    return 350; // Respon super cepat saat giliran saya
  }

  // Saat giliran pemain lain / bot
  if (consecutiveUnchangedCount > 6) {
    return 1000; // Meja hening/pemain lain sedang berpikir, hemat kuota
  }
  return 700; // Halus & responsif saat giliran lawan, memangkas 50% request
}

function resetPollSchedule(targetIntervalMs) {
  if (targetIntervalMs && targetIntervalMs !== currentPollIntervalMs) {
    currentPollIntervalMs = targetIntervalMs;
  }
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(pollState, currentPollIntervalMs);
}

function wakeUpPollingFast() {
  consecutiveUnchangedCount = 0;
  currentPollIntervalMs = 350;
  if (pollTimer) clearTimeout(pollTimer);
  if (!pollInFlight) {
    pollState();
  } else {
    pollTimer = setTimeout(pollState, 350);
  }
}

async function pollState() {
  if (pollInFlight) {
    resetPollSchedule(currentPollIntervalMs);
    return;
  }
  pollInFlight = true;
  try {
    const qParams = new URLSearchParams();
    if (mySeat !== null) qParams.set('seat', mySeat);
    if (myPlayerId) qParams.set('pid', myPlayerId);
    if (lastStateVersion && lastStateSeat === mySeat) qParams.set('ver', lastStateVersion);
    const res = await fetch(`/api/state?${qParams.toString()}`, { cache: 'no-store' });
    const data = await res.json();
    if (data.unchanged) {
      consecutiveUnchangedCount++;
      if (data.time_left !== undefined && latestState) {
        latestState.turn_remaining_sec = data.time_left;
      }
      const nextInterval = computeOptimalPollInterval(latestState);
      resetPollSchedule(nextInterval);
      return;
    }
    if (data.state) {
      consecutiveUnchangedCount = 0;
      lastStateVersion = data.state.state_version || 0;
      lastStateSeat = mySeat;
      updateUI(data.state);
      const nextInterval = computeOptimalPollInterval(data.state);
      resetPollSchedule(nextInterval);
    }
  } catch (e) {
    resetPollSchedule(1000);
  } finally {
    pollInFlight = false;
  }
}

pollState();

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    resetPollSchedule(2500);
  } else {
    wakeUpPollingFast();
  }
});
</script>
</body>
</html>"""

HTML_PAGE_BYTES = HTML_PAGE.encode("utf-8")
HTML_PAGE_GZIPPED = gzip.compress(HTML_PAGE_BYTES, compresslevel=6)

def _format_state_dict(seat: Optional[int]) -> dict:
    is_spec = (seat is None or not (0 <= seat < len(GAME.players)))
    viewer_seat = seat if not is_spec else None
    st = GAME.to_state_dict(viewer_seat=viewer_seat, spectator_delay=is_spec)
    st["host_ip"] = get_local_ip()
    st["server_port"] = 8080
    st["deck_count"] = st.get("draw_pile_count", 0)
    st["discards"] = st.get("discard_pile", [])
    st["wildcard_card"] = st.get("wildcard_indicator", None)
    st["wildcard_multiplier"] = GAME._wildcard_value()
    st["last_event"] = st.get("status_message", "")
    st["leader_seat"] = st.get("highest_score_seat", 0)
    latest_ceki = getattr(GAME, "latest_ceki", None)
    if latest_ceki and (time.time() - latest_ceki.get("timestamp", 0) < 3.0):
        st["latest_ceki"] = latest_ceki
    else:
        st["latest_ceki"] = None
    st["state_version"] = GAME.compute_view_signature()
    return st


class RemiWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/audio/"):
            fname = os.path.basename(parsed.path)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            audio_path = os.path.join(base_dir, "assets", "audio", fname)
            if not os.path.exists(audio_path):
                audio_path = os.path.join(os.getcwd(), "assets", "audio", fname)
            if os.path.exists(audio_path):
                try:
                    with open(audio_path, "rb") as af:
                        content = af.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "public, max-age=604800, immutable")
                    self.end_headers()
                    self.wfile.write(content)
                except Exception:
                    pass
                return
            else:
                self.send_error(404, f"File {fname} not found")
                return

        if parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            seat_param = qs.get("seat", [None])[0]
            seat = int(seat_param) if (seat_param is not None and str(seat_param).isdigit()) else None
            player_id = qs.get("pid", [""])[0].strip()
            client_ver = qs.get("ver", [None])[0]
            with GAME_LOCK:
                now = time.time()
                if player_id:
                    for p in GAME.players:
                        if not p.is_bot and getattr(p, "player_id", "") == player_id:
                            p.last_seen = now
                            p.connected = True
                if GAME.phase == "LOBBY":
                    for idx, p in enumerate(GAME.players):
                        if not p.is_bot and getattr(p, "player_id", ""):
                            if (now - getattr(p, "last_seen", now)) > 25.0:
                                p.is_bot = True
                                p.auto_pilot = True
                                p.player_id = ""
                                p.connected = True
                                bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                                p.name = bot_names[idx % len(bot_names)]
                                GAME.status_message = f"Kursi {idx + 1} dibuka kembali karena pemain terputus."
                else:
                    for idx, p in enumerate(GAME.players):
                        if not p.is_bot and getattr(p, "player_id", ""):
                            if (now - getattr(p, "last_seen", now)) > 25.0:
                                p.is_bot = True
                                p.auto_pilot = True
                                p.player_id = ""
                                p.connected = True
                                bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                                p.name = bot_names[idx % len(bot_names)]
                                GAME.status_message = f"Pemain di Kursi {idx + 1} terputus dan otomatis digantikan oleh {p.name}."

                tick_game_state_locked()
                cur_v = GAME.compute_view_signature()
                latest_ceki_time = getattr(GAME, "latest_ceki", {}).get("timestamp", 0) if getattr(GAME, "latest_ceki", None) else 0
                has_active_ceki = (time.time() - latest_ceki_time) < 2.5
                if client_ver and str(client_ver) == str(cur_v) and GAME.phase not in ("ROUND_OVER", "MATCH_OVER") and not has_active_ceki:
                    self._send_json({"unchanged": True, "v": cur_v, "time_left": round(GAME.turn_remaining_sec, 1)})
                    return
                st = _format_state_dict(seat)
                st["state_version"] = cur_v
            self._send_json({"state": st})
            return
        if parsed.path == "/api/config":
            with GAME_LOCK:
                cfg = {
                    "room_code": GAME.room_code,
                    "num_players": GAME.max_players,
                    "turn_timer_sec": GAME.turn_timer_sec,
                    "target_score": GAME.target_score,
                    "player_name": GAME.players[0].name if GAME.players else "Anda",
                    "bot_delay_sec": getattr(GAME, "bot_delay_sec", 1.0),
                }
            self._send_json(cfg)
            return

        accept_enc = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_enc:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(HTML_PAGE_GZIPPED)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(HTML_PAGE_GZIPPED)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(HTML_PAGE_BYTES)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(HTML_PAGE_BYTES)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(raw)
        seat_raw = payload.get("seat", qs.get("seat", [None])[0])
        seat = int(seat_raw) if (seat_raw is not None and str(seat_raw).isdigit()) else 0
        action = payload.get("action") or qs.get("act", [""])[0]
        player_id = str(payload.get("player_id", "")).strip()

        with GAME_LOCK:
            now = time.time()
            if player_id:
                for p in GAME.players:
                    if not p.is_bot and getattr(p, "player_id", "") == player_id:
                        p.last_seen = now
                        p.connected = True

            if action in ("START_GAME", "START_ROUND"):
                if GAME.phase == "LOBBY":
                    bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                    for idx, p in enumerate(GAME.players):
                        if p.is_bot and (not p.name or "Menunggu" in p.name):
                            p.name = bot_names[idx % len(bot_names)]
                    GAME.start_new_round()
                    GAME.status_message = f"Permainan dimulai! Ronde {GAME.round_number} aktif."
                elif GAME.phase == "ROUND_OVER":
                    GAME.round_over_timer = None
                    GAME.start_new_round()
                    GAME.status_message = f"Ronde {GAME.round_number} dimulai!"
                elif GAME.phase in ("MATCH_OVER", "GAME_OVER"):
                    GAME.round_over_timer = None
                    GAME.reset_match()
                    GAME.start_new_round()
                    GAME.status_message = f"Pertandingan baru dimulai! Ronde {GAME.round_number} aktif."
                self._send_json({"success": True, "state": _format_state_dict(seat)})
                return
            elif action in ("RESET_TO_LOBBY", "TO_LOBBY"):
                GAME.reset_match()
                GAME.status_message = "Kembali ke Ruang Lobby. Silakan pilih kursi atau atur meja."
                self._send_json({"success": True, "state": _format_state_dict(None)})
                return
            elif action == "CLAIM_SEAT":
                seat_idx = int(payload.get("seat", seat))
                name = payload.get("player_name", "").strip() or f"Pemain {seat_idx + 1}"
                if not (0 <= seat_idx < len(GAME.players)):
                    self._send_json({"success": False, "error": "Kursi tidak valid.", "state": _format_state_dict(None)})
                    return

                target_p = GAME.players[seat_idx]
                target_pid = getattr(target_p, "player_id", "")
                is_occupied_by_other = (
                    not target_p.is_bot
                    and target_pid
                    and target_pid != player_id
                    and (now - getattr(target_p, "last_seen", now)) < 35.0
                )

                if is_occupied_by_other:
                    self._send_json({
                        "success": False,
                        "error": f"Kursi {seat_idx + 1} baru saja diambil oleh {target_p.name}! Silakan pilih kursi lain yang masih tersedia.",
                        "occupied_by": target_p.name,
                        "state": _format_state_dict(None)
                    })
                    return

                if player_id:
                    for old_idx, old_p in enumerate(GAME.players):
                        if old_idx != seat_idx and not old_p.is_bot and getattr(old_p, "player_id", "") == player_id:
                            old_p.is_bot = True
                            old_p.auto_pilot = True
                            old_p.player_id = ""
                            bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                            old_p.name = bot_names[old_idx % len(bot_names)]

                target_p.is_bot = False
                target_p.auto_pilot = False
                target_p.player_id = player_id
                target_p.name = name
                target_p.last_seen = now
                GAME.status_message = f"{name} berhasil menempati Kursi {seat_idx + 1}!"
                self._send_json({"success": True, "claimed_seat": seat_idx, "state": _format_state_dict(seat_idx)})
                return
            elif action == "LEAVE_SEAT":
                seat_idx = int(payload.get("seat", seat))
                if 0 <= seat_idx < len(GAME.players):
                    target_p = GAME.players[seat_idx]
                    old_name = target_p.name
                    target_p.is_bot = True
                    target_p.auto_pilot = True
                    target_p.player_id = ""
                    target_p.connected = True
                    bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                    target_p.name = bot_names[seat_idx % len(bot_names)]
                    GAME.status_message = f"{old_name} meninggalkan Kursi {seat_idx + 1} dan digantikan Bot."
                self._send_json({"success": True, "state": _format_state_dict(None)})
                return
            elif action == "SET_BOT":
                seat_idx = int(payload.get("seat", seat))
                if 0 <= seat_idx < len(GAME.players):
                    is_bot = bool(payload.get("is_bot", True))
                    target_p = GAME.players[seat_idx]
                    target_p.is_bot = is_bot
                    target_p.auto_pilot = is_bot
                    if is_bot:
                        target_p.player_id = ""
                        bot_names = ["Bot Siti", "Bot Budi", "Bot Agus", "Bot Joko"]
                        target_p.name = bot_names[seat_idx % len(bot_names)]
                        GAME.status_message = f"Kursi {seat_idx + 1} diatur sebagai Bot."
                    else:
                        target_p.name = f"Pemain {seat_idx + 1} (Menunggu...)"
                        target_p.player_id = ""
                        GAME.status_message = f"Kursi {seat_idx + 1} dibuka untuk teman/pemain lain."
                self._send_json({"success": True, "state": _format_state_dict(None)})
                return
            elif action == "CONFIGURE_AND_START":
                GAME.configure_match(
                    num_players=payload.get("num_players"),
                    turn_timer_sec=payload.get("turn_timer_sec"),
                    target_score=payload.get("target_score"),
                    player_name=payload.get("player_name"),
                    bot_delay_sec=payload.get("bot_delay_sec"),
                )
                GAME.reset_match()
                GAME.start_new_round()
            elif action == "CONFIGURE_ONLY":
                GAME.configure_match(
                    num_players=payload.get("num_players"),
                    turn_timer_sec=payload.get("turn_timer_sec"),
                    target_score=payload.get("target_score"),
                    player_name=payload.get("player_name"),
                    bot_delay_sec=payload.get("bot_delay_sec"),
                )
            elif action == "CHANGE_NAME":
                seat_idx = int(payload.get("seat", seat))
                name = payload.get("name", "").strip()
                if name and 0 <= seat_idx < len(GAME.players):
                    old_name = GAME.players[seat_idx].name
                    GAME.players[seat_idx].name = name
                    GAME.status_message = f"{old_name} mengubah nama menjadi {name}."
            elif action == "RESET_MATCH":
                GAME.reset_match()
                GAME.start_new_round()
            elif action == "START_ROUND":
                GAME.start_new_round()
            elif action in ("TOGGLE_PAUSE", "PAUSE", "RESUME"):
                _, msg = GAME.toggle_pause()
                GAME.status_message = msg
            elif action in ("DRAW_DECK", "AMBIL_PAK"):
                _, msg = GAME.draw_from_deck(seat)
                GAME.status_message = msg
            elif action in ("TAKE_DISCARD", "DRAW_DISCARD"):
                idx = int(payload.get("discard_index", payload.get("index", -1)))
                card_ids = payload.get("card_ids", None)
                _, msg = GAME.take_from_discard(seat, idx, card_ids)
                GAME.status_message = msg
            elif action in ("MELD_HAND", "MELD_CARDS"):
                card_ids = payload.get("card_ids", [])
                _, msg = GAME.meld_from_hand(seat, card_ids)
                GAME.status_message = msg
            elif action == "AUTO_MELD":
                _, msg = GAME.auto_meld_all_valid(seat)
                GAME.status_message = msg
            elif action == "TUTUP_TANGAN":
                _, msg = GAME.declare_tutup_tangan(seat, payload.get("card_id"))
                GAME.status_message = msg
            elif action in ("DISCARD", "DISCARD_CARD"):
                card_id = payload.get("card_id", "")
                _, msg = GAME.discard_card(seat, card_id)
                GAME.status_message = msg
            elif action == "SORT_RANK":
                if seat < len(GAME.players):
                    GAME.players[seat].sort_hand(by_suit=False)
            elif action == "SORT_SUIT":
                if seat < len(GAME.players):
                    GAME.players[seat].sort_hand(by_suit=True)
            elif action == "REORDER_HAND":
                GAME.reorder_player_hand(
                    seat,
                    payload.get("source_card_id", ""),
                    payload.get("target_card_id", ""),
                )
            elif action == "CEKI":
                if 0 <= seat < len(GAME.players) and GAME.check_is_ceki(seat):
                    now = time.time()
                    last_t = getattr(GAME, "last_ceki_times", {}).get(seat, 0.0)
                    if now - last_t >= 1.8:
                        if not hasattr(GAME, "last_ceki_times"):
                            GAME.last_ceki_times = {}
                        GAME.last_ceki_times[seat] = now
                        if not hasattr(GAME, "ceki_counts"):
                            GAME.ceki_counts = {}
                        GAME.ceki_counts[seat] = GAME.ceki_counts.get(seat, 0) + 1
                        count = GAME.ceki_counts[seat]
                        p_name = GAME.players[seat].name
                        GAME.status_message = f"📢 {p_name} berseru: CEKI!"
                        GAME.latest_ceki = {"seat": seat, "timestamp": now, "name": p_name, "count": count}
                        GAME.state_version = getattr(GAME, "state_version", 1) + 1

            st = _format_state_dict(seat)

        self._send_json({"state": st})

    def _send_json(self, obj: dict, status: int = 200, extra_headers: Optional[dict] = None):
        try:
            data = json.dumps(obj).encode("utf-8")
            accept_enc = self.headers.get("Accept-Encoding", "")
            can_gzip = "gzip" in accept_enc and len(data) > 180
            payload = gzip.compress(data, compresslevel=6) if can_gzip else data

            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            if can_gzip:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass


def run_web_server(port: int = 8080, open_browser: bool = True):
    url = f"http://localhost:{port}"
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), RemiWebHandler)
    except OSError as e:
        err_msg = str(e).lower()
        if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) == 98 or "already in use" in err_msg:
            print(f"[INFO] Server Remi Nusantara 2D sudah aktif di: {url}")
            print(f"[INFO] Membuka browser ke {url} ...")
            if open_browser:
                webbrowser.open(url)
            return
        raise e

    threading.Thread(target=_bot_background_worker, daemon=True).start()
    print(f"[REMI NUSANTARA 2D ONLINE] Server aktif di: {url}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    env_port = int(os.environ.get("PORT", "8080"))
    is_cloud = any(
        k in os.environ
        for k in ("PORT", "RENDER", "RAILWAY_ENVIRONMENT", "CODESPACES", "DYNO", "KOYEB_SERVICE_NAME")
    )
    run_web_server(port=env_port, open_browser=not is_cloud)
