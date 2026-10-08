"""Build the "San Franciscans" civilization data mod for AoE2 DE. The civ itself is defined in civ.py.

    python build_mod.py                  # -> build/SanFranciscans/ (a local mod folder) + build/ids.json
    python build_mod.py --install        # ... and copy it into <profile>/mods/local, registered in mod-status.json
    python build_mod.py --game "D:\\SteamLibrary\\steamapps\\common\\AoE2DE" --out /tmp/aoe2build

It takes over the Burgundians' slot (36), built on the Britons' base tech tree:
  * Robotaxi / Elite Robotaxi - unique Castle unit (fast self-driving car that rams), FixedSeed art -> 3D -> sprites
  * Delivery Drone - Archery Range unit from the Castle Age
  * Transamerica Pyramid wonder
  * bonuses: villagers work 10% faster ("hustle culture"), cavalry +10% speed ("autonomous"),
    Universities work 40% faster; team bonus: Universities +20%
  * unique techs: Series A Funding (Castle: +600 gold), Move Fast and Break Things (Imperial:
    Robotaxis +25% speed and +8 attack vs buildings)
New units, graphics, techs and effects are appended to the stock data and only the one slot changes,
so the other civs are untouched. A mod with a .dat is a data mod: it only applies when picked in the
skirmish lobby's "Data Mod" dropdown. Sprites come from <out>/graphics (make_sprites.py, make_wonder.py).
"""
import argparse
import copy
import dataclasses
import json
import shutil
from pathlib import Path

from genieutils.datfile import DatFile
from genieutils.effect import Effect, EffectCommand
from genieutils.tech import ResearchLocation, ResearchResourceCost
from genieutils.unit import ResourceCost, TrainLocation

import civ as C
from aoe2paths import DEFAULT_BUILD, asset, find_game, find_profile

AGES = {"feudal": (101, 2), "castle": (102, 3), "imperial": (103, 4)}   # age tech id, tech-tree "Age ID"
CASTLE, IMPERIAL = AGES["castle"][0], AGES["imperial"][0]
WONDER_UNIT = 276


def add_graphic(d, template_id, file_name, name, frames, duration, angles=16):
    g = copy.deepcopy(d.graphics[template_id])
    gid = len(d.graphics)
    g.id, g.name, g.file_name = gid, name, file_name
    g.frame_count, g.angle_count, g.frame_duration = frames, angles, duration
    g.mirroring_mode = 0   # all 16 angles are rendered, none mirrored
    g.slp = -1
    g.deltas = []
    # angle sounds (when used) hold one entry per angle: keep the template's angle count
    assert not g.angle_sounds_used or len(g.angle_sounds) == angles, (name, len(g.angle_sounds), angles)
    d.graphics.append(g)
    return gid


def add_effect(d, name, cmds):
    d.effects.append(Effect(name=name, effect_commands=[EffectCommand(*c) for c in cmds]))
    return len(d.effects) - 1


def add_tech(d, template_id, name, civ, effect_id, required, location=None, cost=None, lang=None):
    t = copy.deepcopy(d.techs[template_id])
    t.name, t.civ, t.effect_id = name, civ, effect_id
    req = list(required) + [-1] * (6 - len(required))
    t.required_techs = tuple(req)
    t.required_tech_count = sum(1 for r in required if r >= 0)
    if location is not None:
        t.research_locations = [ResearchLocation(*location)] + list(t.research_locations[1:])
    if cost is not None:
        c = [ResearchResourceCost(type=r, amount=a, flag=1) for r, a in cost]
        c += [ResearchResourceCost(type=-1, amount=0, flag=0)] * (3 - len(c))
        t.resource_costs = tuple(c)
    if lang is not None:
        t.language_dll_name = lang
        t.language_dll_description = lang + 1000
        t.language_dll_help = lang + 100000       # stock pattern (e.g. Hamask: 507019 / 508019 / 607019 / 657019)
        t.language_dll_tech_tree = lang + 150000
    d.techs.append(t)
    return len(d.techs) - 1


def template_graphics(base, unit_id):
    """The template unit's graphics records per animation: the new ones copy their settings."""
    u = base.units[unit_id]
    return {"idleA": u.standing_graphic[0], "walkA": u.dead_fish.walking_graphic, "attackA": u.type_50.attack_graphic,
            "deathA": u.dying_graphic, "decayA": base.units[u.dead_unit_id].standing_graphic[0]}


def make_avail_tech(d, civ_id, unit_id):
    """The stock tech that enables a civ's unique unit (Britons: 263 "Longbow (make avail)")."""
    for i, t in enumerate(d.techs):
        if t.civ == civ_id and 0 <= t.effect_id < len(d.effects) and \
                any(c.type == 2 and c.a == unit_id for c in d.effects[t.effect_id].effect_commands):
            return i
    raise LookupError(f"no tech enables unit {unit_id} for civ {civ_id}")


def variants(u):
    """A unit spec and, for the unique unit, its elite version (the elite dict overrides the base stats)."""
    return [u] + ([dict(u, **u["elite"])] if "elite" in u else [])


def make_unit(base, spec, uid, dead_id, G):
    """A copy of the template unit with the spec's stats and graphics; only the stats given change."""
    u = copy.deepcopy(base.units[spec["template"]])
    u.id = u.copy_id = u.base_id = uid
    u.name = spec["internal"]
    lang = spec["string"]
    u.language_dll_name, u.language_dll_creation, u.language_dll_help, u.language_dll_hotkey_text = lang, lang + 1000, 100000 + lang, 150000 + lang
    u.icon_id = spec["panel_icon"]
    for key, attr in (("hp", "hit_points"), ("speed", "speed"), ("los", "line_of_sight")):
        if key in spec:
            setattr(u, attr, spec[key])
    g = {anim: G[f"{spec['key']}_{anim}"] for anim in spec["anims"]}
    u.standing_graphic = (g["idleA"], -1)
    u.dying_graphic = g["deathA"]
    u.dead_fish.walking_graphic = g["walkA"]
    u.dead_fish.running_graphic = g["walkA"]
    u.dead_unit_id = dead_id
    t = u.type_50
    t.attack_graphic = g["attackA"]
    if "attack" in spec:   # melee (class 4)
        t.attacks = [dataclasses.replace(a, amount=spec["attack"]) if a.class_ == 4 else a for a in t.attacks]
        t.displayed_attack = spec["attack"]
    if "bonus_attacks" in spec:
        t.attacks = t.attacks + [type(t.attacks[0])(class_=cls, amount=n) for cls, n in spec["bonus_attacks"]]
    if "melee_armour" in spec:
        t.armours = [dataclasses.replace(a, amount=spec["melee_armour"]) if a.class_ == 4 else a for a in t.armours]
        t.displayed_melee_armour = spec["melee_armour"]
    c = u.creatable
    if "pierce_armour" in spec:
        t.armours = [dataclasses.replace(a, amount=spec["pierce_armour"]) if a.class_ == 3 else a for a in t.armours]
        c.displayed_pierce_armour = spec["pierce_armour"]
    cost = [ResourceCost(r, n, 1) for r, n in spec["cost"]]
    c.resource_costs = tuple(cost + [ResourceCost(-1, 0, 0)] * (2 - len(cost)) + [ResourceCost(4, 1, 0)])  # + 1 population
    tr = spec["train"]
    c.train_locations = [TrainLocation(train_time=tr["time"], unit_id=tr["building"], button_id=tr["button"], hot_key_id=tr["hotkey"])]
    if "creatable_type" in spec:
        c.creatable_type = spec["creatable_type"]
    u.enabled = 0   # a tech makes it available
    return u


def corpse(base, src, uid, gid, name):
    u = copy.deepcopy(base.units[src])
    u.id = u.copy_id = u.base_id = uid
    u.name = name
    u.standing_graphic = (gid, -1)
    return u


def strings():
    """Every new string, id -> text. "\\n" stays a literal backslash-n: the key-value files want it escaped."""
    uu = C.UNITS[0]
    desc = (f"{C.TAGLINE}\\n\\n" + "\\n".join(f"• {text}" for _, text in C.BONUSES)
            + f"\\n\\n<b>Unique Unit:<b>\\n{uu['name']} ({uu['summary']})"
            + "\\n\\n<b>Unique Techs:<b>\\n" + "\\n".join(f"• {t['name']} ({t['summary']})" for t in C.UNIQUE_TECHS)
            + "\\n\\n<b>Team Bonus:<b>\\n" + "\\n".join(text for _, text in C.TEAM_BONUS))
    st = {C.NAME_STRING: C.NAME, C.DESC_STRING: desc}
    for u in C.UNITS:
        for v in variants(u):
            n = v["string"]
            st[n], st[n + 1000], st[n + 100000] = v["name"], f"Create {v['name']}", f"Create <b>{v['name']}<b> (<cost>)\\n{v['help']}"
    up = uu["elite"]
    techs = [dict(name=up["name"], **up["upgrade"])] + C.UNIQUE_TECHS
    for t in techs:
        n = t["string"]
        st[n], st[n + 1000], st[n + 100000] = t["name"], f"Research {t['name']}", f"Research <b>{t['name']}<b> (<cost>)\\n{t['help']}"
    return st


def build(game, out):
    res = game / "resources"
    d = DatFile.parse(str(res / "_common/dat/empires2_x2_p1.dat"))
    stock = json.load(open(res / "_common/dat/civilizations.json"))["civilization_list"]
    base_entry, slot_entry = stock[C.BASE_CIV], stock[C.SLOT]
    NEW = C.SLOT
    base = d.civs[C.BASE_CIV]
    assert d.civs[C.SLOT].name == C.SLOT_NAME == slot_entry["internal_name"], (d.civs[C.SLOT].name, slot_entry["internal_name"])
    # the slot's own civ (the Burgundians) has bonus/unique techs tied to its civ id: park them on a civ that doesn't exist
    for t in d.techs:
        if t.civ == C.SLOT:
            t.civ = 200
    print("new civ id", NEW, "base", base.name)

    # ---------------------------------------------------------------- graphics
    G = {}
    for u in C.UNITS:
        tmpl = template_graphics(base, u["template"])
        for anim, a in u["anims"].items():
            G[f"{u['key']}_{anim}"] = add_graphic(d, tmpl[anim], f"{u['sprite']}_{anim}_x1", f"{u['name']} ({anim})", a["frames"], a["duration"])
    if C.WONDER:
        wonder_tmpl = base.units[WONDER_UNIT].standing_graphic[0]
        G["wonder"] = add_graphic(d, wonder_tmpl, f"{C.WONDER['sprite']}_x1", C.WONDER["name"], 1, 0.0, angles=1)

    # ---------------------------------------------------------------- units (appended to every civ)
    ids = {"NEW": NEW}
    uid = len(base.units)
    for u in C.UNITS:
        for v in variants(u):
            ids[v["id"]], uid = uid, uid + 1
    dead = {}
    for u in C.UNITS:
        dead[u["key"]], uid = uid, uid + 1
    new_units = [make_unit(base, v, ids[v["id"]], dead[u["key"]], G) for u in C.UNITS for v in variants(u)]
    new_units += [corpse(base, base.units[u["template"]].dead_unit_id, dead[u["key"]], G[f"{u['key']}_decayA"], u["internal"] + "_D")
                  for u in C.UNITS]
    for civ in d.civs:
        for u in new_units:
            civ.units.append(copy.deepcopy(u))

    # ---------------------------------------------------------------- the civ
    civ = copy.deepcopy(base)
    civ.name = C.NAME
    if C.WONDER:
        civ.units[WONDER_UNIT].standing_graphic = (G["wonder"], -1)
    # techs: copies of the base civ's own (Britons: Longbow (make avail), Elite Longbowman, Yeomen, Warwolf)
    uu, up = C.UNITS[0], C.UNITS[0]["elite"]
    avail_tmpl = make_avail_tech(d, C.BASE_CIV, base_entry["unique_unit_id"])
    e_avail = add_effect(d, f"{uu['name']} (make avail)", [(2, ids[uu["id"]], 1, -1, 0.0)])
    # like the Jomsviking: Castle Age only. The stock unique units also need tech 266 "Castle built",
    # which never fires for castles placed by a scenario.
    ids["t_avail"] = t_avail = add_tech(d, avail_tmpl, f"{uu['name']} (make avail)", NEW, e_avail, [CASTLE])
    e_elite = add_effect(d, up["name"], [(3, ids[uu["id"]], ids[up["id"]], -1, 0.0)])
    ids["t_elite"] = add_tech(d, base_entry["unique_unit_upgrade_id"], up["name"], NEW, e_elite, [IMPERIAL, t_avail],
                              cost=up["upgrade"]["cost"], lang=up["upgrade"]["string"])
    for t, age, tmpl in zip(C.UNIQUE_TECHS, (CASTLE, IMPERIAL), (base_entry["unique_tech_id_1"], base_entry["unique_tech_id_2"])):
        e = add_effect(d, t["name"], [tuple(ids[x] if isinstance(x, str) else x for x in c) for c in t["effects"]])
        ids[t["key"]] = add_tech(d, tmpl, t["name"], NEW, e, [age], cost=t["cost"], lang=t["string"])
    for u in C.UNITS[1:]:
        e = add_effect(d, f"{u['name']} (make avail)", [(2, ids[u["id"]], 1, -1, 0.0)])
        add_tech(d, avail_tmpl, f"{u['name']} (make avail)", NEW, e, [AGES[u["age"]][0]])
    # civ bonuses live in the civ's tech-tree effect (applied at game start), after the base civ's tree
    tree = copy.deepcopy(d.effects[base.tech_tree_id])
    tree.name = f"{C.NAME} Tech Tree"
    tree.effect_commands += [EffectCommand(*c) for c, _ in C.BONUSES]
    # the base civ's own bonuses are techs with civ == base, so they don't carry over
    d.effects.append(tree)
    civ.tech_tree_id = len(d.effects) - 1
    civ.team_bonus_id = add_effect(d, f"{C.NAME} Team Bonus", [c for c, _ in C.TEAM_BONUS])
    d.civs[C.SLOT] = civ
    ids["G"] = G
    print(json.dumps({k: v for k, v in ids.items() if k != "G"}))

    # ---------------------------------------------------------------- write the mod folder
    mod = out / C.MOD_NAME
    if mod.exists():
        shutil.rmtree(mod)
    dat_dir = mod / "resources/_common/dat"
    dat_dir.mkdir(parents=True)
    d.save(str(dat_dir / "empires2_x2_p1.dat"))
    write_json(res / "_common/dat", dat_dir, ids)
    gfx = mod / "resources/_common/drs/graphics"
    gfx.mkdir(parents=True)
    copy_sprites(out / "graphics", gfx)
    write_art(mod)
    write_strings(mod, slot_entry)
    (mod / "info.json").write_text(json.dumps(C.MOD_INFO))
    (out / "ids.json").write_text(json.dumps(ids, indent=1))
    print("built", mod)
    return ids


def write_json(src, dat_dir, ids):
    civs = json.load(open(src / "civilizations.json"))
    base_entry = civs["civilization_list"][C.BASE_CIV]
    e = copy.deepcopy(civs["civilization_list"][C.SLOT])
    assert e["internal_name"] == C.SLOT_NAME
    slot_techtree = e["tech_tree_name"]
    uu, up = C.UNITS[0], C.UNITS[0]["elite"]
    ut1, ut2 = C.UNIQUE_TECHS
    e.update({
        # internal_name / data_name / tech_tree_name stay: the executable and UI look civs up by them
        "tech_tree_image_path": f"/resources/civ_techtree/menu_techtree_{C.ART_NAME}.png",
        "emblem_image_path": f"/resources/civ_emblems/{C.ART_NAME}.png",
        "unique_unit_image_paths": [f"/resources/uniticons/{uu['menu_icon']}_50730.png"],
        "name_string_id": C.NAME_STRING, "tech_tree_description_string_id": C.DESC_STRING,
        "unique_tech_id_1": ids[ut1["key"]], "unique_tech_id_2": ids[ut2["key"]], "unique_unit_line": C.UNIT_LINE_ID,
        "unique_unit_upgrade_id": ids["t_elite"], "unique_unit_id": ids[uu["id"]], "elite_unique_unit_id": ids[up["id"]],
        "unique_unit_string_ids": [{"name": uu["string"], "description": 100000 + uu["string"]}],
    })
    civs["civilization_list"][C.SLOT] = e
    (dat_dir / "civilizations.json").write_text(json.dumps(civs, indent=2))

    lines = json.load(open(src / "unitlines.json"))
    lines["UnitLines"].append({"Name": f"{uu['name']} Line", "Identifier": uu["name"].lower().replace(" ", "-") + "-line",
                               "LineID": C.UNIT_LINE_ID, "IDChain": [ids[uu["id"]], ids[up["id"]]]})
    (dat_dir / "unitlines.json").write_text(json.dumps(lines, indent=2))

    # the slot gets the base civ's future-units list with its unique unit swapped for ours - only inside
    # "Units" lists: the same number can be a tech id (a text replace of "ID": 8 also hit the Britons' Town Watch)
    fut = json.load(open(src / "futuravailableunits.json"))
    entry = copy.deepcopy(fut[base_entry["internal_name"]])

    def swap_uu(o, in_units=False):
        if isinstance(o, dict):
            if in_units and o.get("ID") == base_entry["unique_unit_id"]:
                o["ID"] = ids[uu["id"]]
            for k, v in o.items():
                swap_uu(v, k == "Units")
        elif isinstance(o, list):
            for v in o:
                swap_uu(v, in_units)
    swap_uu(entry)
    fut[C.SLOT_NAME] = entry
    (dat_dir / "futuravailableunits.json").write_text(json.dumps(fut))

    tt = json.load(open(src / f"CivTechTrees/{base_entry['tech_tree_name']}.json"))
    tt["civ_id"] = slot_techtree
    swap = {  # the base civ's unique entries (Britons: Longbowman, Elite Longbowman, Yeomen, Warwolf) -> ours
        ("UniqueUnit", base_entry["unique_unit_id"]): dict(Name=uu["name"], **{"Name String ID": uu["string"], "Help String ID": 100000 + uu["string"],
                                                                               "Node ID": ids[uu["id"]], "Picture Index": uu["panel_icon"]}),
        ("UniqueUnit", base_entry["elite_unique_unit_id"]): dict(Name=up["name"], **{"Name String ID": up["string"], "Help String ID": 100000 + up["string"],
                                                                                     "Node ID": ids[up["id"]], "Link ID": ids[uu["id"]], "Picture Index": uu["panel_icon"],
                                                                                     "Trigger Tech ID": ids["t_elite"]}),
        ("UniqueTech", base_entry["unique_tech_id_1"]): dict(Name=ut1["name"], **{"Name String ID": ut1["string"], "Help String ID": 100000 + ut1["string"], "Node ID": ids[ut1["key"]]}),
        ("UniqueTech", base_entry["unique_tech_id_2"]): dict(Name=ut2["name"], **{"Name String ID": ut2["string"], "Help String ID": 100000 + ut2["string"], "Node ID": ids[ut2["key"]]}),
    }
    for node in tt["civ_techs_units"]:
        key = (node.get("Node Type"), node.get("Node ID"))
        if key in swap:
            node.update(swap[key])
    uu_node = next(n for n in tt["civ_techs_units"] if n["Node ID"] == ids[uu["id"]])
    for u in C.UNITS[1:]:   # the other units: a copy of the unique unit's node, moved to their building and age
        node = copy.deepcopy(uu_node)
        node.update({"Name": u["name"], "Name String ID": u["string"], "Help String ID": 100000 + u["string"], "Node ID": ids[u["id"]],
                     "Picture Index": u["panel_icon"], "Building ID": u["train"]["building"], "Age ID": AGES[u["age"]][1]})
        tt["civ_techs_units"].append(node)
    (dat_dir / "CivTechTrees").mkdir()
    (dat_dir / f"CivTechTrees/{slot_techtree}.json").write_text(json.dumps(tt, indent=2))


def copy_sprites(src, dst):
    for f in sorted(src.glob("*.sld")):
        shutil.copy(f, dst / f.name)
    want = [f"{u['sprite']}_{anim}_x1.sld" for u in C.UNITS for anim in u["anims"]] + ([f"{C.WONDER['sprite']}_x1.sld"] if C.WONDER else [])
    missing = [w for w in want if not (src / w).exists()]
    if missing:
        print(f"WARNING: {len(missing)} sprites missing from {src} - they will be invisible in game. "
              f"Make them with make_sprites.py / make_wonder.py: " + ", ".join(missing))


def write_art(mod):
    from PIL import Image
    wp = mod / "resources/_common/wpfg/resources"
    for sub in ("uniticons", "civ_emblems", "civ_techtree"):
        (wp / sub).mkdir(parents=True, exist_ok=True)

    def square(path, size):
        im = Image.open(path).convert("RGB")
        s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
        return im.resize((size, size), Image.LANCZOS)

    for u in C.UNITS:
        square(asset(u["menu_art"]), 256).save(wp / f"uniticons/{u['menu_icon']}_50730.png")
    emb = Image.open(asset(C.EMBLEM_ART)).convert("RGBA")
    emb = emb.crop(emb.getbbox()) if emb.getbbox() else emb
    canvas = Image.new("RGBA", (450, 280))
    e = emb.resize((260, 260), Image.LANCZOS)
    # white background -> transparent around the round emblem
    px = e.load()
    for y in range(e.height):
        for x in range(e.width):
            r, g, b, a = px[x, y]
            if min(r, g, b) > 238:
                px[x, y] = (r, g, b, 0)
    canvas.alpha_composite(e, (95, 10))
    # under our name and, like the strings below, under the replaced slot's own
    for name in (C.ART_NAME, C.SLOT_NAME.lower()):
        canvas.save(wp / f"civ_emblems/{name}.png")
        canvas.crop((95, 10, 355, 270)).resize((104, 104), Image.LANCZOS).save(wp / f"civ_techtree/menu_techtree_{name}.png")


def write_strings(mod, slot_entry):
    st = strings()
    # the replaced slot's own name/description strings too (some UI panels use them directly)
    st[slot_entry["name_string_id"]] = st[C.NAME_STRING]
    st[slot_entry["tech_tree_description_string_id"]] = st[C.DESC_STRING]
    # DE's key-value tables hold DLL help strings at id - 79000 (Knight: help 105068 -> key 26068)
    for k, v in list(st.items()):
        if 100000 <= k < 200000:
            st[k - 79000] = v
    lines = [f'{k} "{v}"' for k, v in st.items()]
    for lang_dir in ("en",):   # other UI languages read resources/<de, fr, jp, ...>/strings
        p = mod / f"resources/{lang_dir}/strings/key-value"
        p.mkdir(parents=True, exist_ok=True)
        (p / "key-value-modded-strings-utf8.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def install(out, profile):
    src, dst = out / C.MOD_NAME, profile / "mods/local" / C.MOD_NAME
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    status = profile / "mods/mod-status.json"
    st = json.load(open(status)) if status.exists() else {"Mods": [], "Unsub": []}
    path = f"local//{C.MOD_NAME}"
    st["Mods"] = [m for m in st["Mods"] if m.get("Path") != path]
    st["Mods"].append({"CheckSum": "", "Enabled": True, "LastUpdate": "", "Path": path, "Priority": len(st["Mods"]) + 1,
                       "PublishID": 0, "Title": C.MOD_INFO["Title"], "WorkshopID": 0})
    status.write_text(json.dumps(st))
    print("installed", dst, "- pick it in the skirmish lobby's Data Mod dropdown")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="AoE2 DE install folder (...\\steamapps\\common\\AoE2DE). Default: found via Steam, or $AOE2DE_GAME")
    ap.add_argument("--profile", help="for --install: ...\\Games\\Age of Empires 2 DE\\<steam id>. Default: found, or $AOE2DE_PROFILE")
    ap.add_argument("--out", default=str(DEFAULT_BUILD), help="build folder; sprites are read from <out>/graphics (default: build/ here)")
    ap.add_argument("--install", action="store_true", help="also copy the mod into the profile's mods/local (default: build only)")
    a = ap.parse_args()
    game = find_game(a.game)
    profile = find_profile(a.profile) if a.install else None   # before the slow part
    print("game", game)
    build(game, Path(a.out))
    if a.install:
        install(Path(a.out), profile)
