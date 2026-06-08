#!/usr/bin/env python3
import os
import csv

TRANSLATIONS = {
    "フーマック": "Fumac",
    "シーボック": "Seabock",
    "バムレック": "Bamrec",
    "モーンレック": "Mornrec",
    "イグラス諸島": "Iglass Islands",
    "リオン地方": "Lion Region",
    "旧レイラント領": "Former Leilant Territory",
    "ノースランド": "Northland",
    "ウォルタランド": "Walterland",
    "南アクラル": "South Acral",
    "エルフランド": "Elfland",
    "ソーサランド": "Sorsaland",
    "アクラリンド": "Acrarind",
    "アッシュ": "Ash",
    "ゲフャッハー": "Gefyacher",
    "アーチャー": "Archer",
    "ヴァルキリー": "Valkyrie",
    "サムライ": "Samurai",
    "ニンジャ": "Ninja",
    "ユニコーン": "Unicorn",
    "モールニー": "Mourny",
    "ウンディーネ": "Undine",
    "インフェルノ": "Inferno",
    "エアリー": "Airy",
    "ラキシュ": "Lakish",
    "アマノミツルギ": "Amano-Mitsurugi",
    "ファフニール": "Fafnir",
    "鉱山の街 バルクウェイ": "Mining Town Barakway",
    "水上都市 スクーレ": "Water City Sukure",
    "王都 ヴァレイ": "Royal Capital Valey",
    "山間の町 フェルミナ": "Mountain Town Fermina",
    "湾岸都市 メゾネア": "Coastal City Mezonea",
    "城塞都市 ゼレス": "Fortress City Zeres",
    "魔法都市 ウェロ－": "Magic City Wellow",
    "モールモース": "Molmorth",
    "モルサガルサ": "Molsagarsa",
    "リーヴェ修道院": "Rieve Monastery",
    "ティゴル谷": "Tigor Valley",
    "マリスベイの村": "Malice Bay Village",
    "港町イルグール": "Port Town Ilgull",
    "バルサリオンの中継地": "Baltharion Waystation",
    "ライカンウッド": "Lycanwood",
    "キングリオン": "King Lion",
    "極寒のシーラ": "Frigid Sheela",
    "レイラントの街": "Leilant Town",
    "オスト村": "Ost Village",
    "サンパロスの街": "San Palos Town",
    "宗教都市グラツィア": "Holy City Grazia",
    "ベリアス森の村": "Village of Velias Forest",
    "カルランの街": "Callan Town",
    "夜の都ジグー": "City of Night Jigu",
    "ゴルドアの村": "Goldor Village",
    "白炎の村": "White Flame Village",
    "フランカの里": "Franca Village",
    "幻の村アゼル": "Phantom Village Azer",
    "エルフィン・バレイ": "Elfin Valley",
    "ゼッタの村": "Zetta Village",
    "ハーレィの村": "Harley Village",
    "マリスの船着場": "Malice Pier",
    "リオンの船着場": "Lion Pier",
    "イルグール港": "Ilgull Port",
    "バルサリオンの船着場": "Baltharion Pier",
    "極北の船着場": "Far North Pier",
    "最果ての港": "Port at World's End",
    "エルフの船着場": "Elf Pier",
    "肋骨岬の船着場": "Rib Cape Pier",
    "メゾネア港": "Mezonea Port",
    "オルボガルボの船着場": "Orbogarbo Pier",
    "セロの実の丘": "Celo Fruit Hill",
    "クリス坑道": "Chris Mine",
    "月見の森": "Moonview Forest",
    "クロコ山": "Mount Croco",
    "キーディス山脈": "Kiydis Mountains",
    "レイラントの砦": "Leilant Fortress",
    "惑わしの森": "Forest of Illusion",
    "湖の宿場": "Lake Inn",
    "カーンデルムの森": "Kahnderm Forest",
    "ウルカ峠の村": "Uruka Pass Village",
    "キーラの里": "Keera Village",
    "デナスの農村": "Denas Farm Village",
    "フラムバラムの街": "Flambaram Town",
    "ハイメープル農園": "High Maple Plantation",
    "モーガの砦町": "Fortress Town Moga",
    "サイラス寺院": "Silas Temple",
    "山麓 of 宿場": "Foothill Inn",  # Wait, let's make sure this matches exactly
    "山麓の宿場": "Foothill Inn",
    "デリー農村": "Derry Farm Village",
    "ガレス湾の集落": "Gareth Bay Settlement",
    "バルセールの街": "Balseer Town",
    "死都ジグー": "Dead City Jigu",
    "精霊の胎道": "Spirit Womb Path",
    "ウルの塔": "Tower of Ur",
    "カントレル山の洞窟": "Mount Kantrel Cave",
    "ほのお山の洞窟": "Mount Flame Cave",
    "凍土の森": "Frozen Forest",
    "タロスの顎": "Talos' Jaw",
    "レヴァス山の洞窟": "Mount Levas Cave",
    "ジャリガートの洞窟": "Jaligat Cave",
    "ケミー砦": "Kemy Fortress",
    "吸血鬼の古城": "Vampire's Old Castle",
    "バルク山道": "Barak Mountain Pass",
    "聖女 of 道": "Saint's Path",
    "聖女の道": "Saint's Path",
    "西レヴァス山道": "West Levas Mountain Pass",
    "東レヴァス山道": "East Levas Mountain Pass",
    "ケープ島": "Cape Island",
    "アラクリム島": "Alacrim Island",
    "グリール島": "Greal Island",
    "グラル島": "Gral Island",
    "罪人の島": "Island of Sinners",
    "グリナス島": "Grinas Island",
    "グリシア島": "Gricia Island",
    "コープ島": "Cope Island",
    "かけら島": "Shard Island",
    "三つ子山": "Triplet Mountains",
    "レミントン山": "Mount Remington",
    "イヴァレス山": "Mount Ivares",
    "セヴァリ山": "Mount Sevari",
    "タロスの角": "Talos' Horn",
    "ベリアス湿地帯": "Velias Wetlands",
    "グランタロス湖": "Gran Talos Lake",
    "エルフの湖": "Elf Lake",
    "カントレル山": "Mount Kantrel",
    "ムカデ草の森": "Centipede Grass Forest",
    "ほのお山": "Mount Flame",
    "狼男の森": "Werewolf Forest",
    "旅人の森": "Traveler's Forest",
    "聖ベリアス樹海": "Sacred Velias Forest",
    "吸血鬼の森": "Vampire's Forest",
    "レイラス山脈": "Leyras Mountains",
    "ガレシア山脈": "Galesia Mountains",
    "祈りの山": "Mountain of Prayer",
    "バルク山": "Mount Barak",
    "ウシドリの森": "Cow-Bird Forest",
    "ヨモギシダの森": "Mugwort Fern Forest",
    "ティゴルの森": "Tigor Forest",
    "山麓の森": "Foothill Forest",
    "ディアレイ山": "Mount Diarey",
    "レヴァス高地": "Levas Highlands",
    "ケミー山脈": "Kemy Mountains",
    "ミディア連峰": "Midia Mountain Range",
    "エルデディル山": "Mount Erdedil",
    "オトラ山": "Mount Otra",
    "シロガネゴケの森": "Silver Moss Forest",
    "フェアリールビーの森": "Fairy Ruby Forest",
    "セントマリーの森": "Saint Mary's Forest",
    "死者の森": "Forest of the Dead",
    "幻視の樹海": "Forest of Visions",
    "エルフの森": "Elf Forest",
    "ケムの森": "Kem Forest",
    "ヒドラの樹海": "Hydra Forest",
    "シュケルの森": "Schukel Forest",
    "デュアリクの森": "Dualik Forest",
    "シャマクの森": "Shamak Forest",
    "あかつきの森": "Forest of Dawn",
    "誓いの森": "Forest of Vows",
    "しじまの森": "Forest of Silence",
    "エルデクエデリの森": "Erdequederi Forest",
    "さえずりの森": "Chirping Forest",
    "タロスの髭": "Talos' Beard",
    "フェルミナの森": "Fermina Forest",
    "狩りの森": "Hunting Forest",
    "フクロウの森": "Owl Forest",
    "修行者の森": "Ascetic Forest",
    "ウォルター平原": "Walter Plains",
    "デリー台地": "Derry Heights",
    "シルズの凍土": "Sils Tundra",
    "グール島": "Gool Island",
    "リオン荒野": "Lion Wasteland"
}

def main():
    csv_path = "translation_catalog_split/UI_LocationName.csv"
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

    translated_count = 0
    missing = set()

    for row in rows:
        orig = row[2]
        orig_clean = orig.strip()
        matched = False
        for k, v in TRANSLATIONS.items():
            if k.strip() == orig_clean:
                row[3] = v
                matched = True
                translated_count += 1
                break
        
        if not matched:
            missing.add(orig)

    if missing:
        print(f"[-] Warning: {len(missing)} entries are missing translations:")
        for item in sorted(missing):
            print(f"  * {repr(item)}")
    else:
        print(f"[+] All {len(rows)} Location entries successfully mapped!")

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote {translated_count} translations to {csv_path}.")

if __name__ == "__main__":
    main()
