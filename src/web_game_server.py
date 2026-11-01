"""Web Game Server for Remi Nusantara 2D Online (Local Browser Edition).
Royale Theme with Responsive Non-Overlapping Layout.
"""

from __future__ import annotations
import http.server
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json
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
GAME = RemiGameMatch(room_code="RM1500", num_players=4, turn_timer_sec=30)
GAME.start_new_round()

def _bot_background_worker():
    last_t = time.time()
    bot_accum = 0.0
    while True:
        time.sleep(0.15)
        now = time.time()
        dt = now - last_t
        last_t = now
        with GAME_LOCK:
            if getattr(GAME, "is_paused", False):
                continue
            if GAME.phase in ("TURN_DRAW", "TURN_MELD_DISCARD"):
                cur_p = GAME.players[GAME.current_turn_seat]
                if cur_p.is_bot or cur_p.auto_pilot:
                    bot_accum += dt
                    delay = getattr(GAME, "bot_delay_sec", 1.0)
                    if bot_accum >= delay:
                        bot_accum = 0.0
                        GAME.execute_bot_or_timeout_step()
                else:
                    if GAME.turn_timer_sec > 0:
                        GAME.turn_remaining_sec = max(0.0, GAME.turn_remaining_sec - dt)
                        if GAME.turn_remaining_sec <= 0.0:
                            GAME.execute_bot_or_timeout_step()
            elif GAME.phase == "ROUND_OVER":
                if hasattr(GAME, "round_over_timer") and GAME.round_over_timer is not None:
                    GAME.round_over_timer = max(0.0, GAME.round_over_timer - dt)
                    if GAME.round_over_timer <= 0.0:
                        GAME.start_new_round()

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
    /* Large card dimensions */
    --hand-card-w: clamp(96px, 7.5vw, 108px);
    --hand-card-h: clamp(140px, 11vw, 158px);
    --disc-card-w: clamp(78px, 6vw, 86px);
    --disc-card-h: clamp(114px, 8.8vw, 126px);
    --meld-card-w: clamp(48px, 3.8vw, 54px);
    --meld-card-h: clamp(68px, 5.4vw, 76px);
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

  /* MEJA PERMAINAN ROYALE */
  #table {
    flex: 1;
    margin: 4px 8px;
    border: 7px solid var(--wood-rail);
    border-radius: 20px;
    box-shadow: inset 0 0 50px rgba(0,0,0,0.85), 0 10px 30px rgba(0,0,0,0.9);
    outline: 1.5px solid rgba(250, 204, 21, 0.25);
    outline-offset: -4px;
    background: radial-gradient(ellipse at 50% 48%, var(--felt-center) 0%, var(--felt-mid) 52%, var(--felt-dark) 100%);
    display: grid;
    grid-template-columns: minmax(190px, 230px) 1fr minmax(190px, 230px);
    grid-template-rows: auto auto 1fr auto auto;
    gap: 4px 8px;
    padding: 6px 10px;
    position: relative;
    max-height: calc(100vh - 8px);
    overflow: hidden;
  }

  /* TOP HEADER HUD */
  .header-bar {
    grid-column: 1 / 4;
    grid-row: 1 / 2;
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
    overflow: hidden;
  }
  .zone-active {
    border-color: #facc15;
    box-shadow: 0 0 16px rgba(250, 204, 21, 0.35), inset 0 0 10px rgba(250, 204, 21, 0.15);
  }

  /* OPPONENT: TOP (Bot Siti) */
  #zone-top {
    grid-column: 2 / 3;
    grid-row: 2 / 3;
    padding: 4px 10px;
    gap: 3px;
  }

  /* OPPONENT: LEFT (Bot Budi) */
  #zone-left {
    grid-column: 1 / 2;
    grid-row: 2 / 5;
    justify-content: flex-start;
    gap: 4px;
    padding: 6px;
  }

  /* OPPONENT: RIGHT (Bot Agus) */
  #zone-right {
    grid-column: 3 / 4;
    grid-row: 2 / 5;
    justify-content: flex-start;
    gap: 4px;
    padding: 6px;
  }

  /* CENTER AREA (HERO: Pak Kartu + Wild + BIG DISCARD RAIL) */
  #zone-center {
    grid-column: 2 / 3;
    grid-row: 3 / 4;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 4px 0;
    min-height: 140px;
  }

  /* PLAYER AREA (Anda / Player 1) */
  #zone-bottom {
    grid-column: 2 / 3;
    grid-row: 4 / 5;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 6px 12px 4px 12px;
    background: rgba(4, 26, 16, 0.85);
    border: 1.5px solid rgba(250, 204, 21, 0.4);
    border-radius: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.45);
    position: relative;
  }

  .player-title {
    font-size: 11.5px;
    font-weight: 800;
    color: #f1f5f9;
    letter-spacing: 0.3px;
    text-align: center;
    line-height: 1.3;
  }
  .turn-badge {
    background: #facc15;
    color: #022c16;
    font-weight: 900;
    font-size: 9px;
    padding: 1px 7px;
    border-radius: 999px;
    letter-spacing: 0.3px;
    animation: pulse-glow 1.2s infinite alternate ease-in-out;
    margin-bottom: 2px;
  }
  @keyframes pulse-glow {
    0% { transform: scale(0.97); opacity: 0.85; }
    100% { transform: scale(1.03); opacity: 1; filter: drop-shadow(0 0 6px #facc15); }
  }

  .cards-row {
    display: flex;
    justify-content: center;
    align-items: center;
  }
  .opp-cards {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 2px;
  }
  .opp-cards .card-back + .card-back {
    margin-left: -18px;
  }

  /* ======================================================== */
  /* PROMINENT MELDS CONTAINER (KARTU JADI PEMAIN LAIN)       */
  /* ======================================================== */
  .meld-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
    align-items: center;
    width: 100%;
    min-height: 28px;
    padding: 4px 6px;
    background: rgba(0,0,0,0.3);
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .meld-empty-hint {
    font-size: 10px;
    color: rgba(255,255,255,0.4);
    font-style: italic;
    padding: 2px 4px;
    text-align: center;
  }
  .meld-group {
    display: flex;
    gap: 2px;
    padding: 3px 5px;
    background: rgba(255,255,255,0.08);
    border: 1.5px solid rgba(250, 204, 21, 0.4);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  }

  /* CARD BACK */
  .card-back {
    width: 34px;
    height: 48px;
    background: radial-gradient(circle at center, #991b1b 0%, #580c0c 100%);
    border: 1.5px solid #fbbf24;
    border-radius: 5px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fde047;
    font-size: 8px;
    font-weight: 900;
    box-shadow: 0 2px 6px rgba(0,0,0,0.45);
    position: relative;
    user-select: none;
    flex-shrink: 0;
  }
  .card-back::after {
    content: "♠";
    font-size: 12px;
    opacity: 0.85;
  }

  /* PAK KARTU (Draw Deck 3D) */
  #pak-box {
    width: clamp(86px, 6.8vw, 98px);
    height: clamp(124px, 9.6vw, 138px);
    background: radial-gradient(circle at 40% 30%, #991b1b 0%, #450a0a 100%);
    border: 2px solid #fbbf24;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    text-align: center;
    padding: 6px;
    box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 10px 22px rgba(0,0,0,0.7);
    transition: transform 0.14s ease, box-shadow 0.14s ease;
    flex-shrink: 0;
  }
  #pak-box:hover {
    transform: translateY(-5px) scale(1.03);
    box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 16px 28px rgba(0,0,0,0.8), 0 0 18px rgba(251, 191, 36, 0.45);
  }
  #pak-box.glow {
    border-color: #facc15;
    animation: pak-glow 1.4s infinite alternate ease-in-out;
  }
  @keyframes pak-glow {
    0% { box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 0 8px rgba(250, 204, 21, 0.5); }
    100% { box-shadow: 2px 2px 0 #7f1d1d, 4px 4px 0 #600a0a, 0 0 24px rgba(250, 204, 21, 0.95); }
  }

  /* BUKAAN WILD */
  #wild-box {
    background: radial-gradient(ellipse at center, rgba(88, 28, 135, 0.75) 0%, rgba(38, 10, 60, 0.9) 100%);
    border: 1.5px solid #c084fc;
    border-radius: 12px;
    padding: 4px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: clamp(86px, 6.8vw, 98px);
    height: clamp(124px, 9.6vw, 138px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.5), 0 0 14px rgba(192, 132, 252, 0.3);
    flex-shrink: 0;
  }
  #wild-card-slot .card {
    width: clamp(74px, 5.8vw, 84px);
    height: clamp(108px, 8.4vw, 122px);
    cursor: default;
  }
  #wild-card-slot .card:hover { transform: none; }

  /* ======================================================== */
  /* PROMINENT DISCARD RAIL (KARTU YANG DIBUANG)              */
  /* ======================================================== */
  #discard-rail {
    background: rgba(3, 24, 14, 0.85);
    border: 2px solid rgba(250, 204, 21, 0.4);
    border-radius: 14px;
    padding: 6px 10px;
    flex: 1;
    min-width: 0;
    height: clamp(124px, 9.6vw, 138px);
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    box-shadow: inset 0 2px 12px rgba(0,0,0,0.55), 0 4px 14px rgba(0,0,0,0.3);
  }
  #disc-cards {
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    overflow-y: hidden;
    gap: 8px;
    align-items: center;
    justify-content: flex-start;
    width: 100%;
    height: 100%;
    padding: 4px 2px;
  }
  #disc-cards::-webkit-scrollbar { height: 5px; }
  #disc-cards::-webkit-scrollbar-thumb { background: rgba(250, 204, 21, 0.45); border-radius: 4px; }

  /* LARGE DISCARD CARDS */
  #disc-cards .card {
    width: var(--disc-card-w);
    height: var(--disc-card-h);
    flex-shrink: 0;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  #disc-cards .card:hover {
    transform: translateY(-8px) scale(1.05);
    z-index: 20;
    box-shadow: 0 12px 24px rgba(0,0,0,0.65), 0 0 16px rgba(250, 204, 21, 0.4);
  }
  #disc-cards .c-rank { font-size: 16px; }
  #disc-cards .c-suit-mini { font-size: 13px; }
  #disc-cards .c-center { font-size: 34px; }
  #disc-cards .c-badge-pill {
    font-size: 8.5px;
    padding: 2px 6px;
    background: #facc15;
    color: #0f172a;
    font-weight: 900;
    border: 1px solid #eab308;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
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
  .card.red { color: #dc2626; }
  .card.black { color: #0f172a; }
  .card.joker {
    background: linear-gradient(168deg, #faf5ff 0%, #f3e8ff 100%);
    border-color: #c084fc;
    color: #7e22ce;
  }

  /* CORNER INDEXES (Top-Left always visible when overlapping!) */
  .c-corner-tl {
    position: absolute;
    top: 5px;
    left: 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1;
    pointer-events: none;
  }
  .c-corner-br {
    position: absolute;
    bottom: 5px;
    right: 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1;
    transform: rotate(180deg);
    pointer-events: none;
  }
  .c-rank {
    font-family: 'Outfit', system-ui, -apple-system, sans-serif;
    font-weight: 900;
    font-size: 18px;
    line-height: 1;
    letter-spacing: -0.5px;
  }
  .c-suit-mini {
    font-size: 14px;
    line-height: 1;
    margin-top: 1.5px;
  }

  /* CENTER SUIT ICON */
  .c-center {
    position: absolute;
    top: 50%;
    left: 48%;
    transform: translate(-50%, -50%);
    font-size: 40px;
    line-height: 1;
    pointer-events: none;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));
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
  /* PLAYER HAND: 50% OVERLAPPING FAN (MENUMPUK SETENGAH KARTU)*/
  /* ======================================================== */
  #my-hand {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    padding: 22px 14px 4px 14px;
    width: 100%;
    min-height: 156px;
  }
  #my-hand .card {
    width: var(--hand-card-w);
    height: var(--hand-card-h);
    margin-left: calc(var(--hand-card-w) * -0.52); /* Menumpuk 50%! */
    box-shadow: -4px 0 12px rgba(0,0,0,0.45), 0 4px 12px rgba(0,0,0,0.3);
    transition: transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.18s ease, z-index 0.18s ease;
    position: relative;
    flex-shrink: 0;
  }
  #my-hand .card:first-child {
    margin-left: 0 !important;
  }
  #my-hand .card:hover {
    transform: translateY(-26px) scale(1.08);
    z-index: 80;
    box-shadow: -4px 16px 28px rgba(0,0,0,0.7), 0 0 16px rgba(250, 204, 21, 0.45);
  }
  #my-hand .card.selected {
    transform: translateY(-38px) scale(1.1) !important;
    z-index: 100 !important;
    border-color: #f59e0b !important;
    box-shadow: 0 0 0 3.5px #f59e0b, 0 20px 35px rgba(245, 158, 11, 0.6) !important;
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
    left: 4px;
    right: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 13px;
    line-height: 1;
  }
  .card.small .c-mini-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 22px;
    line-height: 1;
  }
  .card.small .c-mini-bot {
    position: absolute;
    bottom: 2px;
    left: 3px;
    right: 3px;
    font-size: 8px;
    font-weight: 800;
    text-align: center;
    background: rgba(0,0,0,0.08);
    border-radius: 3px;
    padding: 0.5px 0;
  }

  /* ACTION DOCK (ALWAYS 100% VISIBLE AT BOTTOM!) */
  #action-bar {
    grid-column: 1 / 4;
    grid-row: 5 / 6;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 7px;
    padding: 4px 12px;
    background: rgba(4, 20, 12, 0.94);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(250, 204, 21, 0.35);
    border-radius: 999px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.15);
    min-height: 40px;
    max-height: 44px;
    flex-shrink: 0;
    z-index: 50;
  }
  .btn-action {
    height: 32px;
    padding: 0 13px;
    font-size: 11.5px;
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
</style>
</head>
<body>

<div id="table">
  <!-- TOP HEADER HUD -->
  <div class="header-bar">
    <div class="header-top-row">
      <div class="header-brand">
        <span class="brand-logo">👑</span>
        <span id="hdr-title" class="header-title">REMI NUSANTARA 2D</span>
      </div>
      <div class="header-btn-group">
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
    <div id="hdr-status" class="status-notif">Selamat datang di Remi Nusantara 2D Royale!</div>
  </div>

  <!-- OPPONENT: TOP (Bot Siti) -->
  <div id="zone-top" class="zone-box">
    <div style="display:flex;align-items:center;justify-content:space-between;width:100%;padding:0 4px;">
      <div class="player-title" id="top-title">Bot Siti</div>
      <div class="cards-row opp-cards" id="top-cards"></div>
    </div>
    <div id="top-melds-label" style="font-size:10px;color:#fde047;font-weight:700;margin-top:2px;">Kartu Jadi:</div>
    <div class="meld-container" id="top-melds"><div class="meld-empty-hint">Belum ada kartu jadi</div></div>
  </div>

  <!-- OPPONENT: LEFT (Bot Budi) -->
  <div id="zone-left" class="zone-box">
    <div class="player-title" id="left-title">Bot Budi</div>
    <div class="cards-row opp-cards" id="left-cards"></div>
    <div id="left-melds-label" style="font-size:10px;color:#fde047;font-weight:700;margin-top:4px;">Kartu Jadi:</div>
    <div class="meld-container" id="left-melds"><div class="meld-empty-hint">Belum ada kartu jadi</div></div>
  </div>

  <!-- CENTER AREA: THE ARENA (Pak Kartu + Wild + BIG DISCARD RAIL) -->
  <div id="zone-center">
    <!-- PAK KARTU -->
    <div id="pak-box" onclick="sendAction('DRAW_DECK')" draggable="true" ondragstart="onPakDragStart(event)" title="Klik atau Tarik ke tangan untuk ambil kartu">
      <div style="font-weight:900;color:#fde047;font-size:11px;letter-spacing:0.5px;">PAK KARTU</div>
      <div id="pak-count" style="font-size:22px;font-weight:900;margin:3px 0;font-variant-numeric:tabular-nums;">(24)</div>
      <div style="font-size:8.5px;color:#cbd5e1;opacity:0.85;">KLIK / TARIK</div>
    </div>

    <!-- BUKAAN WILD -->
    <div id="wild-box">
      <div id="wild-title" style="font-weight:900;color:#e9d5ff;font-size:10px;text-align:center;margin-bottom:2px;letter-spacing:0.3px;">BUKAAN WILD</div>
      <div id="wild-card-slot"></div>
    </div>

    <!-- PROMINENT DISCARD RAIL -->
    <div id="discard-rail" ondragover="onDiscardDragOver(event)" ondragleave="onDiscardDragLeave(event)" ondrop="onDiscardDrop(event)">
      <div id="disc-title" style="font-size:10.5px;font-weight:800;color:#fde047;margin-bottom:3px;letter-spacing:0.3px;">
        TUMPUKAN BUANGAN (Ambil #1-#7 & Otomatis Jadi):
      </div>
      <div id="disc-cards"></div>
    </div>
  </div>

  <!-- OPPONENT: RIGHT (Bot Agus) -->
  <div id="zone-right" class="zone-box">
    <div class="player-title" id="right-title">Bot Agus</div>
    <div class="cards-row opp-cards" id="right-cards"></div>
    <div id="right-melds-label" style="font-size:10px;color:#fde047;font-weight:700;margin-top:4px;">Kartu Jadi:</div>
    <div class="meld-container" id="right-melds"><div class="meld-empty-hint">Belum ada kartu jadi</div></div>
  </div>

  <!-- PLAYER ZONE (Anda / Player 1) -->
  <div id="zone-bottom" ondragover="onHandDragOver(event)" ondragleave="onHandDragLeave(event)" ondrop="onHandDrop(event)">
    <div style="display:flex;align-items:center;justify-content:space-between;width:100%;padding:0 4px;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span id="my-turn-badge" class="turn-badge" style="display:none;">GILIRAN ANDA!</span>
        <span id="my-info" class="player-title" style="font-size:12px;color:#facc15;">Anda (Player 1)</span>
      </div>
      <div id="my-seri-badge" style="font-size:10px;font-weight:800;color:#f87171;background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:999px;">
        BELUM ADA SERI MIN 3 (AWAS TERBAKAR!)
      </div>
    </div>

    <!-- PLAYER MELDS -->
    <div id="my-melds" class="meld-container" style="width:100%;">
      <div class="meld-empty-hint">Belum ada kartu jadi di meja • Wajib min 1 Seri Urut agar aman</div>
    </div>

    <!-- PLAYER HAND (50% OVERLAPPING FAN) -->
    <div id="my-hand"></div>
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
    <button class="btn-action btn-sort" onclick="sendAction('SORT_RANK')" title="Urutkan kartu tangan berdasarkan Angka (S)">
      🔢 URUT ANGKA (S)
    </button>
    <button class="btn-action btn-sort" onclick="sendAction('SORT_SUIT')" title="Urutkan kartu tangan berdasarkan Kembang / Warna (F)">
      ♠️ URUT KEMBANG (F)
    </button>
  </div>
</div>

<!-- ROUND COUNTDOWN OVERLAY -->
<div id="round-countdown-overlay">
  ⏳ Ronde berikutnya dimulai dalam: <span id="countdown-sec" style="font-size:18px;color:#fff;">5</span> detik...
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
      <div class="setting-label">TIMER PER GILIRAN: <span id="timer-badge-active" style="color:#38bdf8;font-weight:800;">30 Detik</span></div>
      <div id="timer-pills" class="pills-container">
        <button class="pill-btn" onclick="selectConfig('timer', 0)">Tanpa Timer (Santai)</button>
        <button class="pill-btn" onclick="selectConfig('timer', 15)">15s (Blitz)</button>
        <button class="pill-btn active" onclick="selectConfig('timer', 30)">30s (Standar)</button>
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

<script>
const urlParams = new URLSearchParams(window.location.search);
const mySeat = parseInt(urlParams.get('seat') || '0', 10);
let selectedCards = new Set();
let latestState = null;
let currentDrag = null;
let initialClaimDone = false;

const SUIT_ICON = { 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' };

let currentConfig = {
  players: 4,
  score: 1500,
  timer: 30,
  botDelay: 1.0,
  playerName: 'Anda (Player 1)'
};

function groupBadge(c) {
  if (c.rank === 'JOKER' || c.is_wild) return 'WILD';
  if (c.rank === 'A') return '+15';
  if (['K','Q','J','10'].includes(c.rank)) return '+10';
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
    ${!isWild && pointText ? `<div class="c-point-pill">${pointText}</div>` : ''}
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

function renderOpponentZone(prefix, p, isTurn, showFace, targetScore, leaderSeat) {
  const zoneEl = document.getElementById(`zone-${prefix}`);
  const titleEl = document.getElementById(`${prefix}-title`);
  const cardsEl = document.getElementById(`${prefix}-cards`);
  const meldsLabelEl = document.getElementById(`${prefix}-melds-label`);
  const meldsEl = document.getElementById(`${prefix}-melds`);

  if (!zoneEl || !p) return;
  zoneEl.className = 'zone-box' + (isTurn ? ' zone-active' : '');

  const badgeHTML = isTurn ? `<span class="turn-badge">⏳ SEDANG JALAN...</span> ` : '';
  const isLeader = (leaderSeat !== null && leaderSeat !== undefined && p.seat === leaderSeat && (latestState && (latestState.round_number > 1 || p.total_score > 0)));
  const leaderTag = isLeader ? ' <span style="color:#facc15;font-size:0.85em;">[👑 SKOR TERTINGGI]</span>' : '';
  const burnTag = p.burned_last_round ? ' <span style="color:#f87171;">[TERBAKAR!]</span>' : '';

  if (titleEl) {
    titleEl.innerHTML = `${badgeHTML}${p.name}${leaderTag}${burnTag} • Skor: ${p.total_score}/${targetScore} (${p.last_round_score >= 0 ? '+' : ''}${p.last_round_score})`;
  }

  let handHTML = '';
  if (showFace && p.hand && p.hand.length) {
    handHTML = p.hand.map(c => renderCardHTML(c, { small: true })).join('');
  } else {
    for (let i = 0; i < p.hand_count; i++) {
      handHTML += `<div class="card-back"></div>`;
    }
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
  if (!initialClaimDone) {
    initialClaimDone = true;
    if (mySeat > 0 && st.players && st.players[mySeat] && st.players[mySeat].is_bot) {
      const storedName = localStorage.getItem('remi_player_name') || `Teman (P${mySeat + 1})`;
      sendAction('CLAIM_SEAT', { seat: mySeat, player_name: storedName });
    }
  }

  const wRank = st.wildcard_rank || '-';
  const isPaused = Boolean(st.is_paused);
  const timerStr = isPaused
    ? '⏸️ PAUSED'
    : ((st.turn_timer_sec <= 0)
      ? '∞ (Unlimited)'
      : ((st.phase === 'TURN_DRAW' || st.phase === 'TURN_MELD_DISCARD') ? Math.ceil(st.turn_remaining_sec) + 's' : '--'));

  document.getElementById('hdr-title').textContent =
    `REMI NUSANTARA 2D | Room: #${st.room_code} | Ronde: ${st.round_number} | WILD: JOKER + '${wRank}' | Target: ${st.target_score} | ⏱️ TIMER: ${timerStr}`;

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
  const isMyTurn = (st.current_turn_seat === mySeat) && (st.phase === 'TURN_DRAW' || st.phase === 'TURN_MELD_DISCARD');
  const p0 = (st.players && st.players[mySeat]) ? st.players[mySeat] : null;
  const canTutup = Boolean(p0 && p0.can_tutup_tangan);
  const tutupCardId = p0 ? (p0.tutup_discard_id || '') : '';

  const btnTutup = document.getElementById('btn-tutup-tangan');
  if (btnTutup) {
    if (canTutup && isMyTurn && st.phase === 'TURN_MELD_DISCARD') {
      btnTutup.classList.add('glow-tutup');
      btnTutup.title = `KARTU LENGKAP! Klik untuk Tutup Tangan (+250 Poin) dengan membuang ${tutupCardId}!`;
    } else {
      btnTutup.classList.remove('glow-tutup');
      btnTutup.title = "Tutup Tangan langsung dari tangan (+250 Poin) (T)";
    }
  }

  const countdownOverlay = document.getElementById('round-countdown-overlay');
  if (countdownOverlay) {
    if (st.phase === 'ROUND_OVER' && st.round_over_timer !== undefined && st.round_over_timer !== null) {
      countdownOverlay.style.display = 'block';
      const secLeft = Math.max(0, Math.ceil(st.round_over_timer));
      document.getElementById('countdown-sec').textContent = secLeft;
    } else {
      countdownOverlay.style.display = 'none';
    }
  }

  if (bannerEl) {
    if (isPaused) {
      bannerEl.className = 'turn-banner turn-opp';
      bannerEl.textContent = '⏸️ PERMAINAN DIHENTIKAN SEMENTARA (PAUSED) - TEKAN ESC UNTUK LANJUT ⏸️';
    } else if (st.phase === 'GAME_OVER') {
      bannerEl.className = 'turn-banner turn-my';
      bannerEl.textContent = '🏆 PERMAINAN SELESAI! PEMENANG TARGET SKOR TELAH DITENTUKAN! 🏆';
    } else if (st.phase === 'ROUND_OVER') {
      bannerEl.className = 'turn-banner turn-opp';
      bannerEl.textContent = '🏁 RONDE SELESAI! Mempersiapkan ronde berikutnya...';
    } else if (isMyTurn) {
      bannerEl.className = 'turn-banner turn-my';
      if (st.phase === 'TURN_DRAW') {
        bannerEl.textContent = '★ GILIRAN ANDA! [TAHAP 1: AMBIL KARTU] -> Klik PAK KARTU atau Buangan #1-#7 ★';
      } else {
        if (canTutup) {
          bannerEl.textContent = `★ GILIRAN ANDA! KARTU JADI LENGKAP! KLIK 'TUTUP TANGAN +250 (T)' (Buang ${tutupCardId})! ★`;
        } else {
          bannerEl.textContent = "★ GILIRAN ANDA! [TAHAP 2: SUSUN / BUANG] -> Klik 'AUTO TURUN (A)', 'TURUNKAN (M)', atau 'BUANG (B)' ★";
        }
      }
    } else {
      bannerEl.className = 'turn-banner turn-opp';
      const currP = (st.players && st.players[st.current_turn_seat]) ? st.players[st.current_turn_seat] : null;
      const currName = currP ? currP.name : `Pemain ${st.current_turn_seat + 1}`;
      bannerEl.textContent = `Giliran ${currName} sedang berjalan... Harap tunggu.`;
    }
  }

  const notifEl = document.getElementById('hdr-status');
  if (notifEl && (st.last_event || st.status_message)) notifEl.textContent = st.last_event || st.status_message;

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
  if (wildSlot && wildCard) {
    wildSlot.innerHTML = renderCardHTML(wildCard);
  }

  // Render Discard Rail (Single horizontal row!)
  const discContainer = document.getElementById('disc-cards');
  if (discContainer) {
    if (!discards || !discards.length) {
      discContainer.innerHTML = '<div style="font-size:11px;color:rgba(255,255,255,0.4);font-style:italic;padding:4px;">(Tumpukan buangan masih kosong)</div>';
    } else {
      const totalDisc = discards.length;
      discContainer.innerHTML = discards.map((c, i) => {
        const revIdx = totalDisc - 1 - i;
        const isTakeable = (revIdx < 7);
        const badgeText = isTakeable ? `AMBIL #${revIdx + 1}` : `#${revIdx + 1}`;
        const canClick = isMyTurn && st.phase === 'TURN_DRAW' && isTakeable;
        return renderCardHTML(c, {
          badge: badgeText,
          onclick: canClick ? `takeDiscard(${i})` : '',
          draggable: canClick,
          ondragstart: canClick ? `onDiscardDragStart(event, ${i})` : '',
          hint: isTakeable ? `Ambil kartu buangan #${revIdx + 1} & langsung otomatis turun!` : 'Kartu buangan terkunci'
        });
      }).join('');
    }
  }

  // Render Opponents
  const n = st.players.length;
  if (n === 2) {
    renderOpponentZone('top', st.players[(mySeat + 1) % n], st.current_turn_seat === (mySeat + 1) % n, st.show_bot_hands, st.target_score, leaderSeat);
    document.getElementById('zone-left').style.display = 'none';
    document.getElementById('zone-right').style.display = 'none';
  } else if (n === 3) {
    renderOpponentZone('left', st.players[(mySeat + 1) % n], st.current_turn_seat === (mySeat + 1) % n, st.show_bot_hands, st.target_score, leaderSeat);
    renderOpponentZone('top', st.players[(mySeat + 2) % n], st.current_turn_seat === (mySeat + 2) % n, st.show_bot_hands, st.target_score, leaderSeat);
    document.getElementById('zone-left').style.display = 'flex';
    document.getElementById('zone-right').style.display = 'none';
  } else {
    document.getElementById('zone-left').style.display = 'flex';
    document.getElementById('zone-right').style.display = 'flex';
    renderOpponentZone('left', st.players[(mySeat + 1) % n], st.current_turn_seat === (mySeat + 1) % n, st.show_bot_hands, st.target_score, leaderSeat);
    renderOpponentZone('top', st.players[(mySeat + 2) % n], st.current_turn_seat === (mySeat + 2) % n, st.show_bot_hands, st.target_score, leaderSeat);
    renderOpponentZone('right', st.players[(mySeat + 3) % n], st.current_turn_seat === (mySeat + 3) % n, st.show_bot_hands, st.target_score, leaderSeat);
  }

  // Render Player Zone
  if (p0) {
    const isLeader = (leaderSeat !== null && leaderSeat !== undefined && mySeat === leaderSeat && (st.round_number > 1 || p0.total_score > 0));
    const leaderTag = isLeader ? ' [👑 SKOR TERTINGGI]' : '';
    const burnTag = p0.burned_last_round ? ' [TERBAKAR!]' : '';
    document.getElementById('my-info').innerHTML =
      `Kursi ${mySeat + 1} | ${p0.name}${leaderTag}${burnTag} | Skor: ${p0.total_score} / ${st.target_score} (${p0.last_round_score >= 0 ? '+' : ''}${p0.last_round_score}) <span style="font-size:10px;color:#38bdf8;cursor:pointer;text-decoration:underline;" onclick="changePlayerNamePrompt()">✎ Ganti Nama</span>`;

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

    const myMeldsEl = document.getElementById('my-melds');
    if (myMeldsEl) myMeldsEl.innerHTML = renderMeldsHTML(p0.melds, false);

    // Render 50% Overlapping Hand
    const myHandEl = document.getElementById('my-hand');
    if (myHandEl) {
      myHandEl.innerHTML = (p0.hand || []).map(c => {
        const isSel = selectedCards.has(c.id);
        const canClick = isMyTurn && (st.phase === 'TURN_MELD_DISCARD');
        return renderCardHTML(c, {
          selected: isSel,
          onclick: `toggleCard('${c.id}')`,
          onrightclick: `quickDiscard('${c.id}')`,
          draggable: canClick,
          ondragstart: `onHandCardDragStart(event, '${c.id}')`,
          hint: 'Klik untuk pilih; Geser / Klik Kanan untuk Buang (B)'
        });
      }).join('');
    }
  }
}

function toggleCard(cardId) {
  if (selectedCards.has(cardId)) selectedCards.delete(cardId);
  else selectedCards.add(cardId);
  if (latestState) updateUI(latestState);
}

function quickDiscard(cardId) {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
  if (!isMyTurn) return;
  selectedCards.clear();
  sendAction('DISCARD', { card_id: cardId });
}

function meldSelected() {
  if (!selectedCards.size) {
    alert("Pilih minimal 3 kartu di tangan untuk diturunkan!");
    return;
  }
  sendAction('MELD_HAND', { card_ids: Array.from(selectedCards) });
  selectedCards.clear();
}

function discardSelected() {
  if (selectedCards.size !== 1) {
    alert("Pilih tepat 1 kartu di tangan untuk dibuang!");
    return;
  }
  const cid = Array.from(selectedCards)[0];
  selectedCards.clear();
  sendAction('DISCARD', { card_id: cid });
}

function declareTutupTangan() {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_MELD_DISCARD');
  if (!isMyTurn) {
    alert("Hanya bisa Tutup Tangan saat giliran Anda di tahap susun/buang!");
    return;
  }
  const p0 = latestState.players[mySeat];
  if (!p0 || !p0.can_tutup_tangan) {
    alert("Kartu Anda belum memenuhi syarat Tutup Tangan murni! Semua sisa kartu di tangan harus bisa disusun menjadi Seri/Kembar valid (dengan sisa 1 kartu buang).");
    return;
  }
  selectedCards.clear();
  sendAction('TUTUP_TANGAN');
}

function takeDiscard(idx) {
  sendAction('TAKE_DISCARD', { index: idx, discard_index: idx });
}

async function sendAction(action, data = {}) {
  try {
    data.action = action;
    data.seat = mySeat;
    const res = await fetch(`/api/action?act=${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const st = await res.json();
    if (st && st.state) updateUI(st.state);
  } catch (e) {
    console.error("Action error:", e);
  }
}

function togglePause() {
  sendAction('TOGGLE_PAUSE');
}

// Drag & Drop
function onPakDragStart(e) {
  if (!latestState) return;
  const isMyTurn = (latestState.current_turn_seat === mySeat) && (latestState.phase === 'TURN_DRAW');
  if (!isMyTurn) { e.preventDefault(); return; }
  currentDrag = { type: 'PAK' };
  e.dataTransfer.setData('text/plain', 'PAK');
}

function onDiscardDragStart(e, idx) {
  currentDrag = { type: 'DISCARD', idx: idx };
  e.dataTransfer.setData('text/plain', 'DISCARD_' + idx);
}

function onHandCardDragStart(e, cardId) {
  currentDrag = { type: 'HAND', cardId: cardId };
  e.dataTransfer.setData('text/plain', cardId);
}

function onDiscardDragOver(e) {
  if (currentDrag && currentDrag.type === 'HAND') {
    e.preventDefault();
    document.getElementById('discard-rail').style.borderColor = '#4ade80';
  }
}

function onDiscardDragLeave(e) {
  document.getElementById('discard-rail').style.borderColor = 'rgba(250, 204, 21, 0.4)';
}

function onDiscardDrop(e) {
  e.preventDefault();
  document.getElementById('discard-rail').style.borderColor = 'rgba(250, 204, 21, 0.4)';
  if (currentDrag && currentDrag.type === 'HAND') {
    const cid = currentDrag.cardId;
    currentDrag = null;
    selectedCards.clear();
    sendAction('DISCARD', { card_id: cid });
  }
}

function onHandDragOver(e) {
  if (currentDrag && (currentDrag.type === 'PAK' || currentDrag.type === 'DISCARD')) {
    e.preventDefault();
    document.getElementById('zone-bottom').style.borderColor = '#4ade80';
  }
}

function onHandDragLeave(e) {
  document.getElementById('zone-bottom').style.borderColor = 'rgba(250, 204, 21, 0.4)';
}

function onHandDrop(e) {
  e.preventDefault();
  document.getElementById('zone-bottom').style.borderColor = 'rgba(250, 204, 21, 0.4)';
  if (currentDrag && currentDrag.type === 'PAK') {
    currentDrag = null;
    sendAction('DRAW_DECK');
  } else if (currentDrag && currentDrag.type === 'DISCARD') {
    const idx = currentDrag.idx;
    currentDrag = null;
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
  const current = (latestState && latestState.players[mySeat]) ? latestState.players[mySeat].name : 'Player 1';
  const newName = prompt("Ganti nama Anda:", current);
  if (newName && newName.trim()) {
    const clean = newName.trim();
    localStorage.setItem('remi_player_name', clean);
    sendAction('CHANGE_NAME', { seat: mySeat, name: clean });
  }
}

// Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'Escape') togglePause();
  else if (e.key === 'p' || e.key === 'P') openDashboard();
  else if (e.key === 'd' || e.key === 'D') sendAction('DRAW_DECK');
  else if (e.key === 'm' || e.key === 'M') meldSelected();
  else if (e.key === 'a' || e.key === 'A') sendAction('AUTO_MELD');
  else if (e.key === 't' || e.key === 'T') declareTutupTangan();
  else if (e.key === 'b' || e.key === 'B') discardSelected();
  else if (e.key === 's' || e.key === 'S') sendAction('SORT_RANK');
  else if (e.key === 'f' || e.key === 'F') sendAction('SORT_SUIT');
});

// Real-time Polling
setInterval(async () => {
  try {
    const res = await fetch(`/api/state?seat=${mySeat}`);
    const data = await res.json();
    if (data.state) updateUI(data.state);
  } catch (e) {}
}, 300);
</script>
</body>
</html>"""

def _format_state_dict(seat: int) -> dict:
    st = GAME.to_state_dict(viewer_seat=seat)
    st["host_ip"] = get_local_ip()
    st["server_port"] = 8080
    st["deck_count"] = st.get("draw_pile_count", 0)
    st["discards"] = st.get("discard_pile", [])
    st["wildcard_card"] = st.get("wildcard_indicator", None)
    st["last_event"] = st.get("status_message", "")
    st["leader_seat"] = st.get("highest_score_seat", 0)
    return st


class RemiWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            seat = int(qs.get("seat", ["0"])[0])
            with GAME_LOCK:
                st = _format_state_dict(seat)
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

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(raw)
        seat = int(payload.get("seat", qs.get("seat", ["0"])[0]))
        action = payload.get("action") or qs.get("act", [""])[0]

        with GAME_LOCK:
            if action == "CONFIGURE_AND_START":
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
            elif action == "CLAIM_SEAT":
                seat_idx = int(payload.get("seat", seat))
                name = payload.get("player_name", f"Teman (P{seat_idx + 1})")
                if 0 <= seat_idx < len(GAME.players):
                    GAME.players[seat_idx].is_bot = False
                    GAME.players[seat_idx].auto_pilot = False
                    GAME.players[seat_idx].name = name
                    GAME.status_message = f"{name} bergabung di Kursi {seat_idx + 1}!"
            elif action == "CHANGE_NAME":
                seat_idx = int(payload.get("seat", seat))
                name = payload.get("name", "").strip()
                if name and 0 <= seat_idx < len(GAME.players):
                    old_name = GAME.players[seat_idx].name
                    GAME.players[seat_idx].name = name
                    GAME.status_message = f"{old_name} mengubah nama menjadi {name}."
            elif action == "SET_BOT":
                seat_idx = int(payload.get("seat", seat))
                is_bot = bool(payload.get("is_bot", True))
                if 0 <= seat_idx < len(GAME.players):
                    GAME.players[seat_idx].is_bot = is_bot
                    GAME.players[seat_idx].auto_pilot = is_bot
                    st_str = "Bot" if is_bot else "Manusia"
                    GAME.status_message = f"Kursi {seat_idx + 1} diatur sebagai {st_str}."
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

            st = _format_state_dict(seat)

        self._send_json({"state": st})

    def _send_json(self, obj: dict):
        try:
            data = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
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
    run_web_server(port=8080, open_browser=True)
