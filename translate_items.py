#!/usr/bin/env python3
import os
import csv

TRANSLATIONS = {
    # Mushrooms & Plants
    "オーロット茸": "Orot Mushroom",
    "ペブロット茸": "Pebrot Mushroom",
    "メルバグ茸": "Melbug Mushroom",
    "ベルボグ茸": "Belbog Mushroom",
    "カドリの実": "Kadri Fruit",
    "フルボの実": "Furbo Fruit",
    "ベリアスの胞子": "Velias Spores",
    "フバの穂": "Huba Spike",
    
    # Armors & Clothes
    "革の防具": "Leather Armor",
    "リングメイル": "Ring Mail",
    "ハーフプレート": "Half Plate",
    "ヘビーアーマー": "Heavy Armor",
    "フルプレート": "Full Plate",
    "レイラント革鎧": "Leylant Leather Armor",
    "レイラント甲冑": "Leylant Plate Armor",
    "アルセナの聖鎧": "Alsena's Holy Armor",
    "麻のローブ": "Linen Robe",
    "木綿のローブ": "Cotton Robe",
    "厚手のローブ": "Heavy Robe",
    "絹のローブ": "Silk Robe",
    "学者のローブ": "Scholar's Robe",
    "金糸のローブ": "Gold-Thread Robe",
    "純白のローブ": "Pure White Robe",
    "真紅のローブ": "Crimson Robe",
    "カレイドンの衣": "Caleidon's Garment",

    # Daggers & Assassination
    "石の短剣": "Stone Dagger",
    "翡翠の短剣": "Jade Dagger",
    "銀 of 懐剣": "Silver Dirk",
    "銀の懐剣": "Silver Dirk",
    "三日月の短剣": "Crescent Dagger",
    "ブラックダガー": "Black Dagger",
    "アサシンソード": "Assassin Sword",
    "ダークブレード": "Dark Blade",
    "ニンジャソード": "Ninja Blade",
    "カムジの脇差": "Kamji's Wakizashi",

    # Amulets / Talismans
    "キシュの護符": "Kishu Amulet",
    "大地の護符": "Earth Amulet",
    "流れ星の護符": "Meteor Amulet",
    "綺羅星の護符": "Glitter Star Amulet",
    "箒星の護符": "Comet Amulet",
    "明星の護符": "Morning Star Amulet",
    "月明かりの護符": "Moonlight Amulet",
    "陽光の護符": "Sunlight Amulet",
    "天穹の護符": "Celestial Amulet",
    
    # Brooches
    "雀のブローチ": "Sparrow Brooch",
    "燕のブローチ": "Swallow Brooch",
    "鴉のブローチ": "Raven Brooch",
    "梟のブローチ": "Owl Brooch",
    "隼のブローチ": "Falcon Brooch",
    "鷹のブローチ": "Hawk Brooch",
    "鷲のブローチ": "Eagle Brooch",
    "孔雀のブローチ": "Peacock Brooch",
    "鳳凰 of ブローチ": "Phoenix Brooch",
    "鳳凰のブローチ": "Phoenix Brooch",

    # Shields
    "オーク材の盾": "Oak Shield",
    "青銅の盾": "Bronze Shield",
    "くろがねの大盾": "Iron Greatshield",
    "鋼鉄の盾": "Steel Shield",
    "白銀の盾": "Silver Shield",
    "黄金の盾": "Gold Shield",
    "プラチナの大盾": "Platinum Greatshield",
    "竜鱗の大盾": "Dragon Scale Shield",
    "ミスリルの大盾": "Mithril Greatshield",

    # Chimes, Bells & Rattles
    "真鍮のがらがら": "Brass Rattle",
    "骨のがらがら": "Bone Rattle",
    "硝子の鈴": "Glass Bell",
    "幸運の鈴": "Bell of Fortune",
    "宿命の鐘": "Chime of Fate",
    "星辰の鐘": "Astral Chime",
    "ドラグーンベル": "Dragoon Bell",

    # Mirrors
    "シーリンドの鏡": "Sealind Mirror",
    "逆巻きの鏡": "Reversal Mirror",
    "退魔の水鏡": "Exorcism Water Mirror",
    "破邪の御鏡": "Holy Warding Mirror",

    # Grimoires & Principles
    "剣術の初歩": "Basics of Swordplay",
    "剣法の心得": "Principles of Swordplay",
    "長旅の日記": "Long Journey Diary",
    "旅の回顧録": "Memoirs of Travel",
    "旅人の伝記": "Biography of Traveler",
    "旅人の追想録": "Reminiscences of Traveler",
    "旅人の旅行記": "Travelogue of Traveler",
    "アクラル年代記": "Akral Chronicles",
    "ジャジルの手記": "Jazil's Memoirs",
    "バリウスの書": "Book of Varius",
    "魔術の手ほどき": "Introduction to Magic",
    "上位魔法の書": "Book of High Magic",
    "高等魔術の書": "Grimoire of Advanced Magic",
    "地獄の辞典": "Dictionary of Hell",
    "エイボンの書": "Book of Eibon",
    "ネクロノミコン": "Necronomicon",
    "モルサガルサ書": "Book of Molsagarsa",
    "ダルガール教本": "Dargar Manual",
    "カルデロン教典": "Calderon Canon",
    "蛇の祈祷書": "Serpent Prayerbook",
    "クルクリムの書": "Book of Kurukurim",
    "シミュエラ写本": "Simuela Manuscript",

    # Cursed / Demon Swords
    "災いの剣": "Calamity Sword",
    "呪いの剣": "Cursed Sword",
    "降魔の剣": "Exorcist Sword",
    "血の魔剣": "Bloody Demon Sword",
    "影の魔剣": "Shadow Demon Sword",
    "夜の魔剣": "Night Demon Sword",
    "黒の魔剣ゲナウ": "Black Sword Genau",
    "闇の魔剣ガドス": "Dark Sword Gados",
    "死の魔剣ギイ": "Death Sword Gii",

    # Boots & Shoes
    "ロングブーツ": "Long Boots",
    "音無しの靴": "Silent Shoes",
    "早駆け靴": "Quick-step Shoes",
    "風乗り靴": "Wind-rider Shoes",
    "ひとまたぎの靴": "Giant-stride Shoes",
    "千里の長靴": "Thousand-league Boots",
    "双翼の靴": "Winged Shoes",

    # Swords
    "ロングソード": "Longsword",
    "ブロードソード": "Broadsword",
    "ルーンソード": "Runesword",
    "ミョルニール": "Mjolnir",
    "エクスカリバー": "Excalibur",
    "レーヴァテイン": "Laevateinn",
    "グングニール": "Gungnir",
    "竜殺しの大剣": "Dragon Slayer Greatsword",
    "大剣ベルガンド": "Greatsword Belgand",
    "カネシゲ": "Kaneshige",
    "キヨミツ": "Kiyomitsu",
    "カネサダ": "Kanesada",
    "キクイチモンジ": "Kiku-ichimonji",
    "オサフネ": "Osafune",
    "ムラマサ": "Muramasa",
    "マサムネ": "Masamune",
    "クサナギ": "Kusanagi",
    "アルファスの剣": "Sword of Alphas",
    "パリアモンの杖": "Staff of Paliamon",
    "ミディアの帯": "Midia's Sash",
    "キュリクの兜": "Helm of Kyulik",
    "大魔女の高帽子": "Archwitch's Tall Hat",
    "女神の涙": "Tear of the Goddess",
    "がらくた": "Junk",

    # Cloaks / Capes
    "黄昏のマント": "Twilight Cloak",
    "薄暮のマント": "Dusk Cloak",
    "宵のマント": "Evening Cloak",
    "月のマント": "Moon Cloak",
    "薄明りのマント": "Glimmer Cloak",
    "朝まだきの衣": "Dawn Garment",
    "暁のマント": "Sunrise Cloak",
    "曙のマント": "Daybreak Cloak",

    # Staves / Wands
    "蝙蝠の杖": "Bat Staff",
    "大鴉の杖": "Raven Staff",
    "黒猫の杖": "Black Cat Staff",
    "猟犬の杖": "Hound Staff",
    "巨狼の杖": "Great Wolf Staff",
    "毒蛇の杖": "Serpent Staff",
    "猛虎の杖": "Tiger Staff",
    "獅子王の杖": "Lion King Staff",
    "竜帝の杖": "Dragon Emperor Staff",

    # Rings
    "愚者の指輪": "Fool's Ring",
    "皇帝の指輪": "Emperor's Ring",
    "司祭の指輪": "Priest's Ring",
    "正義の指輪": "Ring of Justice",
    "隠者の指輪": "Hermit's Ring",
    "運命の指輪": "Ring of Destiny",
    "力の指輪": "Ring of Strength",
    "審判の指輪": "Ring of Judgement",
    "世界の指輪": "World Ring",
    "シロンの指輪": "Ring of Silon",

    # Bracers
    "秋の腕輪": "Autumn Bracelet",
    "落葉の腕輪": "Falling Leaf Bracelet",
    "霜の腕輪": "Frost Bracelet",
    "冬の腕輪": "Winter Bracelet",
    "氷の腕輪": "Ice Bracelet",
    "春の腕輪": "Spring Bracelet",
    "新緑の腕輪": "Fresh Verdure Bracelet",
    "雷の腕輪": "Thunder Bracelet",
    "夏至の腕輪": "Solstice Bracelet",

    # Maces & Hammers
    "裁きのメイス": "Mace of Judgement",
    "掟のメイス": "Mace of Law",
    "戒律のメイス": "Mace of Discipline",
    "法のメイス": "Mace of Law",
    "罰のメイス": "Mace of Punishment",
    "断罪の槌": "Hammer of Condemnation",
    "統治の槌": "Hammer of Governance",
    "君主の槌": "Hammer of Sovereignty",
    "聖なる槌ラウロ": "Sacred Hammer Lauro",

    # Consumables / Potions / Drops
    "森の薬草": "Forest Herb",
    "旅人の薬": "Traveler's Medicine",
    "魔女の妙薬": "Witch's Elixir",
    "哲人の良薬": "Philosopher's Remedy",
    "賢者の秘薬": "Sage's Elixir",
    "聖者の霊薬": "Saint's Panacea",
    "ネクタル": "Nectar",
    "アンブロシア": "Ambrosia",
    "エリクサー": "Elixir",
    "成育の雫": "Dew of Growth",
    "治療 of 雫": "Dew of Healing",
    "治療の雫": "Dew of Healing",
    "妖精の雫": "Pixie Dew",
    "癒しの雫": "Dew of Recovery",
    "快癒の雫": "Dew of Restoration",
    "根治の雫": "Dew of Remedy",
    "回春の雫": "Dew of Rejuvenation",
    "精霊の雫": "Spirit Dew",
    "賢者の石": "Philosopher's Stone",

    # Helms
    "兵士の兜": "Soldier's Helm",
    "騎士の兜": "Knight's Helm",
    "男爵の兜": "Baron's Helm",
    "子爵の兜": "Viscount's Helm",
    "伯爵の兜": "Count's Helm",
    "侯爵の兜": "Marquis's Helm",
    "公爵の兜": "Duke's Helm",
    "皇帝の兜": "Emperor's Helm",

    # Bows
    "狩人の弓": "Hunter's Bow",
    "猟師の弓": "Huntsman's Bow",
    "エルヴン・ボウ": "Elven Bow",
    "ティゴルの強弓": "Tigol Greatbow",
    "森の精の弓": "Dryad Bow",
    "ヴィルマの弓": "Wilma's Bow",
    "星々の大弓": "Greatbow of Stars",
    "神弓ミルーシュ": "Divine Bow Milush",

    # Arrowheads
    "石の矢尻": "Stone Arrowhead",
    "骨の矢尻": "Bone Arrowhead",
    "鉄の矢尻": "Iron Arrowhead",
    "黒曜石の矢尻": "Obsidian Arrowhead",
    "ティゴルの矢尻": "Tigol Arrowhead",
    "銀の矢尻": "Silver Arrowhead",
    "ヴィルマの矢尻": "Wilma's Arrowhead",
    "破魔の矢尻": "Warding Arrowhead",
    "神罰の矢尻": "Divine Wrath Arrowhead",

    # Arrows
    "白木の矢": "Whitewood Arrow",
    "バルキア銅の矢": "Valkian Copper Arrow",
    "ティゴルの木矢": "Tigol Wooden Arrow",
    "アティアの毒矢": "Atia's Poison Arrow",
    "ヴィルマの矢": "Wilma's Arrow",
    "ゾカールの火矢": "Zokar's Fire Arrow",
    "キアスの光の矢": "Kias's Arrow of Light",

    # Feathers
    "ヒバリの羽飾り": "Lark Feather Ornament",
    "オウムの羽飾り": "Parrot Feather Ornament",
    "白鳥の羽飾り": "Swan Feather Ornament",
    "キメラの羽飾り": "Chimera Feather Ornament",
    "グリフォンの羽": "Gryphon Feather",
    "ペガサスの羽": "Pegasus Feather",
    "不死鳥の羽": "Phoenix Feather",
    "シムルグの羽": "Simurgh Feather",
    "天使の羽飾り": "Angel Feather Ornament",

    # Belts
    "革のベルト": "Leather Belt",
    "鉄のベルト": "Iron Belt",
    "鋼のベルト": "Steel Belt",
    "力のベルト": "Belt of Strength",
    "知恵のバンド": "Band of Wisdom",
    "勇気のバンド": "Band of Courage",
    "名誉のバンド": "Band of Honor",
    "金色の魔法帯": "Golden Magic Sash",
    "精霊の腰帯": "Spirit Sash",

    # Emblems / Crests
    "勝利の紋章": "Crest of Victory",
    "友愛の紋章": "Crest of Fellowship",
    "道徳の紋章": "Crest of Morality",
    "信義の紋章": "Crest of Fidelity",
    "誠実の紋章": "Crest of Sincerity",
    "正義の紋章": "Crest of Justice",
    "秩序の紋章": "Crest of Order",
    "摂理の紋章": "Crest of Providence",
    "叡知の紋章": "Crest of Wisdom",

    # Special Swords
    "水晶剣カディス": "Crystal Sword Cadis",
    "氷の剣リキア": "Ice Sword Likia",
    "月の剣カーン": "Moon Sword Kahn",
    "白の剣ドゥアト": "White Sword Duat",
    "銀の剣ティラナ": "Silver Sword Tilana",
    "光の剣フアナ": "Light Sword Juana",
    "霊剣メルギベル": "Spirit Sword Mergibel",
    "冥剣フルモール": "Nether Sword Fulmol",
    "聖剣ビルダリク": "Holy Sword Vildarik",

    # Crystals & Relics
    "虹の水晶": "Rainbow Crystal",
    "瞬きの水晶球": "Twinkling Crystal Ball",
    "タロスの水晶": "Talos Crystal",
    "キーディスの珠": "Jewel of Kidis",
    "大地の要石": "Earth Keystone",
    "太陽の骨": "Sun Bone",
    "七つ石の大宝玉": "Great Gem of Seven Stones",

    # Flutes & Horns
    "翡翠の笛": "Jade Flute",
    "オーギスの銀笛": "Ogis's Silver Flute",
    "ベリアスの縦笛": "Velias Recorder",
    "一角獣の角笛": "Unicorn Horn",
    "竜の角笛": "Dragon Horn",
    "精霊の葉笛": "Spirit Leaf Flute",

    # Ankhs
    "博愛のアンク": "Ankh of Philanthropy",
    "信仰のアンク": "Ankh of Faith",
    "献身のアンク": "Ankh of Devotion",
    "犠牲のアンク": "Ankh of Sacrifice",
    "祝福のアンク": "Ankh of Blessing",
    "生命のアンク": "Ankh of Life",
    "復活のアンク": "Ankh of Resurrection",
    "精霊のアンク": "Ankh of Spirits",
    "栄光のアンク": "Ankh of Glory",

    # Masks
    "爪のマスク": "Claw Mask",
    "角の仮面": "Horned Mask",
    "翼のマスク": "Winged Mask",
    "牙のマスク": "Fang Mask",
    "風鬼の仮面": "Wind Demon Mask",
    "火妖の仮面": "Fire Sprite Mask",
    "樹霊の仮面": "Tree Spirit Mask",
    "水精の仮面": "Water Pixie Mask",
    "大地の仮面": "Earth Mask",

    # Earrings
    "琥珀のピアス": "Amber Earrings",
    "瑪瑙のピアス": "Agate Earrings",
    "真珠のピアス": "Pearl Earrings",
    "銀のピアス": "Silver Earrings",
    "金のピアス": "Gold Earrings",
    "白金のピアス": "Platinum Earrings",
    "ダイアのピアス": "Diamond Earrings",
    "妖精の耳飾り": "Pixie Earrings",
    "精霊の耳飾り": "Spirit Earrings",

    # Statues
    "野獣の像": "Statue of Wild Beast",
    "魔物の像": "Statue of Fiend",
    "妖精の像": "Statue of Pixie",
    "神竜の像": "Statue of Divine Dragon",
    "精霊の像": "Statue of Spirit",
    "大精霊の像": "Statue of Great Spirit",
    "霊魂の像": "Statue of Soul",
    "始祖の像": "Statue of Ancestor",

    # Chalices
    "天使の聖杯": "Chalice of Angel",
    "大天使の聖杯": "Chalice of Archangel",
    "権天使の聖杯": "Chalice of Principalities",
    "能天使の聖杯": "Chalice of Powers",
    "力天使の聖杯": "Chalice of Virtues",
    "主天使の聖杯": "Chalice of Dominions",
    "座天使の聖杯": "Chalice of Thrones",
    "智天使の聖杯": "Chalice of Cherubim",
    "熾天使の聖杯": "Chalice of Seraphim",

    # Artifacts
    "冥王の爪": "Claw of the Nether King",
    "神鉄の縛鎖": "Divine Iron Chain",
    "守護の塔": "Tower of Protection",
    "無敗の砦": "Fortress of Invincibility",
    "神智の石版": "Tablet of Divine Wisdom",
    "虹色の聖盤": "Iridescent Sacred Disk",
    "七叉の尻尾": "Seven-pronged Tail",
}

def main():
    csv_path = "translation_catalog_split/UI_ItemName.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    rows = []
    headers = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            rows.append(row)

    # Columns: File, Index/Offset, OriginalText, EnglishTranslation, Notes, Context
    translated_count = 0
    missing = set()

    for row in rows:
        orig = row[2]
        if orig in TRANSLATIONS:
            row[3] = TRANSLATIONS[orig]
            translated_count += 1
        else:
            missing.add(orig)

    if missing:
        print(f"[-] Warning: {len(missing)} items are missing translations:")
        for item in sorted(missing):
            print(f"  * {item}")
    else:
        print(f"[+] All {len(rows)} item entries successfully mapped!")

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote {translated_count} translations to {csv_path}.")

if __name__ == "__main__":
    main()
