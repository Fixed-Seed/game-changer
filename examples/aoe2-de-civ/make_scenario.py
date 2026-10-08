"""Scenarios for testing / the demo: the civ of civ.py (in its slot, 36) vs the Franks.

    python make_scenario.py test              # units + buildings placed, nothing scripted
    python make_scenario.py demo              # the demo video's map: the city, the army, the Franks, triggers
    python make_scenario.py bisect            # two partial demos, for finding which part crashes the game
    python make_scenario.py demo --install    # ... and copy it into <profile>/resources/_common/scenario

Reads <out>/ids.json (the new unit and tech ids, from build_mod.py) and writes <out>/scenarios/. The
new units only exist when the lobby runs the scenario with the data mod: Skirmish, Data Mod: <mod>,
Game Mode: Custom Scenario.
"""
import argparse
import json
import shutil
from pathlib import Path

from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario

import civ as C
from aoe2paths import DEFAULT_BUILD, find_profile

ENEMY = 2   # Franks
KNIGHT, CROSSBOW, PIKE, CASTLE, WONDER, VILLAGER, TC = 38, 24, 358, 82, 276, 83, 109
IDS, WRITTEN = {}, []
OUT = DEFAULT_BUILD / "scenarios"


def load(out):
    """build_mod.py's ids -> the module-level ids the scenarios use."""
    global SF, ROBO, ROBO_E, DRONE, UT2
    IDS.update(json.load(open(out / "ids.json")))
    SF = IDS["NEW"]
    ROBO, ROBO_E, DRONE = IDS[C.UNITS[0]["id"]], IDS[C.UNITS[0]["elite"]["id"]], IDS[C.UNITS[1]["id"]]
    UT2 = IDS[C.UNIQUE_TECHS[1]["key"]]   # the Imperial unique tech (Move Fast and Break Things)


def write(sc, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.aoe2scenario"
    sc.write_to_file(str(path))
    WRITTEN.append(path)
    print("wrote", path)


def base(size=80):
    sc = AoE2DEScenario.from_default()
    mm = sc.map_manager
    mm.map_size = size
    pm = sc.player_manager
    pm.active_players = 2
    pm.players[PlayerId.ONE].civilization = SF
    pm.players[PlayerId.TWO].civilization = ENEMY
    for p in (PlayerId.ONE, PlayerId.TWO):
        pm.players[p].food = pm.players[p].wood = pm.players[p].gold = pm.players[p].stone = 2000
    return sc


def test():
    sc = base()
    um = sc.unit_manager
    add = lambda p, u, x, y, r=0: game_changer.add_unit(p, u, x + 0.5, y + 0.5, rotation=r)
    add(PlayerId.ONE, WONDER, 20, 20)
    add(PlayerId.ONE, CASTLE, 30, 14)
    for i in range(4): add(PlayerId.ONE, ROBO, 30 + 2 * i, 26)
    for i in range(3): add(PlayerId.ONE, ROBO_E, 30 + 2 * i, 29)
    for i in range(5): add(PlayerId.ONE, DRONE, 30 + 2 * i, 32)
    for i in range(3): add(PlayerId.ONE, VILLAGER, 24 + i, 28)
    add(PlayerId.TWO, CASTLE, 60, 60)
    for i in range(5): add(PlayerId.TWO, KNIGHT, 50 + 2 * i, 44)
    for i in range(5): add(PlayerId.TWO, CROSSBOW, 50 + 2 * i, 48)
    write(sc, "sf_test")


HOUSE, MARKET, UNIV, SMITH, MONK, FARM, TOWER, BARRACKS, STABLE, LONGSWORD, OAK, PALM = 70, 84, 209, 103, 104, 50, 79, 12, 101, 77, 349, 351


def demo(parts=("town", "army", "enemy", "forest", "triggers"), name="sf_demo"):
    """The demo video's scenario: timings in game seconds (the lobby runs it at Normal speed).
    parts: which sections to include (bisecting crashes)."""
    sc = base(100)
    um = sc.unit_manager
    P1, P2, GAIA = PlayerId.ONE, PlayerId.TWO, PlayerId.GAIA
    add = lambda p, u, x, y, r=0: game_changer.add_unit(p, u, x + 0.5, y + 0.5, rotation=r)
    # --- San Francisco
    if "town" not in parts: add = (lambda real: (lambda p, u, x, y, r=0: real(p, u, x, y, r) if u in (ROBO_E, DRONE) or p != P1 else None))(add)
    add(P1, WONDER, 28, 72)
    add(P1, CASTLE, 40, 63)
    add(P1, TC, 19, 62)
    add(P1, MARKET, 34, 81)
    add(P1, UNIV, 43, 74)
    add(P1, MONK, 21, 79)
    add(P1, SMITH, 47, 67)
    for x, y in ((15, 70), (15, 74), (17, 83), (26, 86), (30, 87), (48, 79), (51, 73), (38, 57), (44, 58)):
        add(P1, HOUSE, x, y)
    for x, y in ((12, 58), (12, 62), (16, 56)):
        add(P1, FARM, x, y)
    for x, y in ((23, 66), (33, 66), (23, 77), (33, 77), (36, 70), (20, 70), (30, 61), (26, 61)):
        add(GAIA, PALM, x, y)
    for i, (x, y) in enumerate(((13, 59), (13, 63), (17, 57), (22, 65), (24, 64))):
        add(P1, VILLAGER, x, y)
    # --- the army
    for r in range(3):
        for c in range(4):
            add(P1, ROBO_E, 50 + 2 * c, 54 + 2 * r, r=2)
    for c in range(5):
        for r in range(2):
            add(P1, DRONE, 51 + 2 * c, 61 + 2 * r, r=2)
    # --- the Franks
    add0 = add
    if "enemy" not in parts: add = lambda p, u, x, y, r=0: None if p == P2 else add0(p, u, x, y, r)
    for i in range(6): add(P2, KNIGHT, 70 + 2 * i, 38, r=6)
    for i in range(8): add(P2, CROSSBOW, 69 + 2 * i, 34, r=6)
    for i in range(6): add(P2, LONGSWORD, 70 + 2 * i, 42, r=6)
    for x, y in ((78, 20), (82, 18), (86, 22), (76, 26), (88, 28)):
        add(P2, HOUSE, x, y)
    add(P2, TOWER, 80, 30); add(P2, TOWER, 90, 20)
    add(P2, BARRACKS, 84, 26)
    add(P2, STABLE, 80, 14)
    # --- forests at the edges
    add = add0
    if "forest" not in parts: add = lambda p, u, x, y, r=0: None
    for x in range(2, 10):
        for y in range(10, 45, 1):
            if (x * 7 + y * 3) % 4: add(GAIA, OAK, x, y)
    for x in range(88, 98):
        for y in range(55, 90):
            if (x * 5 + y * 3) % 4: add(GAIA, OAK, x, y)

    tm = sc.trigger_manager
    if "triggers" not in parts:
        write(sc, name)
        return

    def at(t, name):
        trig = tm.add_trigger(name)
        trig.new_condition.timer(timer=t)
        return trig

    t = tm.add_trigger("start")
    t.new_effect.set_player_visibility(source_player=P1, target_player=P2, visibility_state=0)
    t.new_effect.set_player_visibility(source_player=P1, target_player=GAIA, visibility_state=0)
    t.new_effect.change_view(source_player=P1, location_x=29, location_y=73, scroll=0)
    at(6, "to army").new_effect.change_view(source_player=P1, location_x=55, location_y=58, scroll=1)
    go = at(9, "attack")
    go.new_effect.attack_move(object_list_unit_id=ROBO_E, source_player=P1, area_x1=45, area_y1=50, area_x2=62, area_y2=62, location_x=73, location_y=40)
    at(10, "drones").new_effect.attack_move(object_list_unit_id=DRONE, source_player=P1, area_x1=45, area_y1=58, area_x2=65, area_y2=68, location_x=71, location_y=43)
    at(15, "battle").new_effect.change_view(source_player=P1, location_x=66, location_y=46, scroll=1)
    at(24, "battle2").new_effect.change_view(source_player=P1, location_x=72, location_y=40, scroll=1)
    at(30, "series b").new_effect.research_technology(source_player=P1, technology=UT2, force_research_technology=1)
    b = at(34, "break things")
    b.new_effect.attack_move(object_list_unit_id=ROBO_E, source_player=P1, area_x1=0, area_y1=0, area_x2=99, area_y2=99, location_x=82, location_y=22)
    b.new_effect.attack_move(object_list_unit_id=DRONE, source_player=P1, area_x1=0, area_y1=0, area_x2=99, area_y2=99, location_x=80, location_y=26)
    at(40, "village").new_effect.change_view(source_player=P1, location_x=80, location_y=26, scroll=1)
    at(52, "village2").new_effect.change_view(source_player=P1, location_x=83, location_y=22, scroll=1)
    at(74, "home").new_effect.change_view(source_player=P1, location_x=29, location_y=73, scroll=1)
    write(sc, name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["test", "demo", "bisect"])
    ap.add_argument("--out", default=str(DEFAULT_BUILD), help="build folder with ids.json; scenarios go to <out>/scenarios")
    ap.add_argument("--install", action="store_true", help="also copy the scenario(s) into <profile>/resources/_common/scenario")
    ap.add_argument("--profile", help="for --install: ...\\Games\\Age of Empires 2 DE\\<steam id>. Default: found, or $AOE2DE_PROFILE")
    a = ap.parse_args()
    out = Path(a.out)
    profile = find_profile(a.profile) if a.install else None
    load(out)
    OUT = out / "scenarios"
    if a.what == "bisect":
        demo(("town", "army", "enemy", "forest"), "sf_b1")          # no triggers
        demo(("army", "triggers"), "sf_b2")                         # just the armies + triggers
    else:
        {"test": test, "demo": demo}[a.what]()
    if profile:
        dst = profile / "resources/_common/scenario"
        dst.mkdir(parents=True, exist_ok=True)
        for p in WRITTEN:
            shutil.copy(p, dst / p.name)
            print("installed", dst / p.name)
