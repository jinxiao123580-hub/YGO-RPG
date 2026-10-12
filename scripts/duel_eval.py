# -*- coding: utf-8 -*-
"""
duel_eval.py — 卡组强度人机内战评估
两台脚本脑 WindBot 通过本地 YGOSharp 服务器对打, 统计各套牌胜率。
前置: ygosharp 服务器已构建 (E:\\FUN\\YGO-RPG\\YGO\\ygosharp\\YGOSharp\\bin\\Release)

用法:
  python duel_eval.py list                  # 列出可评估套牌
  python duel_eval.py pair A B 2            # 套牌A vs B 打2局
  python duel_eval.py roundrobin 1 [n_decks]  # 前 n_decks 套全轮转各打 1 局
结果: E:/FUN/YGO-DATA/sources/eval_results.json + 控制台胜率表
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"E:\FUN\YGO-RPG\YGO")
SERVER_DIR = BASE / "ygosharp" / "YGOSharp" / "bin" / "Release"
WIND_DIR = BASE / "windbot-llm" / "bin" / "Release"
LOGS = Path(r"E:\FUN\YGO-DATA\sources\eval_logs")
RESULTS = Path(r"E:\FUN\YGO-DATA\sources\eval_results.json")
MANIFEST = Path(r"E:\FUN\YGO-DATA\content\meta_decks.json")
EXEC_ALIAS = {"Blue-Eyes": "BlueEyes"}  # manifest 名 -> WindBot 执行器名
GAME_TIMEOUT = 480  # 单局上限8分钟

MANIFEST = Path(r"E:\FUN\YGO-DATA\content\meta_decks.json")
EXEC_ALIAS = {"Blue-Eyes": "BlueEyes"}  # manifest 名 -> WindBot 执行器名


def kill_all():
    for n in ("YGOSharp.exe", "WindBot.exe"):
        subprocess.run(["taskkill", "/IM", n, "/F"], capture_output=True)
    time.sleep(1)


def play_one(exe_a, file_a, exe_b, file_b, tag):
    """打一局, 返回 'A'/'B'/'draw'/'timeout'"""
    kill_all()
    LOGS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [str(SERVER_DIR / "YGOSharp.exe"), "Config=server.conf"], cwd=str(SERVER_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    def bot(name, exe, deckfile, logf):
        exe = EXEC_ALIAS.get(exe, exe)
        return subprocess.Popen(
            [str(WIND_DIR / "WindBot.exe"), f"Name={name}", f"Deck={exe}", f"DeckFile={deckfile}",
             "Host=127.0.0.1", "Port=7911", "Version=4945", "Chat=False"],
            cwd=str(WIND_DIR),
            stdout=open(logf, "w", encoding="utf-8", errors="replace"),
            stderr=subprocess.STDOUT)
    botA = bot("EvalA", exe_a, file_a, LOGS / f"{tag}_a.log")
    time.sleep(4)
    botB = bot("EvalB", exe_b, file_b, LOGS / f"{tag}_b.log")
    try:
        server.wait(timeout=GAME_TIMEOUT)
    except subprocess.TimeoutExpired:
        kill_all()
        return "timeout"
    time.sleep(2)
    result = "draw"
    for who, bot in (("A", botA), ("B", botB)):
        try:
            log = (LOGS / f"{tag}_{who.lower()}.log").read_text(encoding="utf-8", errors="replace")
            m = re.search(r"\[对局结束\] vs \S+ -> (Win|Lose|Draw) \(turn=(\d+)\)", log)
            if m:
                if (m.group(1) == "Win" and who == "A") or (m.group(1) == "Lose" and who == "B"):
                    return "A"
                if (m.group(1) == "Win" and who == "B") or (m.group(1) == "Lose" and who == "A"):
                    return "B"
                result = "draw"
        except FileNotFoundError:
            pass
    return result


def load_decks():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {exe: v["file"] for exe, v in m.items()}


def record(exe_a, exe_b, outcome, turns=None):
    data = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    key = f"{exe_a}|{exe_b}"
    e = data.setdefault(key, {"a_win": 0, "b_win": 0, "draw": 0})
    if outcome == "A": e["a_win"] += 1
    elif outcome == "B": e["b_win"] += 1
    else: e["draw"] += 1
    RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def report():
    data = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    wins = {}
    games = {}
    for key, e in data.items():
        a, b = key.split("|")
        wins[a] = wins.get(a, 0) + e["a_win"]
        wins[b] = wins.get(b, 0) + e["b_win"]
        games[a] = games.get(a, 0) + e["a_win"] + e["b_win"] + e["draw"]
        games[b] = games.get(b, 0) + e["a_win"] + e["b_win"] + e["draw"]
    print(f"{'套牌':<16}{'胜':>4}{'局':>4}{'胜率':>8}")
    for exe in sorted(wins, key=lambda x: -wins[x] / max(1, games[x])):
        print(f"{exe:<16}{wins[exe]:>4}{games[exe]:>4}{wins[exe]/max(1,games[exe]):>8.0%}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    decks = load_decks()
    if cmd == "list":
        for exe, f in decks.items():
            print(f"{exe:14s} {f}")
    elif cmd == "pair":
        a, b, n = sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1
        for i in range(n):
            out = play_one(a, decks[a], b, decks[b], f"{a}_vs_{b}_{i}")
            record(a, b, out)
            print(f"[{a} vs {b}] 第{i+1}局 -> {out}", flush=True)
        report()
    elif cmd == "roundrobin":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else len(decks)
        names = list(decks)[:limit]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                for k in range(n):
                    out = play_one(a, decks[a], b, decks[b], f"{a}_vs_{b}_{k}")
                    record(a, b, out)
                    print(f"[{a} vs {b}] -> {out}", flush=True)
        report()
    elif cmd == "report":
        report()


if __name__ == "__main__":
    main()
