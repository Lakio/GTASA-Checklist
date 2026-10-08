"""Catalogue de tout ce qu'il faut faire pour le 100 %, avec la règle de détection.

Les numéros de variables globales ($N) viennent du main.scm d'origine (noms
Sanny Builder) et de l'autosplitter LiveSplit GTASA de tduva, qui associe
chaque valeur de compteur à une mission. Ils sont identiques pour toutes les
versions PC tant que le main.scm n'est pas modifié.

Règles (évaluées dans rules.py) :
    ("g>=", var, n)        variable globale >= n
    ("g!=0", var)          variable globale non nulle
    ("race", idx)          course n° idx gagnée ($2300[idx])
    ("chiliad", k)         course k du Chiliad Challenge
    ("export", liste, i)   véhicule i de la liste d'export
    ("robberies>=", n)     nombre de braquages de Catalina terminés
    ("collect", kind)      collectibles d'un type tous ramassés
    ("any", [r, ...]) / ("all", [r, ...])
    None                   pas de détection : à cocher à la main
"""

from dataclasses import dataclass, field


@dataclass
class Item:
    id: str
    name: str
    category: str
    rule: tuple | None
    pos: tuple[float, float] | None = None  # coordonnées monde (x, y)
    approx: bool = True                      # position du contact approximative
    note: str = ""
    group: str = ""                          # sous-groupe (donneur de mission...)


@dataclass
class Category:
    id: str
    name: str
    items: list[Item] = field(default_factory=list)


# Lieux des contacts (approximatifs, pour situer sur la carte)
LOC = {
    "grove": (2495, -1687),
    "sweet": (2512, -1672),
    "ryder": (2459, -1690),
    "smoke": (2068, -1700),
    "ogloc": (2160, -1300),
    "cesar_ls": (1800, -2120),
    "angel_pine": (-2150, -2400),
    "catalina": (868, -26),
    "truth": (-1095, -1625),
    "garage_sf": (-2026, 179),
    "zero": (-2242, 128),
    "woozie_sf": (-2160, 646),
    "jizzy": (-2621, 1410),
    "wang": (-1957, 287),
    "toreno": (-689, 930),
    "verdant": (414, 2533),
    "four_dragons": (2019, 1007),
    "caligulas": (2196, 1677),
    "mansion": (1298, -799),
    "dschool": (-2031, -117),
    "bike_school": (1173, 1352),
    "boat_school": (-2187, 2416),
    "gym_ls": (2229, -1722),
    "gym_sf": (-2270, -155),
    "gym_lv": (1968, 2295),
    "rs_haul": (-77, -1136),
    "quarry": (612, 867),
    "valet": (-1754, 961),
    "export": (-1577, 94),
    "bmx": (1946, -1371),
    "nrg": (-1574, 76),
    "chiliad": (-2311, -1634),
    "race_ls": (1770, -1700),
    "race_sf": (-1920, 280),
    "race_lv": (1640, 910),
    "race_air": (1700, 1650),
    "stadium_ls": (2695, -1704),
    "stadium_sf": (-2120, -445),
    "stadium_lv": (1100, 1600),
    "ammu_market": (1368, -1279),
    "courier_ls": (1355, -1755),
    "courier_sf": (-2590, 70),
    "courier_lv": (1890, 2087),
    "pimp": (1919, -1789),
    "taxi_ls": (1480, -1720),
    "taxi_sf": (-1990, 620),
    "taxi_lv": (2050, 1300),
    "station_unity": (1743, -1944),
    "station_market": (816, -1361),
    "station_cranberry": (-1942, 138),
    "station_linden": (2865, 1290),
    "station_yellowbell": (1433, 2620),
}


def item_spot_specs() -> dict[str, tuple]:
    """Comment trouver la position exacte de chaque élément dans les fichiers du jeu
    (voir gamefiles.resolve_spots). Les ancres de LOC servent de repli."""
    specs = {
        "v_fire": ("all", "gen:firetruk"),
        "v_vigilante": ("all", "police"),
        "v_paramedic": ("all", "gen:ambulan"),
        "v_taxi": ("approx", ["taxi_ls", "taxi_sf", "taxi_lv"]),
        "v_pimp": ("near", "gen:broadway", "pimp"),
        "v_freight": ("approx", ["station_unity", "station_market", "station_cranberry",
                                 "station_linden", "station_yellowbell"]),
        "a_courier_ls": ("near", "gen:bmx", "courier_ls"),
        "a_courier_sf": ("near", "gen:freeway", "courier_sf"),
        "a_courier_lv": ("near", "gen:faggio", "courier_lv"),
        "a_trucking": ("near", "blip:truck", "rs_haul"),
        "a_quarry": ("near", "blip:quarry", "quarry"),
        "a_zero_rc": ("near", "blip:zero", "zero"),
        "s_8track": ("near", "blip:stadium", "stadium_ls"),
        "s_blood": ("near", "blip:stadium", "stadium_sf"),
        "s_kickstart": ("near", "blip:stadium", "stadium_lv"),
        "s_dirt": ("near", "blip:stadium", "stadium_lv"),
        "c_bmx": ("near", "gen:bmx", "bmx"),
        "c_nrg": ("near", "gen:nrg500", "nrg"),
        "sc_drive": ("near", "blip:school", "dschool"),
        "sc_bike": ("near", "blip:school", "bike_school"),
        "sc_boat": ("near", "blip:school", "boat_school"),
        "g_ammu": ("near", "blip:ammu", "ammu_market"),
        "g_ls": ("near", "blip:gym", "gym_ls"),
        "g_sf": ("near", "blip:gym", "gym_sf"),
        "g_lv": ("near", "blip:gym", "gym_lv"),
    }
    for k in (1, 2, 3):
        specs[f"c_chiliad{k}"] = ("near", "gen:mtbike", "chiliad")
    for first, last, anchor in ((1, 6, "race_ls"), (9, 14, "race_sf"),
                                (15, 18, "race_lv"), (19, 24, "race_air")):
        for idx in range(first, last + 1):
            specs[f"r_{idx}"] = ("near", "blip:race", anchor)
    for flag in range(731, 760):
        specs[f"p_{flag}"] = ("property", flag)
    return specs


# Listes d'export, dans l'ordre des drapeaux $1060..$1069 :
# (nom affiché, nom du modèle dans data/vehicles.ide)
EXPORT_LISTS = [
    [("Buffalo", "buffalo"), ("Sentinel", "sentinel"), ("Infernus", "infernus"),
     ("Camper", "camper"), ("Admiral", "admiral"), ("Patriot", "patriot"),
     ("Sanchez", "sanchez"), ("Stretch", "stretch"), ("Feltzer", "feltzer"),
     ("Remington", "remingtn")],
    [("Cheetah", "cheetah"), ("Rancher", "rancher"), ("Stallion", "stallion"),
     ("Tanker", "petro"), ("Comet", "comet"), ("Slamvan", "slamvan"),
     ("Blista Compact", "blistac"), ("Stafford", "stafford"), ("Sabre", "sabre"),
     ("FCR-900", "fcr900")],
    [("Banshee", "banshee"), ("Super GT", "supergt"), ("Journey", "journey"),
     ("Huntley", "huntley"), ("BF Injection", "bfinject"), ("Blade", "blade"),
     ("Freeway", "freeway"), ("Mesa", "mesa"), ("ZR-350", "zr350"), ("Euros", "euros")],
]


def _strand(cat, group, var, names, loc, start=1, ids=None):
    """Missions d'un même donneur : la n-ième est finie quand le compteur >= n."""
    out = []
    for i, name in enumerate(names):
        value = start + i if ids is None else ids[i]
        out.append(Item(f"m_{var}_{value}", name, cat, ("g>=", var, value),
                        LOC.get(loc), group=group))
    return out


def build_catalog() -> list[Category]:
    cats: list[Category] = []

    # ------------------------------------------------------------------ LS
    c = Category("story_ls", "Histoire — Los Santos")
    c.items += [
        Item("m_intro", "In the Beginning", c.id, ("any", [("g!=0", 24), ("g>=", 448, 1)]),
             LOC["grove"], group="Introduction"),
        Item("m_448_1", "Big Smoke", c.id, ("g>=", 448, 1), LOC["grove"], group="Carl Johnson"),
        Item("m_sweet_kendl", "Sweet & Kendl", c.id, ("g>=", 448, 1), LOC["grove"],
             group="Carl Johnson", note="Fait partie du script de « Big Smoke »."),
        Item("m_448_2", "Ryder", c.id, ("g>=", 448, 2), LOC["ryder"], group="Ryder"),
    ]
    c.items += _strand(c.id, "Sweet", 452, [
        "Tagging Up Turf", "Cleaning the Hood", "Drive-Thru", "Nines and AK's",
        "Drive-By", "Sweet's Girl", "Cesar Vialpando"], "sweet")
    c.items += _strand(c.id, "Big Smoke", 454, [
        "OG Loc", "Running Dog", "Wrong Side of the Tracks", "Just Business"], "smoke")
    c.items += _strand(c.id, "Ryder", 453, [
        "Home Invasion", "Catalyst", "Robbing Uncle Sam"], "ryder")
    c.items += _strand(c.id, "Cesar Vialpando", 457, ["High Stakes, Low-Rider"], "cesar_ls")
    c.items += _strand(c.id, "OG Loc", 455, [
        "Life's a Beach", "Madd Dogg's Rhymes", "Management Issues", "House Party"],
        "ogloc", ids=[1, 2, 3, 5])
    c.items += _strand(c.id, "C.R.A.S.H.", 456, ["Burning Desire", "Gray Imports"], None)
    c.items += _strand(c.id, "Sweet", 452, ["Doberman", "Los Sepulcros"], "sweet", start=8)
    c.items += _strand(c.id, "Sweet", 458, ["Reuniting the Families", "The Green Sabre"], "sweet")
    cats.append(c)

    # ------------------------------------------------------------ Campagne
    c = Category("story_country", "Histoire — Campagne")
    c.items += _strand(c.id, "C.R.A.S.H.", 493, ["Badlands"], "angel_pine")
    c.items += [
        Item("m_first_date", "First Date", c.id,
             ("any", [("g>=", 489, 1), ("robberies>=", 1)]), LOC["catalina"], group="Catalina"),
        Item("m_716", "Tanker Commander", c.id, ("g!=0", 716), LOC["catalina"], group="Catalina"),
        Item("m_first_base", "First Base", c.id, ("robberies>=", 2), LOC["catalina"],
             group="Catalina", note="Cinématique entre deux braquages : déduite du nombre de braquages."),
        Item("m_714", "Local Liquor Store", c.id, ("g!=0", 714), LOC["catalina"], group="Catalina"),
        Item("m_gone_courting", "Gone Courting", c.id, ("robberies>=", 3), LOC["catalina"],
             group="Catalina", note="Cinématique entre deux braquages : déduite du nombre de braquages."),
        Item("m_717", "Against All Odds", c.id, ("g!=0", 717), LOC["catalina"], group="Catalina"),
        Item("m_made_in_heaven", "Made in Heaven", c.id, ("robberies>=", 4), LOC["catalina"],
             group="Catalina", note="Cinématique entre deux braquages : déduite du nombre de braquages."),
        Item("m_715", "Small Town Bank", c.id, ("g!=0", 715), LOC["catalina"], group="Catalina"),
        Item("m_2163", "King in Exile", c.id, ("g!=0", 2163), LOC["angel_pine"], group="Cesar Vialpando"),
        Item("m_491_1", "Body Harvest", c.id, ("g>=", 491, 1), LOC["truth"], group="The Truth"),
        Item("m_wuzimu", "Wu Zi Mu", c.id, ("g>=", 2330, 2), LOC["angel_pine"], group="Cesar Vialpando"),
        Item("m_farewell", "Farewell, My Love...", c.id, ("g>=", 2330, 3), LOC["angel_pine"],
             group="Cesar Vialpando"),
        Item("m_491_2", "Are You Going to San Fierro?", c.id, ("g>=", 491, 2), LOC["truth"],
             group="The Truth"),
    ]
    cats.append(c)

    # ---------------------------------------------------------- San Fierro
    c = Category("story_sf", "Histoire — San Fierro")
    c.items += _strand(c.id, "Carl Johnson", 541, ["Wear Flowers in Your Hair", "Deconstruction"],
                       "garage_sf")
    c.items += _strand(c.id, "C.R.A.S.H.", 546, ["555 We Tip", "Snail Trail"], None)
    c.items += _strand(c.id, "Zero", 542, ["Air Raid", "Supply Lines...", "New Model Army"], "zero")
    c.items += [Item("m_86", "Back to School (auto-école)", c.id, ("g!=0", 86), LOC["dschool"],
                     group="Auto-école")]
    c.items += _strand(c.id, "Syndicat Loco / Triades", 545, [
        "Photo Opportunity", "Jizzy", "T-Bone Mendez", "Mike Toreno", "Outrider",
        "Ice Cold Killa", "Pier 69", "Toreno's Last Flight", "Yay Ka-Boom-Boom"],
        "jizzy", ids=[1, 3, 4, 5, 6, 7, 8, 9, 10])
    c.items += _strand(c.id, "Woozie", 543, [
        "Mountain Cloud Boys", "Ran Fa Li", "Lure", "Amphibious Assault", "The Da Nang Thang"],
        "woozie_sf")
    c.items += _strand(c.id, "Wang Cars", 544, [
        "Zeroing In", "Test Drive", "Customs Fast Track", "Puncture Wounds"], "wang")
    cats.append(c)

    # -------------------------------------------------------------- Désert
    c = Category("story_desert", "Histoire — Désert")
    c.items += _strand(c.id, "Mike Toreno", 593, [
        "Monster", "Highjack", "Interdiction", "Verdant Meadows", "Learning to Fly (école de pilotage)",
        "N.O.E.", "Stowaway", "Black Project", "Green Goo"], "toreno")
    for it in c.items[3:]:
        it.pos = LOC["verdant"]
    cats.append(c)

    # -------------------------------------------------------- Las Venturas
    c = Category("story_lv", "Histoire — Las Venturas")
    c.items += _strand(c.id, "Casino / Woozie / Salvatore", 597, [
        "Fender Ketchup", "Explosive Situation", "You've Had Your Chips", "Don Peyote",
        "Intensive Care", "The Meat Business", "Fish in a Barrel", "Freefall",
        "Saint Mark's Bistro"], "four_dragons")
    c.items += _strand(c.id, "C.R.A.S.H.", 598, ["Misappropriation", "High Noon"], None)
    c.items += _strand(c.id, "Madd Dogg", 599, ["Madd Dogg"], "caligulas")
    c.items += _strand(c.id, "Braquage (Woozie)", 600, [
        "Architectural Espionage", "Key to Her Heart", "Dam and Blast", "Cop Wheels",
        "Up, Up and Away!", "Breaking the Bank at Caligula's"], "four_dragons")
    cats.append(c)

    # --------------------------------------------------- Retour à Los Santos
    c = Category("story_rtls", "Histoire — Retour à Los Santos")
    c.items += _strand(c.id, "Manoir de Madd Dogg", 626, [
        "A Home in the Hills", "Vertical Bird", "Home Coming", "Cut Throat Business"], "mansion")
    c.items[0].pos = LOC["four_dragons"]
    c.items += _strand(c.id, "Sweet", 627, ["Beat Down on B Dup", "Grove 4 Life"], "grove")
    c.items += _strand(c.id, "Sweet", 629, ["Riot", "Los Desperados", "End of the Line"], "grove",
                       ids=[1, 2, 4])
    cats.append(c)

    # ---------------------------------------------------- Missions véhicule
    c = Category("vehicle", "Missions de véhicule")
    c.items += [
        Item("v_fire", "Pompier — niveau 12", c.id, ("g!=0", 1489)),
        Item("v_vigilante", "Justicier — niveau 12", c.id, ("g!=0", 1488)),
        Item("v_paramedic", "Ambulancier — niveau 12", c.id, ("g!=0", 1487)),
        Item("v_taxi", "Taxi — 50 courses", c.id, ("g!=0", 1491)),
        Item("v_pimp", "Proxénète — niveau 10", c.id, ("g!=0", 1991)),
        Item("v_freight", "Train de marchandises — niveau 2", c.id, ("g!=0", 8239)),
    ]
    cats.append(c)

    # ------------------------------------------------------- Missions d'actifs
    c = Category("assets", "Missions d'actifs")
    c.items += [
        Item("a_courier_ls", "Coursier Los Santos", c.id, ("g!=0", 1992)),
        Item("a_courier_sf", "Coursier San Fierro", c.id, ("g!=0", 1994)),
        Item("a_courier_lv", "Coursier Las Venturas", c.id, ("g!=0", 1993)),
        Item("a_valet", "Voiturier (niveau 5)", c.id, ("g!=0", 1900), LOC["valet"]),
        Item("a_trucking", "Camionnage — 8 missions", c.id, ("g>=", 8159, 8), LOC["rs_haul"]),
        Item("a_quarry", "Carrière — 7 missions", c.id, ("g!=0", 1493), LOC["quarry"]),
        Item("a_zero_rc", "Achat du magasin RC de Zero", c.id, ("g!=0", 1620), LOC["zero"]),
    ]
    cats.append(c)

    # -------------------------------------------------------------- Courses
    c = Category("races", "Courses")
    races = [
        ("Los Santos", [(1, "Little Loop"), (2, "Backroad Wanderer"), (3, "City Circuit"),
                        (4, "Vinewood"), (5, "Freeway"), (6, "Into the Country")]),
        ("San Fierro", [(9, "Dirtbike Danger"), (10, "Bandito County"), (11, "Go-Go Karting"),
                        (12, "San Fierro Fastlane"), (13, "San Fierro Hills"),
                        (14, "Country Endurance")]),
        ("Las Venturas", [(15, "SF to LV"), (16, "Dam Rider"), (17, "Desert Tricks"),
                          (18, "LV Ringroad")]),
        ("Aériennes", [(19, "World War Ace"), (20, "Barnstorming"), (21, "Military Service"),
                       (22, "Chopper Checkpoint"), (23, "Whirly Bird Waypoint"),
                       (24, "Heli Hell")]),
    ]
    for group, lst in races:
        for idx, name in lst:
            c.items.append(Item(f"r_{idx}", name, c.id, ("race", idx), group=group))
    cats.append(c)

    # ---------------------------------------------------- Stades et défis
    c = Category("challenges", "Stades & défis")
    c.items += [
        Item("s_8track", "8-Track (1re place)", c.id, ("race", 25), group="Stades"),
        Item("s_dirt", "Dirt Track (1re place)", c.id, ("race", 26), group="Stades"),
        Item("s_kickstart", "Kickstart", c.id, ("g!=0", 90), group="Stades"),
        Item("s_blood", "Blood Ring", c.id, ("g!=0", 1941), group="Stades"),
        Item("c_bmx", "BMX Challenge", c.id, ("g!=0", 2795), LOC["bmx"], group="Défis"),
        Item("c_nrg", "NRG-500 Challenge", c.id, ("g!=0", 2796), LOC["nrg"], group="Défis"),
        Item("c_chiliad1", "Chiliad Challenge — course 1", c.id, ("chiliad", 1), LOC["chiliad"],
             group="Défis"),
        Item("c_chiliad2", "Chiliad Challenge — course 2", c.id, ("chiliad", 2), LOC["chiliad"],
             group="Défis"),
        Item("c_chiliad3", "Chiliad Challenge — course 3", c.id, ("chiliad", 3), LOC["chiliad"],
             group="Défis"),
    ]
    cats.append(c)

    # -------------------------------------------------------------- Écoles
    c = Category("schools", "Écoles (bronze minimum)")
    c.items += [
        Item("sc_drive", "Auto-école (Back to School)", c.id, ("g!=0", 86), LOC["dschool"]),
        Item("sc_bike", "Moto-école", c.id, ("g!=0", 2201), LOC["bike_school"]),
        Item("sc_boat", "École de bateau", c.id, ("g!=0", 1969), LOC["boat_school"]),
        Item("sc_pilot", "École de pilotage (Learning to Fly)", c.id, ("g>=", 593, 5), LOC["verdant"]),
    ]
    cats.append(c)

    # --------------------------------------------- Ammu-Nation et salles
    c = Category("gyms", "Ammu-Nation & salles de sport")
    c.items += [
        Item("g_ammu", "Défi de tir Ammu-Nation (4 armes)", c.id, ("g!=0", 5272)),
        Item("g_ls", "Boxe — salle de Ganton (LS)", c.id, ("g!=0", 8153), LOC["gym_ls"]),
        Item("g_sf", "Kung-fu — Cobra (SF)", c.id, ("g!=0", 8154), LOC["gym_sf"]),
        Item("g_lv", "Kickboxing — Below the Belt (LV)", c.id, ("g!=0", 8158), LOC["gym_lv"]),
    ]
    cats.append(c)

    # ------------------------------------------------------ Export / Import
    c = Category("exports", "Export / Import")
    for li, vehicles in enumerate(EXPORT_LISTS):
        for si, (name, _model) in enumerate(vehicles):
            c.items.append(Item(f"e_{li}_{si}", name, c.id, ("export", li, si), LOC["export"],
                                group=f"Liste {li + 1}",
                                note="Clic : voir où trouver ce véhicule sur la carte."))
    cats.append(c)

    # ---------------------------------------------------------- Collectibles
    c = Category("collectibles", "Collectibles")
    c.items += [
        Item("col_tags", "100 tags (graffitis)", c.id, ("collect", "tags"),
             note="Les positions des tags sont relevées dans la mémoire du jeu : "
                  "elles apparaissent sur la carte après un premier lancement du jeu "
                  "avec l'appli ouverte."),
        Item("col_snapshots", "50 photos (snapshots)", c.id, ("collect", "snapshots")),
        Item("col_horseshoes", "50 fers à cheval", c.id, ("collect", "horseshoes")),
        Item("col_oysters", "50 huîtres", c.id, ("collect", "oysters")),
    ]
    cats.append(c)

    # ------------------------------------------------------------- Planques
    c = Category("properties", "Planques à acheter")
    props = [
        (754, "Jefferson", "Los Santos"), (738, "Verdant Bluffs", "Los Santos"),
        (743, "Verona Beach", "Los Santos"), (758, "Willowfield", "Los Santos"),
        (731, "Santa Maria Beach", "Los Santos"), (740, "Mulholland", "Los Santos"),
        (759, "Blueberry", "Campagne"), (736, "Palomino Creek", "Campagne"),
        (753, "Dillimore", "Campagne"), (747, "Whetstone / Flint County", "Campagne"),
        (750, "Angel Pine", "Campagne"),
        (746, "Chinatown", "San Fierro"), (748, "Doherty", "San Fierro"),
        (741, "Paradiso", "San Fierro"), (742, "Hashbury", "San Fierro"),
        (739, "Calton Heights", "San Fierro"), (749, "Queens (suite d'hôtel)", "San Fierro"),
        (751, "El Quebrados", "Désert"), (752, "Tierra Robada", "Désert"),
        (733, "Fort Carson", "Désert"),
        (757, "Creek", "Las Venturas"), (732, "Rockshore West", "Las Venturas"),
        (737, "Redsands West", "Las Venturas"), (735, "Whitewood Estates", "Las Venturas"),
        (734, "Prickle Pine", "Las Venturas"),
        (755, "Old Venturas Strip (suite)", "Las Venturas"),
        (744, "Pirates in Men's Pants (suite)", "Las Venturas"),
        (745, "The Camel's Toe (suite)", "Las Venturas"),
        (756, "The Clown's Pocket (suite)", "Las Venturas"),
    ]
    for var, name, group in props:
        c.items.append(Item(f"p_{var}", name, c.id, ("g!=0", var), group=group))
    cats.append(c)

    return cats


def all_items(cats: list[Category]) -> list[Item]:
    return [it for c in cats for it in c.items]
