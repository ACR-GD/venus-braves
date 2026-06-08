#!/usr/bin/env python3
import os
import csv
import re

def csv_to_python(s):
    def repl(m):
        return chr(int(m.group(1), 16))
    return re.sub(r"\\x([0-9A-Fa-f]{2})", repl, s)

def python_to_csv(s):
    if not isinstance(s, str):
        return s
    res = []
    for char in s:
        o = ord(char)
        if o < 0x20 and char not in ("\n", "\r", "\t"):
            res.append(f"\\x{o:02X}")
        else:
            res.append(char)
    return "".join(res)

TITLE_TRANSLATIONS = {
    "はじめに": "Introduction",
    "アイテム": "Items",
    "アイテムの成長": "Item Growth",
    "アカガエルの池": "Red Frog Pond",
    "アーチャー": "Archer",
    "オプション": "Options",
    "クリティカルチャージ": "Critical Charge",
    "ゲームの説明": "About the Game",
    "ゴーレム山賊団アジト": "Golem Bandit Hideout",
    "セーブ": "Saving",
    "パラメータ": "Parameters",
    "フェーズについて": "About Phases",
    "リファレンス": "Reference",
    "リファレンスについて": "About Reference",
    "ルールの説明": "Rules Explanation",
    "レベル": "Levels",
    "レーダー": "Radar",
    "ローテーション": "Rotation",
    "ワンポイントアドバイス": "Advice & Tips",
    "世界地図": "World Map",
    "世界記録": "World Records",
    "予測安全値": "Forecast Safety Value",
    "人間関係": "Relationships",
    "仲間を募集": "Recruit Allies",
    "仲間達の様子": "Status of Allies",
    "会心攻撃": "Critical Attack",
    "僧侶": "Priest",
    "出産と子供": "Birth and Children",
    "剣闘士": "Gladiator",
    "勇者たちの酒場": "Heroes' Tavern",
    "友情": "Friendship",
    "友情～精霊招喚": "Friendship - Spirit Summon",
    "噂を聞く": "Hear Rumors",
    "回復": "Healing",
    "坑夫たちの酒場": "Miners' Tavern",
    "基本操作": "Basic Controls",
    "基本的な遊び方": "Basic Gameplay",
    "墓場": "Cemetery",
    "女神と話す": "Talk with Goddess",
    "属性": "Attributes",
    "年齢と成長": "Age and Growth",
    "幻術師": "Illusionist",
    "引退する": "Retire",
    "強さ": "Strength",
    "恋愛": "Romance",
    "恋愛～プロポーズ": "Romance - Proposal",
    "恋愛～結婚": "Romance - Marriage",
    "情報屋でのセーブ": "Save at Info Broker",
    "情報屋での人の入れ替え": "Swap Allies at Info Broker",
    "戦士": "Warrior",
    "戦歴": "Battle History",
    "戦闘": "Battle",
    "戦闘の操作": "Battle Controls",
    "招喚攻撃": "Summon Attack",
    "攻撃力": "Attack Power",
    "攻撃補助": "Attack Assist",
    "敗走フェーズ": "Retreat Phase",
    "敵の列攻撃": "Enemy Row Attack",
    "敵の情報": "Enemy Info",
    "敵の攻撃と能力": "Enemy Attacks & Abilities",
    "敵の複数攻撃": "Enemy Multi-Attack",
    "森、洞窟の探索の中断": "Abort Forest/Cave Search",
    "武装伝承": "Weapon Inheritance",
    "水上都市スクーレ": "Water City Sukure",
    "王都ヴァレイ": "Royal Capital Valey",
    "疲労度": "Fatigue",
    "石化攻撃": "Petrification Attack",
    "祈りの森": "Sacred Forest",
    "祝福の日": "Day of Blessing",
    "神官": "Cleric",
    "素早さ": "Speed",
    "編成": "Formation",
    "職種": "Classes",
    "街外れの森": "Forest Outskirts",
    "被攻撃率": "Targeting Rate",
    "複数攻撃": "Multi-Attack",
    "記録室": "Records Room",
    "調子": "Condition",
    "遠征": "Expeditions",
    "酒場“月の涙”": "Tavern \"Tears of the Moon\"",
    "鉱山の街バルクウェイ": "Mining Town Barakway",
    "間接攻撃": "Indirect Attack",
    "防御補助": "Defend Assist",
    "隠しコマンド": "Hidden Commands",
    "預言書": "Book of Prophecy",
    "騎士": "Knight",
    "騎士団本部": "Order Headquarters",
    "魔女": "Witch",
    "魔術師": "Wizard",
    "ＨＰ": "HP"
}

BODY_TRANSLATIONS = {
    "\x14(": "\x14(",
    "\x15": "\x15",
    "\x15\x0B": "\x15\x0B",
    "\x15\x0C": "\x15\x0C",
    "\x15\x0E": "\x15\x0E",
    "\x15\x0F": "\x15\x0F",
    "\x15\x10": "\x15\x10",
    "\x15\x11": "\x15\x11",
    "\x15\x12": "\x15\x12",
    
    "△ボタンで敗走を選んだ場合の段階です。敗走を選ぶと、後列にいる仲間が戦闘を離脱し、前列と中列の仲間は１列ずつ後退します。\n\nなお、敗走時の中列、後列へのダメージは、通常の攻撃力と同等のものになります。\n\nここで全滅したら\x14(":
    "This phase occurs when you select Retreat with the △ button. When you retreat, allies in the Back Row will withdraw from combat, and allies in the Front and Middle Rows will move back one row.\n\nNote that the damage received by the Middle and Back Rows during a retreat is equivalent to their normal Attack Power.\n\nIf your party is wiped out here... \x14(",

    "「アカガエルの池」では、データのセーブをしたり、山賊団を遠征に出したりできます。\n\n「アカガエルの池」には、\x14(":
    "At the \"Red Frog Pond\", you can save your game data or send the Bandit Gang on expeditions.\n\nAt the \"Red Frog Pond\", there is... \x14(",

    "「クロニクルモード」\nここで語られる物語は、不死者ブラッドと仲間達が生きた世界とはまた別の、それでいてそっくりな世界での物語。\n\n女神と名乗る女性は一体何者なのか？\n迫りくる災いの正体とは？\n\nすべての答えは、１００年間戦い抜いた先にあります。":
    "\"Chronicle Mode\"\nThe story told here takes place in a world different from, yet identical to, the one where the immortal Blood and his companions lived.\n\nWho is this woman who calls herself a goddess?\nWhat is the true nature of the approaching calamity?\n\nAll the answers lie at the end of surviving for 100 years.",

    "「クロニクルモード」は、「ヴィーナス＆ブレイブス」のエンディングを迎えないと遊ぶことはできませんが、隠しコマンドの入力により「ヴィーナス＆ブレイブス」を遊ばなくても「クロニクルモード」を遊ぶことができます。\n\n「ヴィーナス＆ブレイブス」のタイトル画面表示中に、Ｌ１ボタンとＲ１ボタンを押したまま、以下のコマンドを素早く入力してください。入力に成功すると、タイトル画面のメニュー「クロニクルモード」が加わります。\n\n\n\u3000\u3000（・）\u3000△ボタンを軽く押す\n\u3000\u3000（一）\u3000△ボタンを長めに押して離す\n\n\x11\n隠しコマンド\x10\n\x11\n（\u3000一・\u3000・一\u3000・・・\u3000・・一\u3000）\x10":
    "\"Chronicle Mode\" cannot be unlocked until you reach the ending of \"Venus & Braves\". However, you can play \"Chronicle Mode\" without playing \"Venus & Braves\" by entering a hidden command.\n\nWhile the \"Venus & Braves\" title screen is displayed, hold down the L1 and R1 buttons and quickly input the following command. If successful, \"Chronicle Mode\" will be added to the title screen menu.\n\n\n    (・) Press the △ button briefly\n    (一) Hold the △ button longer, then release\n\n\x11\nHidden Command\x10\n\x11\n(  一・  ・一  ・・・  ・・一  )\x10",

    "「クロニクルモード」は、「ヴィーナス＆ブレイブス」の舞台に良く似たパラレルワールドで、騎士団を１００年間育てていくゲームモードです。\n\n基本的なルールは、全て「ヴィーナス＆ブレイブス」本編と変わりませんが、このモードの主人公はブラッドと違い不死者ではありません。\n\n「クロニクルモード」で１００年間戦い抜くには、団長も自分の子に任務を引き継がせ、世代交代をして行かなくてはならないのです。":
    "\"Chronicle Mode\" is a game mode in which you raise your Order of Knights over a span of 100 years in a parallel world closely resembling the setting of \"Venus & Braves\".\n\nAlthough the basic rules are identical to the main game, the protagonist in this mode is not immortal like Blood.\n\nTo survive the 100-year battle in \"Chronicle Mode\", the leader must pass on the mantle to their own child, ensuring a succession of generations.",

    "「世界地図」では、スクーレの周辺を見渡せる地図を見ることができます。\n\n地図の上には、出現中の魔物や、噂になっている街などが表示されており、一目で現在の状況がわかるようになっています。\n魔物にカーソルを合わせると、出来事を示すウィンドウが表示され、○ボタンを押すとその詳細を見ることができます。\n\n△ボタンのメニューから「索敵モード」を選ぶと、索敵モードに入ります。\n索敵モード中は魔物アイコンが点滅し、その場所の壊滅が近くなるにしたがってアイコンの点滅が速くなっていきます。\n\n\n\x15\x04":
    "In the \"World Map\", you can view a map of the area around Sukure.\n\nActive monsters, rumored towns, and other information are displayed on the map, allowing you to assess the current situation at a glance.\nHovering the cursor over a monster displays an event window, and pressing the ○ button shows its details.\n\nSelect \"Search Mode\" from the △ button menu to enter Search Mode.\nDuring Search Mode, monster icons flash; the closer a location is to destruction, the faster the icon flashes.\n\n\n\x15\x04",

    "「世界地図」では、バルクウェイ周辺を見渡せる地図を見ることができます。\n\n地図の上には、出現中の魔物や、噂になっている街などが表示されており、一目で現在の状況がわかるようになっています。\n魔物にカーソルを合わせると、出来事を示すウィンドウが表示され、○ボタンを押すとその詳細を見ることができます。\n\n△ボタンのメニューから、「索敵モード」を選ぶと、索敵モードに入ります。\n索敵モード中は魔物アイコンが点滅し、その場所の壊滅が近くなるにしたがってアイコンの点滅が速くなっていきます。\n\n\x15\x04":
    "In the \"World Map\", you can view a map of the area around Barakway.\n\nActive monsters, rumored towns, and other information are displayed on the map, allowing you to assess the current situation at a glance.\nHovering the cursor over a monster displays an event window, and pressing the ○ button shows its details.\n\nSelect \"Search Mode\" from the △ button menu to enter Search Mode.\nDuring Search Mode, monster icons flash; the closer a location is to destruction, the faster the icon flashes.\n\n\x15\x04",

    "「世界地図」では、大陸全土を見渡せる地図を見ることができます。\n\n地図の上には、出現中の魔物や、噂になっている街などが表示されており、一目で現在の状況がわかるようになっています。\n魔物にカーソルを合わせると、出来事を示すウィンドウが表示され、○ボタンを押すとその詳細を見ることができます。\n\n△ボタンのメニューから「索敵モード」を選ぶと、索敵モードに入ります。\n索敵モード中は魔物アイコンが点滅し、その場所の壊滅が近くなるにしたがってアイコンの点滅が速くなっていきます。\n\n\n\x15\x04":
    "In the \"World Map\", you can view a map of the entire continent.\n\nActive monsters, rumored towns, and other information are displayed on the map, allowing you to assess the current situation at a glance.\nHovering the cursor over a monster displays an event window, and pressing the ○ button shows its details.\n\nSelect \"Search Mode\" from the △ button menu to enter Search Mode.\nDuring Search Mode, monster icons flash; the closer a location is to destruction, the faster the icon flashes.\n\n\n\x15\x04",

    "「世界地図」では、大陸全土を見渡せる地図を見ることができます。\n\n地図の上には、出現中の魔物や、噂になっている街などが表示されており、一目で現在の状況がわかるようになっています。\n魔物にカーソルを合わせると、出来事を示すウィンドウが表示され、○ボタンを押すとその詳細を見ることができます。\n\n△ボタンのメニューから「索敵モード」を選ぶと、索敵モードに入ります。\n索敵モード中は魔物アイコンが点滅し、その場所の壊滅が近くなるにしたがってアイコンの点滅が速くなっていきます。\n\n\x15\x04":
    "In the \"World Map\", you can view a map of the entire continent.\n\nActive monsters, rumored towns, and other information are displayed on the map, allowing you to assess the current situation at a glance.\nHovering the cursor over a monster displays an event window, and pressing the ○ button shows its details.\n\nSelect \"Search Mode\" from the △ button menu to enter Search Mode.\nDuring Search Mode, monster icons flash; the closer a location is to destruction, the faster the icon flashes.\n\n\x15\x04",

    "「祈りの森」では、データのセーブをしたり、騎士団を遠征に出したりできます。\n\n「祈りの森」には、\x14(":
    "In the \"Sacred Forest\", you can save your game data or send the Order on expeditions.\n\nIn the \"Sacred Forest\", there is... \x14(",

    "「祝福の日」とは、その年の１日目のことを指します。この日には、１年の区切りとして色々な変化が起こります。\n\nまず、騎士団の仲間たちが１つずつ歳を取り、仲間の成長と衰退の一覧が表示されます。\n\n次に、女神により前年の騎士団の功績を評価されます。\nフィールドマップに残っている魔物の数と、そのレベルに応じて精霊のはかりの\x14(":
    "The \"Day of Blessing\" refers to the first day of the year. On this day, various changes occur marking the division of the year.\n\nFirst, the members of your Order age by one year, and a list displaying their growth and decline is shown.\n\nNext, the goddess evaluates your Order's achievements from the previous year.\nDepending on the number of monsters remaining on the field map and their levels, the scales of spirits... \x14(",

    "「祝福の日」とは、その年の１日目のことを指します。この日には、１年の区切りとして色々な変化が起こります。\n\nまず、騎士団の仲間たちが１つずつ歳を取り、仲間の成長と衰退の一覧が表示されます。\n\n次に、女神アリアにより前年の騎士団の功績を評価されます。\nフィールドマップに残っている魔物の数と、そのレベルに応じて精霊のはかりの\x14(":
    "The \"Day of Blessing\" refers to the first day of the year. On this day, various changes occur marking the division of the year.\n\nFirst, the members of your Order age by one year, and a list displaying their growth and decline is shown.\n\nNext, the goddess Aria evaluates your Order's achievements from the previous year.\nDepending on the number of monsters remaining on the field map and their levels, the scales of spirits... \x14(",

    "「街外れの森」では、データのセーブをしたり、騎士団を遠征に出したりできます。\n\n「街外れの森」には、\x14(":
    "In the \"Forest Outskirts\", you can save your game data or send the Order on expeditions.\n\nIn the \"Forest Outskirts\", there is... \x14(",

    "ここでは、現在騎士団にいる仲間の\x14(":
    "Here, the members currently in your Order... \x14(",

    "ここでは、騎士団の戦歴や年譜、歴史、団員記録を見ることができます。\n\n「戦歴」では、騎士団が今までに倒した敵の数や、獲得した予測安全値の累計などを見ることができます。\n\n「年譜」では、騎士団での出来事や記録などが年表風に記録されてゆきます。\n\n「歴史」では、\x14(":
    "Here, you can view the Order's battle history, chronicles, history, and member records.\n\n\"Battle History\" displays information such as the number of enemies defeated by the Order so far and the accumulated forecast safety values.\n\n\"Chronicles\" records the events and milestones of the Order in a chronological timeline format.\n\n\"History\" shows... \x14(",

    "このゲームは大きく分けて、\n\n\x14(":
    "This game is broadly divided into...\n\n\x14(",

    "この世界では、\x14(":
    "In this world... \x14(",

    "これまでのゲームのデータをセーブしたい時には、\x14(":
    "When you want to save your progress... \x14(",

    "これまでのゲームの内容をセーブするには、情報屋に会った時に話しかけて「冒険を記録する」を選択してください。セーブデータは全部で５つまで持つことができます。":
    "To save your progress, speak to the Info Broker when you meet them and select \"Record Adventure\". You can hold up to 5 save files in total.",

    "アイテムを装備した仲間が戦闘に参加すると、装備しているアイテムに経験値が蓄積されていきます。\n\n経験値の蓄積が一定の値を越えると、そのアイテムはレベルが上がり、より高い能力を持つアイテムに変化します。\n\nアイテムを装備者から外すと、蓄積されていた経験値が失われてしまいますが、\n武器のレベルは装備者から外しても下がることはありません。\n\nなお、アイテムは成長の限界へ達すると、次のレベルアップ時に壊れてしまうことがあります。":
    "When an ally equipped with an item participates in battle, experience points accumulate for that item.\n\nOnce the accumulated experience points exceed a certain value, the item's level increases, transforming it into an item with higher attributes.\n\nRemoving an item from the user loses the accumulated experience points. However, a weapon's level will not decrease even if unequipped.\n\nAdditionally, once an item reaches its growth limit, it may break upon the next level up.",

    "アクラル大陸を治める王が住む、大陸の中心に位置する都。\n\nブラッドたち騎士団の活動の舞台は、この王都を中心に世界へと広がって行きます。\n\nヴァレイの中の移動は、□ボタンで街の地図を開いて行います。\n\n\x15\x04\x03":
    "The capital city located at the center of the continent, home to the King who rules Acral.\n\nThe stage for Blood and his Order's activities will expand from this capital city out into the world.\n\nMovement within Valey is done by opening the town map with the □ button.\n\n\x15\x04\x03",

    "アクラル大陸を治める王が住む、大陸の中心に位置する都。\n\n騎士団の活動の舞台は、この王都を中心に行われます。\n\nヴァレイの中の移動は、□ボタンで街の地図を開いて行います。\n\n\x15\x04\x03":
    "The capital city located at the center of the continent, home to the King who rules Acral.\n\nThe activities of the Order are centered around this capital city.\n\nMovement within Valey is done by opening the town map with the □ button.\n\n\x15\x04\x03",

    "オプションでは、以下の項目を設定することができます。\n\n\x15\x02\x03":
    "In Options, you can configure the following settings:\n\n\x15\x02\x03",

    "ゲームに慣れてきたら…\n\n\n\x15\x03\x03":
    "Once you get used to the game...\n\n\n\x15\x03\x03",

    "フェーズとは、戦闘の各段階のことを指します。戦闘は、次の６つのフェーズで構成されています。\n\n\u3000\x14(":
    "Phases refer to each stage of combat. Combat is composed of the following 6 phases:\n\n  \x14(",

    "フェーズとは、戦闘の各段階のことを指します。戦闘は、次の７つのフェーズで構成されています。\n\n\u3000\x14(":
    "Phases refer to each stage of combat. Combat is composed of the following 7 phases:\n\n  \x14(",

    "メニューから「編成」を選ぶと編成画面に行きます。ここでは、戦闘時にどの仲間を使ってどのように戦うかを決定する、最も重要な編成の作業を行います。\n\n編成画面では、実際に戦闘させる７人を画面左側の４×３列の枠内に配置します。この枠は画面の下から順に前列・中列・後列となっています。\n\n前列の仲間の前に出る％は、各位置の被攻撃率です。戦闘では、基本的に中央部の方が外側よりも攻撃を受ける確率が高くなります。\n\nまた、画面右側にはカーソルを合わせた仲間の個人情報が表示されます。\n\n戦闘は、ここで配置した７人をそのままローテーションさせて戦うので、列を空けて編成すると、前列に誰もいなくなった時に中列に敵の攻撃が直撃し、倍のダメージを受けてしまいます。後列を直撃した場合も同様です。ローテーション後のことを考慮して編成しましょう。\nＲ１ボタンを利用すると、実際にローテーション後の陣形を確認することができます。\n\n\n\x15\x04\x03":
    "Selecting \"Formation\" from the menu takes you to the formation screen. Here, you perform the most important task of deciding which allies to use and how to arrange them in battle.\n\nOn the formation screen, place the 7 allies who will actually fight into the 4x3 grid on the left side of the screen. From the bottom of the grid up, the rows are Front, Middle, and Back.\n\nThe percentage in front of Front Row allies is their targeting rate. In battle, units in the center are generally more likely to be attacked than those on the sides.\n\nAdditionally, individual information of the ally under the cursor is displayed on the right side of the screen.\n\nSince combat rotates the 7 placed units as they are, leaving a row empty will cause enemy attacks to strike the Middle Row directly if the Front Row becomes empty, dealing double damage. The same applies if the Back Row is struck directly. Plan your formation while considering the layout after rotation.\nPressing the R1 button allows you to verify the actual formation after rotation.\n\n\n\x15\x04\x03",

    "リファレンスでは、このゲームに関するルールや操作、用語などが説明されています。\n方向キーの上下でメニューをスクロールさせて知りたい項目を選び、○ボタンを押すとその項目へ行きます。\n文章中にある赤い文字の言葉は、その項目へのリンクを表わしています。方向キーか左スティックの左右で選択し、色が変わってから○ボタンを押すと、その言葉の説明へ行きます。\n\n例えば、\x14(":
    "In the Reference manual, rules, controls, and terminology regarding this game are explained.\nScroll the menu up and down with the Directional buttons to choose the item you wish to know about, and press the ○ button to proceed to that item.\nWords highlighted in red within the text represent links to those items. Select them with the Left/Right Directional buttons or Left Stick, and press the ○ button once the color changes to go to the explanation of that term.\n\nFor example, \x14(",

    "リファレンスでは、このゲームに関するルールや操作、用語などが説明されています。\n方向キーまたは左スティックの上下でメニュ\nーをスクロールさせて知りたい項目を選び、○ボタンで決定、×ボタンでキャンセルできます。\n\n文章中にある赤い文字の言葉は、その項目へのリンクを表わしています。\n方向キーまたは左スティックの左右で選択し、色が変わってから○ボタンを押すと、その言葉の説明へ行きます。そこからは×ボタンで元の画面に戻って来ることができます。\n\nリファレンス画面を抜けたい時には、目次で△ボタン押してメニューを開き「戻る」を選ぶか、×ボタンを押してください。\n\n\n\x15\x02":
    "In the Reference manual, rules, controls, and terminology regarding this game are explained.\nScroll the menu up and down with the Directional buttons or Left Stick to choose the item you wish to know about, then confirm with the ○ button or cancel with the × button.\n\nWords highlighted in red within the text represent links to those items.\nSelect them with the Left/Right Directional buttons or Left Stick, and press the ○ button once the color changes to go to the explanation of that term. From there, you can return to the previous screen with the × button.\n\nTo exit the Reference screen, press the △ button at the table of contents to open the menu and select \"Back\", or press the × button.\n\n\n\x15\x02",

    "一度に複数回連続の攻撃を仕掛けてくる攻撃方法です。\x14(":
    "An attack method that unleashes multiple consecutive attacks at once. \x14(",

    "世界記録とは、メモリーカード(PS2)内で共有されている記録データのランキングです。\n\x11\n\x15":
    "World Records are the rankings of record data shared within the Memory Card (PS2).\n\x11\n\x15",

    "中列からでも敵を攻撃できる能力を間接攻撃と呼びます。\x14(":
    "The ability to attack enemies even from the Middle Row is called Indirect Attack. \x14(",

    "中列に攻撃補助の力を持つ仲間を配すると、直前の仲間の攻撃力を補って高めることができます。ただし、この能力は１回の\x14(":
    "Placing an ally with Attack Assist in the Middle Row will support and increase the Attack Power of the ally directly in front of them. However, this ability can only be used once per... \x14(",

    "中列に防御補助の力を持つ職種の仲間を配すると、直前の仲間が攻撃を受けた時に、そのダメージを軽減してくれます。ただし、この能力は、１回の\x14(":
    "Placing an ally with Defend Assist in the Middle Row will mitigate damage when the ally directly in front of them is attacked. However, this ability can only be used once per... \x14(",

    "予測安全値とは、精霊のはかりにあらわれる“未来の安全度”を示すものです。\n\n敵を倒して\x14(":
    "The Forecast Safety Value represents the \"future safety level\" shown on the scales of spirits.\n\nBy defeating enemies... \x14(",

    "仲間たちがまれに発揮する、通常よりも強力な攻撃のことです。通常の１．５～２倍の力の攻撃力を発揮できますが、発動するタイミングは予測できません。":
    "This is a more powerful attack than normal that allies occasionally unleash. It can deal 1.5 to 2 times the normal damage, but the timing of its activation cannot be predicted.",

    "仲間たちの職種は１７種類あり、どの職種に属するかによって、基本的にどのような能力を備えているのかが決まります。それぞれの特性を把握し、それを考慮して、十分に能力を活かせる編成をしましょう。\n\n\x11\n\x13\x1A職種一覧\x13\x16\x10\n\n\n\x14(":
    "There are 17 classes for your allies, and which class they belong to basically determines what kind of abilities they possess. Grasp the characteristics of each class and arrange your formation to make full use of their capabilities.\n\n\x11\n\x13\x1AClass List\x13\x16\x10\n\n\n\x14(",

    "仲間の入れ替えや寿命による引退によって騎士団から退団者が出たとき、その退団者が\x14(":
    "When members leave the Order due to swaps or retirement from old age, if the leaving member... \x14(",

    "体力を表わす数値です。攻撃を受けることにより減少します。ＨＰがゼロになった仲間は死亡の状態になり、戦闘から離脱してしまいます。":
    "A value representing physical health. It decreases upon receiving attacks. An ally whose HP drops to zero will enter a state of death and withdraw from battle.",

    "体力を表わす数値です。攻撃を受けることにより減少します。ＨＰがゼロになった仲間は負傷や死亡の状態になり、戦闘から離脱してしまいます。":
    "A value representing physical health. It decreases upon receiving attacks. An ally whose HP drops to zero will enter a state of injury or death and withdraw from battle.",

    "前列にいる仲間全員に対して、同時にダメージを与える攻撃です。前列に誰もいないと、その時点で最前列にいる者全員が倍のダメージを受けることになってしまいます。戦闘前に\x14(":
    "An attack that inflicts damage on all allies in the Front Row simultaneously. If no one is in the Front Row, everyone currently in the foremost row will take double damage. Before battle... \x14(",

    "友情が深まり、\x14(":
    "Friendship deepens... \x14(",

    "同性同士の仲がある程度深まると、友情関係となり、遠征からの帰還時に二人の会話を見られることがあります。\n\nまた、まれに友情をさらに深めようと悩んでいる仲間を見かけることがあります。\n\nそんな時、画面に選択肢が出たら、友情を深められると思う選択肢を選んであげましょう。\n選択によってはその仲間の友情が深まるかもしれません。\n\x11\n\x15'\x03":
    "When relationships between members of the same sex deepen to a certain degree, they form a friendship, and you may see conversations between them upon returning from expeditions.\n\nAdditionally, you may occasionally see allies who are struggling with how to further deepen their friendship.\n\nAt such times, if options appear on the screen, select the option you think will help deepen their friendship.\nDepending on your choice, their friendship may grow closer.\n\x11\n\x15'\x03",

    "同性同士の仲が非常に深まり、親友と呼べる仲になると、遠征からの帰還時にその二人の友情を称えて精霊が力を授けてくれます。\nこの力を授けられる出来事を、精霊招喚と呼びます。\n精霊招喚を起こした二人の仲間を戦闘に参加させると、強力な\x14\uf8f3":
    "When relationships between members of the same sex deepen significantly to the point of being called best friends, the spirits will bestow power to honor their friendship upon returning from an expedition.\nThis event of bestowing power is called a Spirit Summon.\nIf you include the two allies who triggered a Spirit Summon in battle, a powerful... \x14\uf8f3",

    "大陸南部、バルク山にある鉱山集落。\n\nゴーレム山賊団はこの街を根城に生活をし、日々の活動をしています。\n\nバルクウェイの中の移動は、□ボタンで街の地図を開いて行います。\n\n\x15\x04\x03":
    "A mining settlement located on Mount Barak in the southern part of the continent.\n\nThe Golem Bandits reside and carry out their daily activities using this town as their base.\n\nMovement within Barakway is done by opening the town map with the □ button.\n\n\x15\x04\x03",

    "女神アリアから、予言についての話を聞くことができます。\n\nその時に騎士団がするべきことを教えてくれるので、やるべきことを忘れてしまったら話を聞いてみるといいでしょう。":
    "You can listen to the goddess Aria talk about the prophecies.\n\nShe will tell you what the Order should do at that time, so if you forget what you are supposed to do, it is a good idea to speak with her.",

    "女神アリアから、次の予言についての話を聞くことができます。\n\nその時に騎士団がするべきことを教えてくれるので、やるべきことを忘れてしまったら話を聞いてみるといいでしょう。":
    "You can listen to the goddess Aria talk about the next prophecy.\n\nShe will tell you what the Order should do at that time, so if you forget what you are supposed to do, it is a good idea to speak with her.",

    "強さには、個人の強さと騎士団の強さがあります。いずれも戦闘における強さを示した数値です。\n\n個人の強さは、\x14(":
    "Strength is divided into individual strength and Order strength. Both represent numerical values indicating prowess in combat.\n\nIndividual strength... \x14(",

    "戦闘で、後列に来た時に\x14(":
    "During battle, when moving to the Back Row... \x14(",

    "戦闘では、中央部の方が外側よりも攻撃を受ける確率が高くなります。編成画面で前列の仲間の前に出る％が、各位置の被攻撃率になります。":
    "In battle, units in the center are more likely to receive attacks than those on the sides. The percentage displayed in front of the Front Row allies on the formation screen represents the targeting rate for each position.",

    "戦闘の際、仲間たちは\x14(":
    "In battle, allies... \x14(",

    "戦闘の際、仲間たちは職種や年齢に応じた攻撃力を発揮します。基本的に、攻撃は前列のみが行います。攻撃が有効になった場合、この攻撃力の値と同じ値のダメージが敵に与えられ、敵の\x14(":
    "In battle, allies exhibit Attack Power based on their class and age. Basically, only the Front Row attacks. If an attack succeeds, damage equivalent to this Attack Power value is inflicted on the enemy, and the enemy's... \x14(",

    "戦闘は、\x14(":
    "Combat... \x14(",

    "戦闘は、４×３列の枠に配置した７人を、図のようにローテーションさせることによって行います。\n\x15\x02":
    "Combat is conducted by rotating the 7 placed units within the 4x3 grid as shown in the diagram.\n\x15\x02",

    "戦闘中、後列で受けた\x14(":
    "During battle, healing received in the Back Row... \x14(",

    "戦闘中、後列に来たときに\x14(":
    "During battle, when moving to the Back Row... \x14(",

    "戦闘中に\x14(":
    "During battle... \x14(",

    "攻撃の素早さを表わす数値です。戦闘では、敵・味方を問わず、この値が高い者から順に攻撃を始めます。":
    "A value representing combat speed. In battle, actions commence in descending order of this value, regardless of whether the unit is an ally or an enemy.",

    "攻撃補助の能力を持った仲間を中列に配すると、その直前にいる前列の仲間の攻撃力を補って高めてくれます。ただし、この能力は１回のローテーションにつき１回しか発揮できません。例えば、ローテーションせずに続けて中列に留まった場合、２回目以降の攻撃にはこの能力は発揮されません。\n\x15\x05":
    "Placing an ally with Attack Assist in the Middle Row will support and increase the Attack Power of the Front Row ally directly in front of them. However, this ability can only be unleashed once per rotation. For example, if they remain in the Middle Row without rotating, this ability will not be triggered for subsequent attacks.\n\x15\x05",

    "敵の情報を得ると、メニューに「敵の情報」が追加されます。ここでは、敵の種類や能力、攻撃の特徴などを知ることができます。方向キーまたは左スティックの左右で「能力」「攻撃パターン」「特徴」を見ることができるので、戦闘前に確認しておきましょう。":
    "Once you obtain information on an enemy, \"Enemy Info\" will be added to the menu. Here, you can learn about the enemy's type, abilities, and attack characteristics. You can check their \"Abilities,\" \"Attack Patterns,\" and \"Features\" using the Left/Right Directional buttons or Left Stick, so be sure to check them before battle.",

    "敵は、普段は\x14(":
    "Enemies normally... \x14(",

    "旅をしていると、情報屋に会うことがあります。情報屋は、これまでのゲームの内容を\x14(":
    "As you travel, you may meet the Info Broker. The Info Broker... \x14(",

    "森や洞窟などに入る前には、メニューに「ルールの確認」という項目が追加されます。\nここには、戦い方、ゲームオーバー条件など、その場所特有のルールが書かれています。足を踏み入れる前に必ず確認しておきましょう。":
    "Before entering forests or caves, a \"Confirm Rules\" option is added to the menu.\nHere, rules unique to that location, such as combat conditions and game-over criteria, are documented. Be sure to check them before stepping in.",

    "森や洞窟の中でSTARTボタンを押すと、入口に戻ることができます。中断して\x14(":
    "Pressing the START button inside a forest or cave allows you to return to the entrance. Aborting and... \x14(",

    "異性同士の仲が非常に深まると、遠征から帰還した時にその二人が結婚をすることがあります。\n結婚をすると、妻となった仲間が\x14(":
    "When relationships between members of opposite sexes deepen significantly, they may get married upon returning from an expedition.\nWhen married, the wife... \x14(",

    "異性同士の仲間がある程度親密になると、恋愛関係となり、遠征から帰還した時に二人でデートをしているところを見られることがあります。\n\nまた、まれに一人の仲間が恋の悩みを抱えて、何をすべきか考えこんでいることがあります。\nそんな時、画面に選択肢が出たら仲間のためになる行動を選択してあげましょう。\n\n選択によってはその仲間の恋が進展するかもしれません。\n\n\x11\n\x15$\x03":
    "When members of opposite sexes become close to a certain degree, they enter a romantic relationship, and you may see them on dates upon returning from expeditions.\n\nAdditionally, you may occasionally see an ally struggling with romance, lost in thought about what to do.\nAt such times, if options appear on the screen, select the action that benefits your ally.\n\nDepending on your choice, their romance may progress.\n\n\x11\n\x15$\x03",

    "異性同士の仲間の仲がより深まると、遠征から帰還した時にプロポーズをしているところを見られることがあります。\nプロポーズをした仲間とその相手は、その後結婚をする可能性が高くなります。\n\x11\n\x15%\x03":
    "When relationships between members of opposite sexes deepen further, you may witness a proposal upon returning from an expedition.\nThe proposing ally and their partner will have a high chance of marrying after that.\n\x11\n\x15%\x03",

    "疲労度とは、１回の旅の中で受けたダメージを全て合計した数値のことです。疲労度は、±０を中心としたプラスとマイナスの数値で表わされます。疲労度によって\x14(":
    "Fatigue represents the total sum of damage received during a single trip. Fatigue is represented by positive and negative values centered around ±0. Depending on Fatigue... \x14(",

    "登場する仲間には、レベルが設定されています。最初に入団したキャラクターはレベルが無い状態ですが、敵を倒すことでレベルが上昇して行きます。\n\nレベルは最大５まで上昇し、戦闘においてとどめを刺すことにより段階が１つ上がります。段階が上がると、\x14(":
    "Allies have levels. Characters who initially join have no level, but their level increases as they defeat enemies.\n\nThe level rises to a maximum of 5, increasing by one tier when they land the finishing blow in battle. When a tier rises... \x14(",

    "登場する仲間や敵の中には、属性を持つものがいます。属性は「風・火・土・水」の４種類で、「無」は属性がないことを表わしています。\n\n戦闘において、敵・味方の双方に属性があり、その組み合わせに強弱関係が成り立つ場合、攻撃力が影響を受けることがあります。\n属性同士の強弱関係を以下に示します。\n\n\x15":
    "Some allies and enemies possess elemental attributes. The four attributes are \"Wind, Fire, Earth, and Water,\" while \"None\" indicates no attribute.\n\nIn battle, if both the enemy and ally have attributes and their combination establishes a strengths/weaknesses relationship, Attack Power may be affected.\nThe relationship between attributes is shown below.\n\n\x15",

    "登場する仲間や敵の中には、属性を持つものがいます。属性は「風・火・土・水」の４種類で、「無」は属性がないことを表わしています。\n\n戦闘において、敵・味方の双方に属性があり、その組み合わせに強弱関係が成り立つ場合、攻撃力が影響を受けることがあります。\n属性同士の強弱関係を以下に示します。\n\n\x15\x1E":
    "Some allies and enemies possess elemental attributes. The four attributes are \"Wind, Fire, Earth, and Water,\" while \"None\" indicates no attribute.\n\nIn battle, if both the enemy and ally have attributes and their combination establishes a strengths/weaknesses relationship, Attack Power may be affected.\nThe relationship between attributes is shown below.\n\n\x15\x1E",

    "登場人物たちの各能力を数値化したものを、パラメータと言います。編成画面では、カーソルを合わせた仲間のパラメータが画面右側に表示されます。また、編成や募集の時などに見られる「仲間の詳細」でも、現在のパラメータを見ることができます。\n\n各パラメータの数値は\x14(":
    "Numerical values representing the various capabilities of characters are called parameters. On the formation screen, the parameters of the ally under the cursor are displayed on the right side of the screen. You can also view the current parameters in the \"Ally Details\" seen during formations or recruitment.\n\nThe value of each parameter... \x14(",

    "登場人物たちは、主人公が騎士、バルは戦士という風にそれぞれの職種に属しています。職種とは、そのルーツや社会的役割などを同じくする人々や集団のことを分類した名称のことです。\n彼らは、長年に渡る集団生活の中で独自の習慣や特殊な技術を発展させてきました。戦闘においても職種ごとに特徴が反映され、それぞれに異なった傾向の能力を示します。\x11\n\x15\x01\x03":
    "Characters belong to their respective classes, such as the protagonist being a Knight and Bal being a Warrior. A class is a name categorizing groups of people sharing the same roots or social roles.\nThrough years of communal living, they have developed unique customs and specialized skills. In battle, characteristics are reflected for each class, exhibiting different tendencies in their capabilities. \x11\n\x15\x01\x03",

    "自分の\x14(":
    "My... \x14(",

    "通常の基本操作は次の通りです。\n\n\u3000○ボタン‥‥‥決定\n\u3000△ボタン‥‥‥メニューを開く／閉じる\n\u3000□ボタン‥‥‥詳細を見る\n\u3000×ボタン‥‥‥キャンセル\n\u3000方向キー‥‥‥山賊団／カーソルの移動\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000（左スティックでも操作可）\n\u3000SELECTボタン‥‥‥\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000過去のメッセージを表示\n\n\x11\n\x15":
    "Basic controls are as follows:\n\n  ○ button: Confirm\n  △ button: Open/close menu\n  □ button: View details\n  × button: Cancel\n  Directional buttons: Move Bandits/cursor\n  (Can also be operated with the Left Stick)\n  SELECT button:\n  Display message log\n\n\x11\n\x15",

    "通常の基本操作は次の通りです。\n\n\u3000○ボタン‥‥‥決定\n\u3000△ボタン‥‥‥メニューを開く／閉じる\n\u3000□ボタン‥‥‥詳細を見る\n\u3000×ボタン‥‥‥キャンセル\n\u3000方向キー‥‥‥騎士団／カーソルの移動\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000（左スティックでも操作可）\n\u3000SELECTボタン‥‥‥\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000過去のメッセージを表示\n\n\x11\n\x15":
    "Basic controls are as follows:\n\n  ○ button: Confirm\n  △ button: Open/close menu\n  □ button: View details\n  × button: Cancel\n  Directional buttons: Move Order/cursor\n  (Can also be operated with the Left Stick)\n  SELECT button:\n  Display message log\n\n\x11\n\x15",

    "通常時の主な基本操作は次の通りです。\n\n○ボタン‥‥‥決定、アクション、会話の操作\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000（話し掛ける、セリフ送り、\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000セリフ一括表示、会話の終了）\n△ボタン‥‥‥メニューの表示／キャンセル\n×ボタン‥‥‥キャンセル\n方向キー‥‥‥カーソル／人物の移動\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000（左スティックでも操作可）\nSELECTボタン‥‥‥ヘルプモード\nＲ１／Ｒ２ボタン‥‥‥(ヘルプモードで)\n\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000\u3000カーソルの倍速移動":
    "Main basic controls during normal gameplay are as follows:\n\n○ button: Confirm, action, conversation controls\n          (Talk, advance text, display all text,\n           end conversation)\n△ button: Display menu / cancel\n× button: Cancel\nDirectional buttons: Move cursor / character\n                    (Can also be operated with the Left Stick)\nSELECT button: Help Mode\nR1/R2 buttons: (In Help Mode)\n              Move cursor at double speed",

    "遠征中、画面の右下に騎士団や街等の位置を示すレーダーが表示されます。\n\nレーダーに表示されるのは場所の位置情報だけでなく、その場所がどんな状態にあるのかも表されます。\n光点の状態をこまめに確認して遠征に役立ててください。\n\nなお、□ボタンを押すことでレーダーの表示範囲を切り替えることができます。\n\nレーダーに表示される光点の種類と意味は、以下のとおりです。\n\n\x15\x02\x03":
    "During expeditions, a radar indicating the positions of the Order, towns, etc. is displayed at the bottom right of the screen.\n\nThe radar displays not only geographic location info but also what state those locations are in.\nCheck the state of the blips frequently to aid in your expeditions.\n\nAdditionally, pressing the □ button toggles the display range of the radar.\n\nThe types and meanings of the blips displayed on the radar are as follows:\n\n\x15\x02\x03",

    "酒場“月の涙”で「噂を聞く」を選択すると、スクーレ周辺で広まっている様々な噂を聞くことができます。\n\n噂の場所に行くと、そこで仕事を依頼されたり、色々な情報を聞くことができます。\n\nただし、仕事の依頼や情報は、最大５件までしかストックすることができません。\n\n５件を越えて新しく仕事を受けたり情報を聞く場合、ストックしている仕事、情報と入れ替えることになります。\n\nまた、噂や仕事の依頼、情報は一度聞いたり引き受けたりしてから日数が経ちすぎると、出来事が忘れ去られたり他の誰かに解決されて消滅してしまうので注意してください。\n\n噂に聞いた場所にはフィールドマップに青い旗が、仕事を引き受けた場所には赤い旗が立ち、レーダー上で点滅します。\n\n\n\x15\x04\x03":
    "Selecting \"Hear Rumors\" at the Tavern \"Tears of the Moon\" allows you to hear various rumors spreading around Sukure.\n\nGoing to the rumored location allows you to be requested for jobs or hear various information.\n\nHowever, job requests and information can only be stocked up to a maximum of 5 entries.\n\nIf you receive a new job or hear info exceeding 5 entries, you will replace it with the stocked jobs/information.\n\nAdditionally, please note that if too many days pass after hearing a rumor or accepting a job request, the event may be forgotten or resolved by someone else and disappear.\n\nLocations heard in rumors will have a blue flag on the field map, and accepted job locations will have a red flag, flashing on the radar.\n\n\n\x15\x04\x03",

    "酒場で「噂を聞く」を選択すると、大陸全土で広まっている様々な噂を聞くことができます。\n\n噂の場所に行くと、そこで仕事を依頼されたり、色々な情報を聞くことができます。\n\nただし、仕事の依頼や情報は、馬車や妖精の道の情報を除いて最大５件までしかストックすることができません。\n\n５件を越えて新しく仕事を受けたり情報を聞く場合、ストックしている仕事、情報と入れ替えることになります。\n\nまた、噂や仕事の依頼、情報は一度聞いたり引き受けたりしてから日数が経ちすぎると、出来事が忘れ去られたり他の誰かに解決されて消滅してしまうので注意してください。\n\n噂に聞いた場所にはフィールドマップに青い旗が、仕事を引き受けた場所には赤い旗が立ち、レーダー上で点滅します。\n\n\n\x15\x04\x03":
    "Selecting \"Hear Rumors\" at a Tavern allows you to hear various rumors spreading across the entire continent.\n\nGoing to the rumored location allows you to be requested for jobs or hear various information.\n\nHowever, job requests and information can only be stocked up to a maximum of 5 entries, excluding carriage and Fairy Road information.\n\nIf you receive a new job or hear info exceeding 5 entries, you will replace it with the stocked jobs/information.\n\nAdditionally, please note that if too many days pass after hearing a rumor or accepting a job request, the event may be forgotten or resolved by someone else and disappear.\n\nLocations heard in rumors will have a blue flag on the field map, and accepted job locations will have a red flag, flashing on the radar.\n\n\n\x15\x04\x03",

    "鉱山の街バルクウェイから北西に位置する水の都。\n\nブラッド率いる騎士団は、この街を拠点として活動を繰り広げます。\n\nスクーレの中の移動は、□ボタンで街の地図を開いて行います。\n\n\x15\x04\x03":
    "The Water City located north-west of the Mining Town Barakway.\n\nThe Order led by Blood uses this city as their base to carry out their activities.\n\nMovement within Sukure is done by opening the town map with the □ button.\n\n\x15\x04\x03",

    "防御補助の能力を持った仲間を中列に配すると、その直前にいる前列の仲間が受けたダメージを軽減してくれます。ただし、この能力は１回のローテーションごとに１回しか使えません。例えば、ローテーションせずに続けて中列に留まった場合、一度この力を使ってしまうと、それ以降の攻撃は防ぐことができません。\n\n\x15\x06":
    "Placing an ally with Defend Assist in the Middle Row will mitigate the damage received by the Front Row ally directly in front of them. However, this ability can only be used once per rotation. For example, if they remain in the Middle Row without rotating, once they use this power, they cannot defend against subsequent attacks.\n\n\x15\x06",

    "騎士団の仲間は、武器を装備することができ、これをアイテムと呼びます。\n\nアイテムを装備すると、攻撃力などの\x14(":
    "Members of the Order can equip weapons, which are referred to as items.\n\nEquipping an item increases stats such as Attack Power... \x14(",

    "騎士団の仲間達は、それぞれが自分の周りの仲間と人間関係を持っています。\n\n仲間同士の仲が深まると、恋をしたり、友情が芽生えたりと様々な出来事が起き、\nさらに関係が深まれば、\x14(":
    "Members of the Order each maintain personal relationships with the companions around them.\n\nAs relationships between companions deepen, various events such as falling in love or sparking friendship occur. If the relationship deepens further... \x14(",

    "ＨＰとは、仲間の持つ体力を表わす数値のことで、攻撃を受けることにより減少します。ＨＰがゼロになると負傷の状態になり、仲間の中から１人でも負傷者が出た場合、その戦闘は負けとなります。戦闘中、後列に\x14(":
    "HP represents the physical health of an ally and decreases upon receiving attacks. If HP drops to zero, they enter an injured state. If even a single ally is injured, the battle is lost. During battle, placing them in the Back Row... \x14("
}

def main():
    csv_path = "translation_catalog_split/Tutorial_Help_Combined.csv"
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

    # Columns: File, Block Index, Title (Original), Title (Translation), Body (Original), Body (Translation), Notes, Context
    title_translated = 0
    body_translated = 0
    missing_titles = set()
    missing_bodies = set()

    for row in rows:
        orig_title = row[2]
        orig_body = row[4]
        
        # Translate Title
        if orig_title:
            orig_title_py = csv_to_python(orig_title).strip()
            if orig_title_py in TITLE_TRANSLATIONS:
                row[3] = python_to_csv(TITLE_TRANSLATIONS[orig_title_py])
                title_translated += 1
            else:
                missing_titles.add(orig_title)
        else:
            row[3] = ""

        # Translate Body
        if orig_body:
            orig_body_py = csv_to_python(orig_body).strip()
            # Try to match direct clean string or complete string
            matched = False
            for k, v in BODY_TRANSLATIONS.items():
                if k.strip() == orig_body_py:
                    row[5] = python_to_csv(v)
                    body_translated += 1
                    matched = True
                    break
            if not matched:
                missing_bodies.add(orig_body)
        else:
            row[5] = ""

    if missing_titles:
        print(f"[-] Warning: {len(missing_titles)} titles missing translations:")
        for t in sorted(missing_titles):
            print(f"  * {repr(t)}")
            
    if missing_bodies:
        print(f"[-] Warning: {len(missing_bodies)} bodies missing translations:")
        for b in sorted(missing_bodies):
            print(f"  * {repr(b)}")

    if not missing_titles and not missing_bodies:
        print("[+] All Title and Body help entries successfully mapped!")

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote {title_translated} titles and {body_translated} bodies to {csv_path}.")

if __name__ == "__main__":
    main()
