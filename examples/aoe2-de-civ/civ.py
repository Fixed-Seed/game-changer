"""The San Franciscans, as data: edit this file (and the art in assets/gen) to make your own civ.

build_mod.py turns it into a data mod; make_sprites.py / make_wonder.py make the sprites it names
(frame counts and sprite names are shared by both sides, so they can't drift apart); make_scenario.py
builds a demo map with it.

Ids of stock objects (units, techs, buildings, graphics) are the game's own: look them up with
genieutils (`DatFile.parse(".../empires2_x2_p1.dat").civs[1].units[38].name` -> 'KNGHT') or with
Advanced Genie Editor. New string ids must be unused in the stock string tables. A unit or tech with
string id N uses N (name), N + 1000 ("Create ..." / "Research ..."), N + 100000 (help) and N + 150000
(hotkey / tech-tree text), the stock pattern.
"""

MOD_NAME = "SanFranciscans"   # the mod's folder: <profile>/mods/local/<MOD_NAME>
MOD_INFO = {"Author": "Fixed Seed", "Title": "San Franciscans Civilization",
            "Description": "A new civilization: self-driving Robotaxis, Delivery Drones and the Transamerica Pyramid. Art generated with FixedSeed."}

NAME, NAME_STRING = "San Franciscans", 10399
TAGLINE, DESC_STRING = "Tech Bro civilization", 120299   # the civ description (picker, tech tree) starts with the tagline
ART_NAME = "sanfranciscans"   # file names of the emblem and tech-tree picture
BASE_CIV = 1  # Britons: Western European architecture and a standard tech tree
# The civ takes over the Burgundians' slot. A genuinely extra (64th) civ loads and plays, but the
# game's civ picker only lists civs the executable knows: its civ-id table (BRITON-CIV ... DANES-CIV)
# and the UI icon tables are index-based and hard-coded (index 63 is "random"). Replacing a slot is
# how DE civ mods ship; the Burgundians come back when the mod is removed.
SLOT = 36
SLOT_NAME = "Burgundians"   # checked against the game's data, so a patch that reorders civs stops the build

# Civ bonuses: effect commands appended to the civ's tech-tree effect (applied at game start), each with
# its line in the description. (5, unit, class, attribute, x) multiplies an attribute of a unit (-1: any)
# of a class (-1: any): attributes 5 = speed, 13 = work rate; classes 4 = villagers, 12 = cavalry;
# unit 209 = University.
BONUSES = [
    ((5, -1, 4, 13, 1.10), "Villagers work 10% faster (hustle culture)"),
    ((5, -1, 12, 5, 1.10), "Cavalry move 10% faster (autonomous driving)"),
    ((5, 209, -1, 13, 1.40), "Universities work 40% faster"),
]
TEAM_BONUS = [((5, 209, -1, 13, 1.20), "Universities work 20% faster")]

# Units. The first is the unique unit (trained at the Castle from the Castle Age, with an Elite
# upgrade); the others are extra units made available in their `age`. Each is a copy of a stock
# `template` unit (its class, sounds, attack/armour classes and the settings of its graphics records)
# with the stats given here and new sprites.
#   cost:  (resource, amount), resources 0 food, 1 wood, 2 stone, 3 gold
#   train: building (82 Castle, 87 Archery Range, 101 Stable, 12 Barracks), time (s), button slot, hotkey
#   bonus_attacks: extra (armour class, amount): 20 siege, 21 buildings
#   icons: menus, the civ picker and the tech tree load our art (menu_art -> uniticons/<menu_icon>_50730.png).
#          The in-game command panel draws icons from the base game's prebuilt widgetui atlas, which a
#          local mod can't extend (tested: widgetui/ in the mod root and under resources/_common are both
#          ignored), so in-game the units borrow the closest stock icons (panel_icon): a wheeled
#          battering vehicle (73, Siege Ram) and a war machine (80, Scorpion).
#   anims: frames per angle (16 angles each) and seconds per frame. The rest is for make_sprites.py:
#          a `fsgc render3d` motion plus the tuned parameters the shipped sprites used on top of it
#          (amp/pitch/dist/roll/sink in px or degrees, hover = px above the ground), and burn = darken
#          into a burnt-out wreck.
UNITS = [
    dict(key="robotaxi", id="ROBO", internal="SF_ROBOTAXI", name="Robotaxi", string=5817,
         template=38,  # Knight
         summary="self-driving cavalry",   # the description's "Unique Unit" line
         help=("San Franciscan unique cavalry: a self-driving car that rams anything in its way. "
               "Very fast. Strong vs. archers, siege and buildings. Weak vs. Pikemen and Camels."),
         hp=115, speed=1.6, los=5, attack=11, melee_armour=1, pierce_armour=3,
         bonus_attacks=[(21, 8), (20, 6)],   # vs buildings, siege
         cost=[(0, 60), (3, 65)], train=dict(building=82, time=18, button=1, hotkey=16101),
         creatable_type=2,  # castle unique unit (as the Jomsviking); 1 = a standard unit
         panel_icon=73, menu_icon=950, menu_art="icon_robotaxi",
         elite=dict(id="ROBO_E", internal="SF_ROBOTAXI_E", name="Elite Robotaxi", string=5818,
                    hp=140, attack=13, melee_armour=2, pierce_armour=4,
                    upgrade=dict(string=7913, cost=[(0, 850), (3, 700)], help="Upgrades your Robotaxis to Elite.")),
         sprite="u_sf_robotaxi",   # build/graphics/u_sf_robotaxi_<anim>_x1.sld
         render=dict(glb="assets/gen/robotaxi.glb", length=80, forward_yaw=-90, canvas=200, samples=40),
         anims={
             "idleA": dict(frames=10, duration=0.1, motion="bob", amp=0.3),
             "walkA": dict(frames=12, duration=0.05, motion="walk"),
             "attackA": dict(frames=16, duration=0.06, motion="lunge", dist=14),
             "deathA": dict(frames=20, duration=0.06, motion="die", roll=85, burn=True),
             "decayA": dict(frames=1, duration=0.1, motion="wreck", roll=85, burn=True),
         }),
    dict(key="drone", id="DRONE", internal="SF_DRONE", name="Delivery Drone", string=5819,
         template=24,  # Crossbowman
         help=("Hovering ranged unit that drops parcels on its targets. "
               "Fast. Strong vs. infantry. Weak vs. archers and Skirmishers."),
         hp=45, speed=1.3,
         cost=[(1, 35), (3, 40)], train=dict(building=87, time=22, button=5, hotkey=16084),
         age="castle",
         panel_icon=80, menu_icon=951, menu_art="icon_drone",
         sprite="u_sf_drone",
         render=dict(glb="assets/gen/drone.glb", length=64, forward_yaw=-90, canvas=200, samples=20, sun=6.0,
                     brighten=1.7),   # dark generated texture: lift its shadows when packing
         anims={
             "idleA": dict(frames=12, duration=0.08, motion="bob", amp=2.0, hover=34),
             "walkA": dict(frames=12, duration=0.05, motion="bob", amp=1.5, pitch=8, hover=34),
             "attackA": dict(frames=12, duration=0.07, motion="lunge", dist=-6, pitch=10, hover=34),
             "deathA": dict(frames=20, duration=0.06, motion="die", roll=60, hover=34, sink=1, speed=1.2, burn=True),
             "decayA": dict(frames=1, duration=0.1, motion="wreck", roll=60, sink=1, burn=True),
         }),
]

# Unique techs (Castle Age, Imperial Age): copies of the base civ's own (Yeomen, Warwolf) with new
# effects. (1, resource, 1, -1, n) adds n of a resource; (5, unit, class, attribute, x) multiplies and
# (4, ...) adds; attack/armour changes are class * 256 + amount (attribute 9 = attack). Units can be
# named by their id above.
UNIQUE_TECHS = [
    dict(key="t_ut1", name="Series A Funding", string=7914, cost=[(0, 200)],
         effects=[(1, 3, 1, -1, 600.0)],   # +600 gold
         summary="instantly receive 600 gold", help="A VC wires you 600 gold. Immediately."),
    dict(key="t_ut2", name="Move Fast and Break Things", string=7915, cost=[(0, 600), (3, 500)],
         effects=[(5, "ROBO", -1, 5, 1.25), (5, "ROBO_E", -1, 5, 1.25),                         # speed x1.25
                  (4, "ROBO", -1, 9, 21 * 256 + 8.0), (4, "ROBO_E", -1, 9, 21 * 256 + 8.0)],     # +8 vs buildings
         summary="Robotaxis +25% speed, +8 attack vs. buildings",
         help="Robotaxis move 25% faster and get +8 attack vs. buildings."),
]

WONDER = dict(sprite="b_sf_wonder", name="Transamerica Pyramid", art="wonder")   # None keeps the stock wonder
EMBLEM_ART = "emblem"   # a round emblem on white (assets/gen/emblem.*)
UNIT_LINE_ID = -330     # unitlines.json LineID of the unique unit line (unused by the stock lines)
