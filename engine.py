"""Deterministic 5e rules engine.

Everything numeric lives here so the LLM never has to do math:
dice, characters, encounter XP budgets, loot, NPCs.
"""
import math
import random
import re

ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]


def mod(score: int) -> int:
    return (score - 10) // 2


def fmt(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


# ------------------------------------------------------------------ dice
DICE_RE = re.compile(r"^(\d*)d(\d+)(?:(k[hl])(\d+))?((?:[+-]\d+)*)$")


def roll(expr: str = "1d20", advantage: str = "none") -> dict:
    e = re.sub(r"\s+", "", str(expr).lower())
    m = DICE_RE.match(e)
    if not m:
        raise ValueError(f"I can't parse '{expr}'. Try 2d6+3, d20, or 4d6kh3.")
    n = int(m.group(1) or 1)
    sides = int(m.group(2))
    if not (1 <= n <= 100) or not (2 <= sides <= 1000):
        raise ValueError("Keep it to 1-100 dice with 2-1000 sides.")
    modifier = sum(int(x) for x in re.findall(r"[+-]\d+", m.group(5) or ""))
    keep_mode, keep_n = m.group(3), int(m.group(4) or 0)

    def once():
        dice = [random.randint(1, sides) for _ in range(n)]
        kept = dice
        if keep_mode:
            kept = sorted(dice, reverse=(keep_mode == "kh"))[: max(1, keep_n)]
        return dice, kept

    single_d20 = n == 1 and sides == 20
    adv = {"advantage": "adv", "disadvantage": "dis"}.get(advantage, advantage)
    if adv not in ("adv", "dis"):
        adv = "none"
    first = once()
    discarded = None
    chosen = first
    if adv != "none" and single_d20:
        second = once()
        better = max if adv == "adv" else min
        chosen = better([first, second], key=lambda p: p[1][0])
        discarded = (second if chosen is first else first)[0]
    dice, kept = chosen
    return {
        "type": "roll", "expr": e, "dice": dice, "kept": kept, "modifier": modifier,
        "total": sum(kept) + modifier, "advantage": adv, "discarded": discarded,
        "crit": single_d20 and kept[0] == 20, "fumble": single_d20 and kept[0] == 1,
        "sides": sides,
    }


def total(expr: str) -> int:
    return roll(expr)["total"]


# ------------------------------------------------------------ characters
RACES = {
    "Human": dict(asi={a: 1 for a in ABILITIES}, speed=30, traits=["Versatile", "Extra Language"],
                  first=["Aldric", "Mara", "Tobias", "Elena", "Garrick", "Sybil", "Joren", "Brenna", "Cedric", "Isolde"],
                  last=["Ashford", "Blackwood", "Thorne", "Hollis", "Marsh", "Vance"]),
    "Elf": dict(asi={"dex": 2, "int": 1}, speed=30, traits=["Darkvision", "Keen Senses", "Fey Ancestry", "Trance"],
                first=["Aelar", "Thia", "Faelyn", "Caelum", "Sariel", "Vaelis", "Lethandrel", "Naivara"],
                last=["Moonwhisper", "Starweaver", "Oakenshade", "Silverbrook", "Dawnstrider", "Nightbloom"]),
    "Dwarf": dict(asi={"con": 2, "wis": 1}, speed=25, traits=["Darkvision", "Dwarven Resilience", "Stonecunning"],
                  first=["Dorgun", "Helga", "Baern", "Vistra", "Torbek", "Kathra", "Rurik", "Dagna"],
                  last=["Ironfist", "Stonehelm", "Deepdelver", "Forgeborn", "Anvilbrow", "Coppervein"]),
    "Halfling": dict(asi={"dex": 2, "cha": 1}, speed=25, traits=["Lucky", "Brave", "Halfling Nimbleness"],
                     first=["Pip", "Rosie", "Corrin", "Lidda", "Merric", "Seraphina", "Wellby", "Tilda"],
                     last=["Goodbarrel", "Tealeaf", "Underbough", "Brushgather", "Greenbottle", "Thorngage"]),
    "Tiefling": dict(asi={"cha": 2, "int": 1}, speed=30, traits=["Darkvision", "Hellish Resistance", "Infernal Legacy"],
                     first=["Kallista", "Mordai", "Rieta", "Akmenos", "Nemeia", "Skamos", "Orianna", "Damakos"],
                     last=["Ashveil", "Cindermark", "Dreadmoor", "Hollowthorn"]),
    "Dragonborn": dict(asi={"str": 2, "cha": 1}, speed=30, traits=["Breath Weapon", "Damage Resistance"],
                       first=["Arjhan", "Kriv", "Medrash", "Sora", "Nala", "Rhogar", "Tazan", "Daar"],
                       last=["Clethtinthiallor", "Kerrhylon", "Myastan", "Yarjerit"]),
    "Gnome": dict(asi={"int": 2, "con": 1}, speed=25, traits=["Darkvision", "Gnome Cunning"],
                  first=["Boddynock", "Nissa", "Fonkin", "Zook", "Orla", "Wrenn", "Dimble", "Bimpnottin"],
                  last=["Nackle", "Beren", "Daergel", "Folkor", "Scheppen", "Timbers"]),
    "Half-Orc": dict(asi={"str": 2, "con": 1}, speed=30, traits=["Darkvision", "Relentless Endurance", "Savage Attacks"],
                     first=["Grask", "Shaka", "Ront", "Ilvara", "Thokk", "Baggi", "Yevelda", "Dench"],
                     last=["Skullcleaver", "Bonegnash", "Ironhide", "Redtusk"]),
    "Half-Elf": dict(asi={"cha": 2}, flex=2, bonus_skills=2, speed=30, traits=["Darkvision", "Fey Ancestry", "Skill Versatility"],
                     first=["Aldric", "Thia", "Mara", "Caelum", "Elena", "Sariel", "Joren", "Naivara"],
                     last=["Ashford", "Moonwhisper", "Hollis", "Silverbrook", "Vance", "Dawnstrider"]),
}

SKILLS = {
    "Acrobatics": "dex", "Animal Handling": "wis", "Arcana": "int", "Athletics": "str",
    "Deception": "cha", "History": "int", "Insight": "wis", "Intimidation": "cha",
    "Investigation": "int", "Medicine": "wis", "Nature": "int", "Perception": "wis",
    "Performance": "cha", "Persuasion": "cha", "Religion": "int", "Sleight of Hand": "dex",
    "Stealth": "dex", "Survival": "wis",
}

BACKGROUNDS = {
    "Acolyte": ["Insight", "Religion"], "Charlatan": ["Deception", "Sleight of Hand"],
    "Criminal": ["Deception", "Stealth"], "Entertainer": ["Acrobatics", "Performance"],
    "Folk Hero": ["Animal Handling", "Survival"], "Guild Artisan": ["Insight", "Persuasion"],
    "Hermit": ["Medicine", "Religion"], "Noble": ["History", "Persuasion"],
    "Outlander": ["Athletics", "Survival"], "Sage": ["Arcana", "History"],
    "Sailor": ["Athletics", "Perception"], "Soldier": ["Athletics", "Intimidation"],
}

CLASSES = {
    "Barbarian": dict(hd=12, pri=["str", "con", "dex", "wis", "cha", "int"], saves=["str", "con"], nskills=2,
                      skills=["Animal Handling", "Athletics", "Intimidation", "Nature", "Perception", "Survival"],
                      ac=dict(kind="unarmored", stat="con", label="Unarmored Defense"), caster=None, extra=(5,),
                      attacks=[dict(name="Greataxe", dice="1d12", stat="str")],
                      feats={1: ["Rage", "Unarmored Defense"], 2: ["Reckless Attack", "Danger Sense"], 3: ["Primal Path"],
                             5: ["Extra Attack", "Fast Movement"], 7: ["Feral Instinct"], 9: ["Brutal Critical"], 11: ["Relentless Rage"]},
                      gear=["Greataxe", "Two handaxes", "Explorer's pack", "4 javelins"]),
    "Bard": dict(hd=8, pri=["cha", "dex", "con", "wis", "int", "str"], saves=["dex", "cha"], nskills=3,
                 skills=list(SKILLS), ac=dict(kind="dex", base=11, cap=None, label="Leather armor"), caster="full", cast_stat="cha", extra=(),
                 attacks=[dict(name="Rapier", dice="1d8", stat="dex")],
                 feats={1: ["Bardic Inspiration", "Spellcasting"], 2: ["Jack of All Trades", "Song of Rest"], 3: ["Bard College", "Expertise"],
                        5: ["Font of Inspiration"], 6: ["Countercharm"], 10: ["Magical Secrets"]},
                 gear=["Rapier", "Lute", "Leather armor", "Dagger", "Entertainer's pack"]),
    "Cleric": dict(hd=8, pri=["wis", "con", "str", "cha", "dex", "int"], saves=["wis", "cha"], nskills=2,
                   skills=["History", "Insight", "Medicine", "Persuasion", "Religion"],
                   ac=dict(kind="dex", base=16, cap=2, label="Scale mail & shield"), caster="full", cast_stat="wis", extra=(),
                   attacks=[dict(name="Mace", dice="1d6", stat="str")],
                   feats={1: ["Spellcasting", "Divine Domain"], 2: ["Channel Divinity", "Domain feature"], 5: ["Destroy Undead"],
                          10: ["Divine Intervention"]},
                   gear=["Mace", "Scale mail", "Shield", "Holy symbol", "Priest's pack"]),
    "Druid": dict(hd=8, pri=["wis", "con", "dex", "int", "cha", "str"], saves=["int", "wis"], nskills=2,
                  skills=["Arcana", "Animal Handling", "Insight", "Medicine", "Nature", "Perception", "Religion", "Survival"],
                  ac=dict(kind="dex", base=13, cap=None, label="Leather armor & shield"), caster="full", cast_stat="wis", extra=(),
                  attacks=[dict(name="Scimitar", dice="1d6", stat="dex")],
                  feats={1: ["Druidic", "Spellcasting"], 2: ["Wild Shape", "Druid Circle"], 5: [], 18: ["Timeless Body", "Beast Spells"]},
                  gear=["Scimitar", "Wooden shield", "Leather armor", "Druidic focus", "Explorer's pack"]),
    "Fighter": dict(hd=10, pri=["str", "con", "dex", "wis", "cha", "int"], saves=["str", "con"], nskills=2,
                    skills=["Acrobatics", "Animal Handling", "Athletics", "History", "Insight", "Intimidation", "Perception", "Survival"],
                    ac=dict(kind="fixed", v=18, label="Chain mail & shield"), caster=None, extra=(5, 11, 20),
                    asi_levels=(4, 6, 8, 12, 14, 16, 19),
                    attacks=[dict(name="Longsword", dice="1d8", stat="str")],
                    feats={1: ["Fighting Style", "Second Wind"], 2: ["Action Surge"], 3: ["Martial Archetype"], 5: ["Extra Attack"],
                           9: ["Indomitable"], 11: ["Extra Attack (2)"]},
                    gear=["Longsword", "Chain mail", "Shield", "Light crossbow & 20 bolts", "Dungeoneer's pack"]),
    "Monk": dict(hd=8, pri=["dex", "wis", "con", "str", "cha", "int"], saves=["str", "dex"], nskills=2,
                 skills=["Acrobatics", "Athletics", "History", "Insight", "Religion", "Stealth"],
                 ac=dict(kind="unarmored", stat="wis", label="Unarmored Defense"), caster=None, extra=(5,),
                 attacks=[dict(name="Martial Arts strike", dice="MARTIAL", stat="dex")],
                 feats={1: ["Unarmored Defense", "Martial Arts"], 2: ["Ki", "Unarmored Movement"], 3: ["Monastic Tradition", "Deflect Missiles"],
                        4: ["Slow Fall"], 5: ["Extra Attack", "Stunning Strike"], 6: ["Ki-Empowered Strikes"], 7: ["Evasion", "Stillness of Mind"]},
                 gear=["Shortsword", "10 darts", "Explorer's pack"]),
    "Paladin": dict(hd=10, pri=["str", "cha", "con", "wis", "dex", "int"], saves=["wis", "cha"], nskills=2,
                    skills=["Athletics", "Insight", "Intimidation", "Medicine", "Persuasion", "Religion"],
                    ac=dict(kind="fixed", v=18, label="Chain mail & shield"), caster="half", cast_stat="cha", extra=(5,),
                    attacks=[dict(name="Longsword", dice="1d8", stat="str")],
                    feats={1: ["Divine Sense", "Lay on Hands"], 2: ["Fighting Style", "Divine Smite"], 3: ["Divine Health", "Sacred Oath"],
                           5: ["Extra Attack"], 6: ["Aura of Protection"], 10: ["Aura of Courage"]},
                    gear=["Longsword", "Chain mail", "Shield", "5 javelins", "Holy symbol", "Priest's pack"]),
    "Ranger": dict(hd=10, pri=["dex", "wis", "con", "str", "cha", "int"], saves=["str", "dex"], nskills=3,
                   skills=["Animal Handling", "Athletics", "Insight", "Investigation", "Nature", "Perception", "Stealth", "Survival"],
                   ac=dict(kind="dex", base=14, cap=2, label="Scale mail"), caster="half", cast_stat="wis", extra=(5,),
                   attacks=[dict(name="Longbow", dice="1d8", stat="dex", ranged=True)],
                   feats={1: ["Favored Enemy", "Natural Explorer"], 2: ["Fighting Style", "Spellcasting"], 3: ["Ranger Archetype", "Primeval Awareness"],
                          5: ["Extra Attack"], 8: ["Land's Stride"], 10: ["Hide in Plain Sight"]},
                   gear=["Longbow & 20 arrows", "Two shortswords", "Scale mail", "Dungeoneer's pack"]),
    "Rogue": dict(hd=8, pri=["dex", "int", "cha", "con", "wis", "str"], saves=["dex", "int"], nskills=4,
                  skills=["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception",
                          "Performance", "Persuasion", "Sleight of Hand", "Stealth"],
                  ac=dict(kind="dex", base=11, cap=None, label="Leather armor"), caster=None, extra=(),
                  asi_levels=(4, 8, 10, 12, 16, 19),
                  attacks=[dict(name="Shortsword", dice="1d6", stat="dex"), dict(name="Shortbow", dice="1d6", stat="dex", ranged=True)],
                  feats={1: ["Expertise", "Sneak Attack", "Thieves' Cant"], 2: ["Cunning Action"], 3: ["Roguish Archetype"],
                         5: ["Uncanny Dodge"], 7: ["Evasion"], 11: ["Reliable Talent"]},
                  gear=["Shortsword", "Shortbow & 20 arrows", "Thieves' tools", "Leather armor", "Two daggers"]),
    "Sorcerer": dict(hd=6, pri=["cha", "con", "dex", "wis", "int", "str"], saves=["con", "cha"], nskills=2,
                     skills=["Arcana", "Deception", "Insight", "Intimidation", "Persuasion", "Religion"],
                     ac=dict(kind="dex", base=10, cap=None, label="No armor"), caster="full", cast_stat="cha", extra=(),
                     attacks=[dict(name="Fire Bolt", dice="CANTRIP", stat="cha", ranged=True, spell=True),
                              dict(name="Dagger", dice="1d4", stat="dex")],
                     feats={1: ["Spellcasting", "Sorcerous Origin"], 2: ["Font of Magic"], 3: ["Metamagic"]},
                     gear=["Two daggers", "Arcane focus", "Dungeoneer's pack"]),
    "Warlock": dict(hd=8, pri=["cha", "con", "dex", "wis", "int", "str"], saves=["wis", "cha"], nskills=2,
                    skills=["Arcana", "Deception", "History", "Intimidation", "Investigation", "Nature", "Religion"],
                    ac=dict(kind="dex", base=11, cap=None, label="Leather armor"), caster="pact", cast_stat="cha", extra=(),
                    attacks=[dict(name="Eldritch Blast", dice="BLAST", stat="cha", ranged=True, spell=True),
                             dict(name="Dagger", dice="1d4", stat="dex")],
                    feats={1: ["Otherworldly Patron", "Pact Magic"], 2: ["Eldritch Invocations"], 3: ["Pact Boon"], 11: ["Mystic Arcanum (6th)"]},
                    gear=["Light crossbow", "Leather armor", "Arcane focus", "Two daggers", "Scholar's pack"]),
    "Wizard": dict(hd=6, pri=["int", "con", "dex", "wis", "cha", "str"], saves=["int", "wis"], nskills=2,
                   skills=["Arcana", "History", "Insight", "Investigation", "Medicine", "Religion"],
                   ac=dict(kind="dex", base=10, cap=None, label="No armor"), caster="full", cast_stat="int", extra=(),
                   attacks=[dict(name="Fire Bolt", dice="CANTRIP", stat="int", ranged=True, spell=True),
                            dict(name="Quarterstaff", dice="1d6", stat="str")],
                   feats={1: ["Spellcasting", "Arcane Recovery"], 2: ["Arcane Tradition"], 18: ["Spell Mastery"]},
                   gear=["Quarterstaff", "Spellbook", "Component pouch", "Scholar's pack"]),
}

FULL_SLOTS = {
    1: [2], 2: [3], 3: [4, 2], 4: [4, 3], 5: [4, 3, 2], 6: [4, 3, 3], 7: [4, 3, 3, 1], 8: [4, 3, 3, 2],
    9: [4, 3, 3, 3, 1], 10: [4, 3, 3, 3, 2], 11: [4, 3, 3, 3, 2, 1], 12: [4, 3, 3, 3, 2, 1],
    13: [4, 3, 3, 3, 2, 1, 1], 14: [4, 3, 3, 3, 2, 1, 1], 15: [4, 3, 3, 3, 2, 1, 1, 1], 16: [4, 3, 3, 3, 2, 1, 1, 1],
    17: [4, 3, 3, 3, 2, 1, 1, 1, 1], 18: [4, 3, 3, 3, 3, 1, 1, 1, 1], 19: [4, 3, 3, 3, 3, 2, 1, 1, 1],
    20: [4, 3, 3, 3, 3, 2, 2, 1, 1],
}

PLACES = ["a mist-shrouded river town", "the back alleys of a sprawling port city", "a remote mountain monastery",
          "a failing noble house", "a traveling caravan", "a border fort nobody remembers", "a village that no longer exists",
          "the shadow of a sleeping dragon's mountain"]
EVENTS = ["lost everything to a fire that was no accident", "swore an oath over a grave and has kept it ever since",
          "stole something that was never meant to be found", "was spared by a monster and still doesn't know why",
          "found a sealed letter addressed to them in a dead stranger's pocket", "owes a life-debt to someone they've never met",
          "heard a voice in the dark offering a bargain"]
BONDS = ["protect the one person who still believes in them", "find the sibling who vanished on the king's road",
         "repay the debt to a mentor who died for them", "bring a stolen heirloom home", "prove their old order was framed"]
FLAWS = ["can't walk away from a dare", "trusts too quickly and forgives too slowly", "hoards trinkets and secrets alike",
         "talks to fill silence, usually saying too much", "believes rules are for other people", "never admits they're afraid"]


def _pick_class(name):
    if name:
        for k in CLASSES:
            if k.lower() == str(name).lower():
                return k
    return random.choice(list(CLASSES))


def _pick_race(name):
    if name:
        for k in RACES:
            if k.lower().replace("-", "") == str(name).lower().replace("-", "").replace(" ", ""):
                return k
    return random.choice(list(RACES))


def _pick_bg(name):
    if name:
        for k in BACKGROUNDS:
            if k.lower() == str(name).lower():
                return k
    return random.choice(list(BACKGROUNDS))


def random_name(race: str) -> str:
    r = RACES[race]
    return f"{random.choice(r['first'])} {random.choice(r['last'])}"


ASI_LEVELS = (4, 8, 12, 16, 19)


def _expertise_count(cls_name, level):
    """Rogue: two skills at 1st, two more at 6th. Bard: two at 3rd, two more at 10th."""
    if cls_name == "Rogue":
        return 2 * (1 + (level >= 6))
    if cls_name == "Bard":
        return 2 * ((level >= 3) + (level >= 10))
    return 0


def _speed_bonus(cls_name, level):
    """Monk Unarmored Movement (+10 at 2nd, rising to +30) and Barbarian Fast Movement (+10 at 5th)."""
    if cls_name == "Monk" and level >= 2:
        return 10 + 5 * ((level >= 6) + (level >= 10) + (level >= 14) + (level >= 18))
    if cls_name == "Barbarian" and level >= 5:
        return 10
    return 0


def _slots(spec, level):
    if spec == "full":
        return {str(i + 1): n for i, n in enumerate(FULL_SLOTS[level])}
    if spec == "half" and level >= 2:
        return {str(i + 1): n for i, n in enumerate(FULL_SLOTS[math.ceil(level / 2)])}
    if spec == "pact":
        count = 1 if level == 1 else 2 if level < 11 else 3 if level < 17 else 4
        slot_level = min(5, math.ceil(level / 2))
        return {str(slot_level): count}
    return {}


def make_character(name=None, race=None, character_class=None, level=1, background=None, concept=""):
    level = max(1, min(20, int(level or 1)))
    race = _pick_race(race)
    cls_name = _pick_class(character_class)
    bg = _pick_bg(background)
    cls, rc = CLASSES[cls_name], RACES[race]
    name = name or random_name(race)

    scores = dict(zip(cls["pri"], [15, 14, 13, 12, 10, 8]))
    for a, b in rc["asi"].items():
        scores[a] += b
    flex = [a for a in cls["pri"] if a not in rc["asi"]][: rc.get("flex", 0)]  # e.g. Half-Elf: two +1s of choice
    for a in flex:
        scores[a] += 1
    for lv in cls.get("asi_levels", ASI_LEVELS):
        if level >= lv:
            for a in cls["pri"]:
                if scores[a] <= 18:
                    scores[a] += 2
                    break
                if scores[a] < 20:
                    scores[a] += 1
                    break
    scores = {a: min(20, v) for a, v in scores.items()}
    mods = {a: mod(v) for a, v in scores.items()}
    prof = 2 + (level - 1) // 4

    hp = cls["hd"] + mods["con"] + (level - 1) * (cls["hd"] // 2 + 1 + mods["con"])
    hp = max(hp, level)

    acs = cls["ac"]
    if acs["kind"] == "fixed":
        ac = acs["v"]
    elif acs["kind"] == "unarmored":
        ac = 10 + mods["dex"] + mods[acs["stat"]]
    else:
        d = mods["dex"] if acs["cap"] is None else min(mods["dex"], acs["cap"])
        ac = acs["base"] + d

    saves = {a: {"bonus": mods[a] + (prof if a in cls["saves"] else 0), "prof": a in cls["saves"]} for a in ABILITIES}

    skill_prof = list(BACKGROUNDS[bg])
    options = [s for s in cls["skills"] if s not in skill_prof]
    skill_prof += random.sample(options, min(cls["nskills"], len(options)))
    extra_pool = [s for s in SKILLS if s not in skill_prof]  # Half-Elf Skill Versatility
    skill_prof += random.sample(extra_pool, min(rc.get("bonus_skills", 0), len(extra_pool)))
    expert = set(random.sample(skill_prof, min(_expertise_count(cls_name, level), len(skill_prof))))
    jack = cls_name == "Bard" and level >= 2  # Jack of All Trades: half proficiency on everything else
    skills = [{"name": s, "bonus": mods[a] + (2 * prof if s in expert else prof if s in skill_prof else prof // 2 if jack else 0),
               "prof": s in skill_prof, "expertise": s in expert, "ability": a}
              for s, a in sorted(SKILLS.items())]
    perception = next(s["bonus"] for s in skills if s["name"] == "Perception")

    n_attacks = 1 + sum(1 for lv in cls["extra"] if level >= lv)
    attacks = []
    for atk in cls["attacks"]:
        stat = atk["stat"]
        dice = atk["dice"]
        note = "Ranged" if atk.get("ranged") else "Melee"
        if dice == "MARTIAL":
            dice = "1d4" if level < 5 else "1d6" if level < 11 else "1d8" if level < 17 else "1d10"
        elif dice == "CANTRIP":
            dice = f"{1 + (level >= 5) + (level >= 11) + (level >= 17)}d10"
            note = "Cantrip, 120 ft"
        elif dice == "BLAST":
            beams = 1 + (level >= 5) + (level >= 11) + (level >= 17)
            dice = "1d10"
            note = f"Cantrip, {beams} beam{'s' if beams > 1 else ''}, 120 ft"
        add_mod = 0 if atk.get("spell") else mods[stat]
        attacks.append({"name": atk["name"], "to_hit": prof + mods[stat], "damage": f"{dice}{fmt(add_mod) if add_mod else ''}",
                        "note": note})
    if n_attacks > 1:
        attacks[0]["note"] += f" · {n_attacks} attacks per Attack action"
    if cls_name == "Rogue":
        attacks[0]["note"] += f" · Sneak Attack +{math.ceil(level / 2)}d6"

    features = [f for lv in sorted(cls["feats"]) if lv <= level for f in cls["feats"][lv]]
    spell = None
    if cls["caster"]:
        sm = mods[cls["cast_stat"]]
        slots = _slots(cls["caster"], level)
        if slots:
            spell = {"ability": cls["cast_stat"].upper(), "save_dc": 8 + prof + sm, "attack": prof + sm, "slots": slots,
                     "pact": cls["caster"] == "pact"}

    backstory = {
        "origin": f"{name.split()[0]} grew up in {random.choice(PLACES)}.",
        "hook": f"Years later, they {random.choice(EVENTS)}.",
        "bond": f"Now a {bg.lower()} turned {cls_name.lower()}, they are driven to {random.choice(BONDS)}.",
        "flaw": f"Flaw: {random.choice(FLAWS)}.",
    }
    return {
        "type": "character", "name": name, "race": race, "class": cls_name, "level": level, "background": bg,
        "abilities": {a: {"score": scores[a], "mod": mods[a]} for a in ABILITIES},
        "hp": hp, "ac": ac, "ac_note": acs["label"], "speed": rc["speed"] + _speed_bonus(cls_name, level),
        "initiative": mods["dex"] + (prof // 2 if jack else 0), "proficiency": prof,
        "saves": saves, "skills": skills, "passive_perception": 10 + perception, "attacks": attacks,
        "features": features, "racial_traits": rc["traits"], "spellcasting": spell,
        "equipment": cls["gear"], "backstory": backstory, "concept": concept or "",
    }


# ----------------------------------------------------------- encounters
CR_XP = {0: 10, 0.125: 25, 0.25: 50, 0.5: 100, 1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800, 6: 2300, 7: 2900, 8: 3900,
         9: 5000, 10: 5900, 11: 7200, 12: 8400, 13: 10000, 14: 11500, 15: 13000, 16: 15000, 17: 18000, 18: 20000,
         19: 22000, 20: 25000, 21: 33000}
XP_THRESH = {
    1: (25, 50, 75, 100), 2: (50, 100, 150, 200), 3: (75, 150, 225, 400), 4: (125, 250, 375, 500),
    5: (250, 500, 750, 1100), 6: (300, 600, 900, 1400), 7: (350, 750, 1100, 1700), 8: (450, 900, 1400, 2100),
    9: (550, 1100, 1600, 2400), 10: (600, 1200, 1900, 2800), 11: (800, 1600, 2400, 3600), 12: (1000, 2000, 3000, 4500),
    13: (1100, 2200, 3400, 5100), 14: (1250, 2500, 3800, 5700), 15: (1400, 2800, 4300, 6400), 16: (1600, 3200, 4800, 7200),
    17: (2000, 3900, 5900, 8800), 18: (2100, 4200, 6300, 9500), 19: (2400, 4900, 7300, 10900), 20: (2800, 5700, 8500, 12700),
}
DIFFS = ["easy", "medium", "hard", "deadly"]
MULTS = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5]
THEMES = ["any", "undead", "goblinoid", "beast", "humanoid", "giant", "dragon", "fiend", "aberration", "dungeon",
          "forest", "mountain", "swamp", "bandit", "cult"]


def cr_label(cr):
    return {0.125: "1/8", 0.25: "1/4", 0.5: "1/2"}.get(cr, str(int(cr)))


def _m(name, cr, hp, ac, atk, tags):
    return {"name": name, "cr": cr, "hp": hp, "ac": ac, "attack": atk, "tags": tags.split()}


MONSTERS = [
    _m("Kobold", 0.125, 5, 12, "Dagger +4, 1d4+2", "humanoid dragon dungeon"),
    _m("Cultist", 0.125, 9, 12, "Scimitar +3, 1d6+1", "humanoid cult dungeon"),
    _m("Bandit", 0.125, 11, 12, "Scimitar +3, 1d6+1", "humanoid bandit"),
    _m("Giant Rat", 0.125, 7, 12, "Bite +4, 1d4+2", "beast dungeon"),
    _m("Skeleton", 0.25, 13, 13, "Shortsword +4, 1d6+2", "undead dungeon"),
    _m("Zombie", 0.25, 22, 8, "Slam +3, 1d6+1", "undead dungeon"),
    _m("Goblin", 0.25, 7, 15, "Scimitar +4, 1d6+2", "goblinoid humanoid dungeon forest"),
    _m("Wolf", 0.25, 11, 13, "Bite +4, 2d4+2", "beast forest"),
    _m("Orc", 0.5, 15, 13, "Greataxe +5, 1d12+3", "humanoid mountain"),
    _m("Hobgoblin", 0.5, 11, 18, "Longsword +3, 1d8+1", "goblinoid humanoid"),
    _m("Shadow", 0.5, 16, 12, "Strength Drain +4, 2d6+2", "undead dungeon"),
    _m("Worg", 0.5, 26, 13, "Bite +5, 2d6+3", "beast goblinoid forest"),
    _m("Bugbear", 1, 27, 16, "Morningstar +4, 2d8+2", "goblinoid humanoid dungeon"),
    _m("Goblin Boss", 1, 21, 17, "Scimitar +4, 1d6+2", "goblinoid humanoid"),
    _m("Ghoul", 1, 22, 12, "Claws +4, 2d4+2 (paralysis)", "undead dungeon"),
    _m("Giant Spider", 1, 26, 14, "Bite +5, 1d8+3 + poison", "beast forest dungeon"),
    _m("Dire Wolf", 1, 37, 14, "Bite +5, 2d6+3", "beast forest"),
    _m("Animated Armor", 1, 33, 18, "Slam +4, 1d6+2", "construct dungeon"),
    _m("Bandit Captain", 2, 65, 15, "Scimitar +5, 1d6+3", "humanoid bandit"),
    _m("Ogre", 2, 59, 11, "Greatclub +6, 2d8+4", "giant mountain"),
    _m("Gelatinous Cube", 2, 84, 6, "Pseudopod +4, 3d6 acid", "ooze dungeon"),
    _m("Ghast", 2, 36, 13, "Claws +5, 2d6+3", "undead dungeon"),
    _m("Owlbear", 3, 59, 13, "Claws +7, 2d8+5", "beast forest"),
    _m("Wight", 3, 45, 14, "Longsword +4, 1d8+2", "undead dungeon"),
    _m("Mummy", 3, 58, 11, "Rotting Fist +5, 2d6+3", "undead dungeon"),
    _m("Doppelganger", 3, 52, 14, "Slam +6, 1d6+4", "aberration humanoid"),
    _m("Banshee", 4, 58, 12, "Corrupting Touch +4, 3d6", "undead"),
    _m("Ettin", 4, 85, 12, "Battleaxe +7, 2d8+5", "giant mountain"),
    _m("Troll", 5, 84, 15, "Claws +7, 2d6+4", "giant swamp"),
    _m("Vampire Spawn", 5, 82, 15, "Claws +6, 2d4+3", "undead fiend"),
    _m("Hill Giant", 5, 105, 13, "Greatclub +8, 3d8+5", "giant mountain"),
    _m("Wraith", 5, 67, 13, "Life Drain +6, 4d8+3", "undead"),
    _m("Mage", 6, 40, 12, "Dagger +5 / spells (fireball, counterspell)", "humanoid cult"),
    _m("Young Green Dragon", 8, 136, 18, "Bite +7, 2d10+4 · poison breath", "dragon forest swamp"),
    _m("Frost Giant", 8, 138, 15, "Greataxe +9, 3d12+6", "giant mountain"),
    _m("Young Red Dragon", 10, 178, 18, "Bite +10, 2d10+6 · fire breath 16d6", "dragon mountain"),
    _m("Vampire", 13, 144, 16, "Bite +9, 1d6+4 + 3d6 necrotic", "undead fiend"),
    _m("Purple Worm", 15, 247, 18, "Bite +14, 3d8+9 · swallow", "aberration dungeon"),
    _m("Balor", 19, 262, 19, "Longsword +14, 3d8+8 fire · Whip", "fiend"),
]

TACTICS = {
    "undead": "The horde advances without fear; any smart ones hang back and let the rank-and-file soak damage.",
    "goblinoid": "Hit-and-run: ambush from cover, disengage, and gang up on the squishiest target.",
    "beast": "They go for the isolated or wounded target and flee below a third of their HP.",
    "giant": "Simple plan, big hits: smash the nearest threat and hurl scenery at the casters.",
    "dragon": "Opens with breath, then takes to the air. Retreats when bloodied, and holds a grudge.",
    "fiend": "Prefers bargaining to brawling; offers a deal mid-fight, and the fine print bites.",
    "aberration": "Works on the mind first: confusion, mimicry, and splitting up the party.",
    "humanoid": "A leader gives orders; the weakest try to surrender. Someone always runs for reinforcements.",
}
SETTINGS = ["a collapsed mine shaft", "a moonlit forest road", "a flooded crypt", "a roadside shrine", "a burning farmstead",
            "a rope bridge over a chasm", "a candlelit chapel", "a rain-slick rooftop market"]
TWISTS = ["Hazard: the floor is slick; Dex save (DC 12) or fall prone when dashing.",
          "A bell, gong or alarm sounds when combat starts. Reinforcements arrive on round 4.",
          "Heavy fog: everything past 30 ft is lightly obscured.",
          "Something valuable is in the room, and both sides want it more than they want to win.",
          "A crumbling section of terrain collapses at the start of round 3.",
          "One foe is secretly a prisoner under duress and will switch sides if freed."]


def _mult(count, party_size):
    idx = 1 if count == 1 else 2 if count == 2 else 3 if count <= 6 else 4 if count <= 10 else 5 if count <= 14 else 6
    if party_size < 3:
        idx += 1
    elif party_size >= 6:
        idx -= 1
    return MULTS[max(0, min(idx, len(MULTS) - 1))]


def _adj(group, party_size):
    return sum(CR_XP[m["cr"]] for m in group) * _mult(len(group), party_size)


def make_encounter(party_level=3, party_size=4, difficulty="medium", theme="any"):
    level = max(1, min(20, int(party_level or 3)))
    size = max(1, min(10, int(party_size or 4)))
    difficulty = str(difficulty or "medium").lower()
    if difficulty not in DIFFS:
        difficulty = "medium"
    theme = str(theme or "any").lower()
    thresholds = {d: XP_THRESH[level][i] * size for i, d in enumerate(DIFFS)}
    budget = thresholds[difficulty]
    pool = [m for m in MONSTERS if theme == "any" or theme in m["tags"]]
    if not pool:
        pool, theme = MONSTERS, "any"
    def can_afford(m):
        return CR_XP[m["cr"]] * _mult(1, size) <= budget * 1.1

    affordable = [m for m in pool if can_afford(m)]
    if not affordable:  # nothing in this theme is small enough for the party: relax the theme rather than blow the budget
        affordable = [m for m in MONSTERS if can_afford(m)] or [min(MONSTERS, key=lambda m: m["cr"])]
        theme = "any"
    affordable.sort(key=lambda m: CR_XP[m["cr"]])
    best, best_score = None, 1e18
    for _ in range(500):
        anchor = random.choice(affordable[len(affordable) // 3:])
        group = [anchor]
        for _i in range(random.randint(0, 11)):
            cand = random.choice(group) if random.random() < 0.6 else random.choice(affordable)
            trial = group + [cand]
            if _adj(trial, size) <= budget * 1.1:
                group = trial
            else:
                break
        score = abs(_adj(group, size) - budget) + (len({m["name"] for m in group}) - 1) * budget * 0.03
        if score < best_score:
            best, best_score = group, score
    agg = {}
    for m in best:
        agg.setdefault(m["name"], {**m, "count": 0})["count"] += 1
    monsters = sorted(agg.values(), key=lambda m: -m["cr"])
    adjusted = _adj(best, size)
    actual = "trivial"
    for d in DIFFS:
        if adjusted >= thresholds[d]:
            actual = d
    tags = {t for m in monsters for t in m["tags"]}
    tactic = next((TACTICS[t] for t in ("undead", "dragon", "goblinoid", "giant", "fiend", "aberration", "beast", "humanoid")
                   if t in tags), "They fight smart and protect their leader.")
    setting = random.choice(SETTINGS)
    return {
        "type": "encounter", "title": f"{random.choice(['Ambush', 'Trouble', 'Skirmish', 'Showdown'])} at {setting}",
        "party_level": level, "party_size": size, "difficulty": actual, "requested": difficulty, "theme": theme,
        "thresholds": thresholds, "total_xp": sum(CR_XP[m["cr"]] for m in best), "adjusted_xp": int(adjusted),
        "monsters": [{"name": m["name"], "count": m["count"], "cr": cr_label(m["cr"]), "hp": m["hp"], "ac": m["ac"],
                      "attack": m["attack"], "xp": CR_XP[m["cr"]]} for m in monsters],
        "tactics": tactic, "twist": random.choice(TWISTS),
    }


# ----------------------------------------------------------------- loot
GEMS = ["amber", "jade", "garnet", "moonstone", "opal", "black pearl", "sapphire", "star ruby"]
MAGIC = {
    "common": ["Potion of Healing", "Spell Scroll (cantrip)", "Driftglobe", "Moon-Touched Sword", "Cloak of Billowing"],
    "uncommon": ["+1 Weapon", "Bag of Holding", "Cloak of Protection", "Boots of Elvenkind", "Wand of Magic Detection",
                 "Potion of Greater Healing", "Gauntlets of Ogre Power", "Goggles of Night"],
    "rare": ["+2 Weapon", "Flame Tongue", "Cloak of Displacement", "Ring of Protection", "Wand of Fireballs", "Boots of Speed",
             "Ring of Spell Storing", "Potion of Superior Healing"],
    "very rare": ["+3 Weapon", "Robe of Stars", "Staff of Power", "Ring of Regeneration", "Dragon Scale Mail", "Rod of Lordly Might"],
    "legendary": ["Vorpal Sword", "Staff of the Magi", "Holy Avenger"],
}


def make_loot(party_level=3, hoard=False):
    lvl = max(1, min(20, int(party_level or 3)))
    tier = 1 if lvl <= 4 else 2 if lvl <= 10 else 3 if lvl <= 16 else 4
    gp = total("2d6") * {1: 5, 2: 25, 3: 200, 4: 1000}[tier] * (3 if hoard else 1)
    sp = total("3d6") * 10 if tier <= 2 else 0
    weights = {1: (60, 30, 9, 1, 0), 2: (20, 45, 30, 5, 0), 3: (5, 20, 45, 28, 2), 4: (0, 10, 30, 50, 10)}[tier]
    rarities = ["common", "uncommon", "rare", "very rare", "legendary"]
    n_items = total("1d4") if hoard else (1 if random.random() < 0.4 else 0)
    items = []
    for _ in range(n_items):
        r = random.choices(rarities, weights)[0]
        items.append({"name": random.choice(MAGIC[r]), "rarity": r})
    gem_value = {1: 10, 2: 50, 3: 500, 4: 1000}[tier]
    gems = [{"name": random.choice(GEMS), "value": gem_value} for _ in range(total("1d4") if hoard else 0)]
    return {"type": "loot", "hoard": bool(hoard), "tier": tier, "party_level": lvl, "gp": gp, "sp": sp, "gems": gems, "items": items}


# ------------------------------------------------------------------ npcs
ROLES = ["innkeeper", "blacksmith", "merchant", "guard captain", "priest", "fence", "hedge wizard", "sage", "farmer", "noble",
         "smuggler", "bard", "healer", "ferryman", "assassin", "cultist"]
APPEARANCE = ["a wine-stained apron and a sharp stare", "a scar that disappears into a grey beard", "far too many rings",
              "ink-stained fingers and sleepless eyes", "an immaculate coat that doesn't match the neighbourhood",
              "a limp they never explain", "a voice much quieter than their frame suggests"]
VOICE = ["speaks in a slow whisper", "laughs at their own jokes", "hums while thinking", "never uses contractions",
         "ends every sentence like a question", "gruff and clipped, like paying by the word", "over-friendly, calls everyone 'friend'"]
TRAITS = ["fiercely loyal", "quietly greedy", "endlessly curious", "terrified of being noticed", "proud to a fault", "gently sarcastic"]
WANTS = ["to see their rival ruined", "enough coin to leave town", "news of a missing child", "to be left completely alone",
         "a rare ingredient only found in the old crypt", "someone brave enough to carry a letter"]
SECRETS = ["is secretly in debt to the local thieves' guild", "sold out the last group of adventurers who came through",
           "knows where the cult meets and has been too afraid to say", "is not who they claim to be",
           "is slowly being replaced by something that wears their face", "found a map in a dead man's coat and told no one"]
ATTITUDES = ["friendly", "wary", "indifferent", "hostile", "desperate", "scheming"]


def make_npc(role=None, race=None):
    race = _pick_race(race)
    role = role or random.choice(ROLES)
    return {
        "type": "npc", "name": random_name(race), "race": race, "role": role, "appearance": random.choice(APPEARANCE),
        "voice": random.choice(VOICE), "trait": random.choice(TRAITS), "wants": random.choice(WANTS),
        "secret": random.choice(SECRETS), "attitude": random.choice(ATTITUDES),
    }
