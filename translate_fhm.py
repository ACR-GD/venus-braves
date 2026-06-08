#!/usr/bin/env python3
import os
import csv

TRANSLATIONS = {
    "戦闘前に、敵の情報を入手することができます。\nＨＰや、攻撃力をよく見て、戦い方の参考に\nしましょう。\n \n方向キー（左スティック）の左右で、\n敵の情報の内容を切り替えることができます。\n \nひととおり敵の情報を見終わったら、\n△ボタンでメニューを表示し\n編成画面にいってください。":
    "Before battle, you can view enemy information.\nCheck their HP and Attack Power carefully to\nhelp formulate your strategy.\n \nUse the Left/Right Directional buttons (or Left Stick)\nto cycle through the enemy details.\n \nOnce you have finished checking their information,\npress the △ button to open the menu and\nproceed to the Formation screen.",

    "編成画面では、仲間の陣形を変更することができます。\n画面下から、前列、中列、後列です。\n \n方向キー（左スティック）でカーソルを移動、\n○ボタンで、仲間を選択し、\nカーソルを移動させ、\nもう一度○ボタンを押すと、\nその場所に仲間を配置することができます。\n \n前列の仲間が傷ついても、\nローテーションして、中列、後列の仲間と\n入れ替わることができるように\n各列に仲間を配置するとよいでしょう。":
    "On the Formation screen, you can adjust your unit positions.\nFrom the bottom of the screen up, they are the Front, Middle, and Back rows.\n \nUse the Directional buttons (or Left Stick) to move the cursor.\nPress the ○ button to select a unit, move the cursor to\nyour desired position, and press ○ again to place them.\n \nPosition your units so that when Front Row members\nare injured, you can rotate them to swap with\nhealthy allies in the Middle and Back Rows.",

    "今度の魔物は、今までのものより、\n攻撃力が高めなので注意が必要です。\n \nＨＰが低めの仲間をどうやって守るかが、\n編成の鍵になるでしょう。":
    "The monsters this time have higher Attack Power\nthan previous ones, so caution is advised.\n \nHow you protect units with low HP will be the\nkey to your formation strategy.",

    "世界には、たくさんの%c80:0:0%『職種』%c%があり、\nそのなかでも%c80:0:0%『騎士』%c%という職種には\n『防御補助』という能力があります。\nこれは、前列にいる仲間へのダメージを、\n中列から防いでくれるというものです。\nＨＰが少ない仲間が前列に立ったとき、\nその仲間を守るために、非常に有効な手立てと\nいえるでしょう。\nただし、その能力は、ローテーションしてから\n1回しか使うことができないので、\n注意が必要です。":
    "There are many %c80:0:0%[Classes]%c% in the world, and\namong them, the %c80:0:0%[Knights]%c% possess an\nability called \"Defend Assist\".\nThis allows them to protect Front Row allies from damage\nwhile positioned in the Middle Row.\nWhen a low-HP ally moves to the Front Row, this is\nan extremely effective way to keep them safe.\nHowever, note that this ability can only be used\nonce per rotation.",

    "今度の敵はＨＰが多いので長期戦になるでしょう。\nまた、この魔物はずるがしこいやつで、\n回復能力の無い戦士を、集中して狙ってきます。\n気をつけましょう。":
    "This enemy has high HP, so expect a long battle.\nFurthermore, this monster is cunning and will focus\nits attacks on Warriors who lack healing abilities.\nWatch out!",

    "戦士は、騎士や神官と違って\n回復することができません。\nまた、神官や僧侶も、\n自分自身を回復させることはできません。\n慎重に編成してください。":
    "Unlike Knights and Clerics, Warriors cannot heal.\nAdditionally, Clerics and Priests cannot heal themselves.\nPlan your formation carefully!",

    "この敵はＨＰが低い仲間を、集中的に狙ってくる賢い魔物です。\nＨＰの低い仲間をどう守るかが、戦いの鍵になるでしょう。":
    "This clever monster focuses on allies with low HP.\nHow you protect them will be the key to victory.",

    "戦闘には、7人まで参加することができます。\n仲間の能力をよく見比べて、魔物を倒すのに\n最も適した者を選抜してください。":
    "Up to 7 allies can participate in battle.\nCompare your units' abilities carefully and select the\nbest party to defeat the monsters.",

    "この魔物は回復能力の無い戦士を狙ってくる、\nずる賢いやつです。\n防御補助や列回復をうまく使って、\n狙われた仲間をフォローしましょう。":
    "This cunning monster will target Warriors who cannot heal.\nUse Defend Assist and Row Healing wisely to support\ntargeted allies.",

    "戦闘中、後列で大量に回復したとき、\n全身にオーラをまとった%c80:0:0%『クリティカルチャージ』%c%状態に\nなることがあります。\n \nこの状態になると、次に攻撃する時、\n蓄積した回復量に応じて\n通常よりも強力な攻撃力を発揮します。\n \nしかし、敵からダメージを受けると、\nこの状態は失われます。":
    "During battle, healing a large amount of HP in the Back Row\ncan trigger an aura-clad %c80:0:0%[Critical Charge]%c% state.\n \nIn this state, the unit's next attack will deal massive\ndamage based on the total amount of HP restored.\n \nHowever, taking damage from enemies will cancel this state.",

    "敵は列回復者を狙ってくるいやらしい魔物です。\n列回復者は、自分自身を回復させることはできません。\nほかの仲間の助けを借りて、万全の陣形を作り上げましょう。":
    "The enemy is a nasty beast that targets Row Healers.\nRow Healers cannot heal themselves, so enlist the help\nof other allies to maintain a solid formation.",

    "敵はＨＰが高く、長期戦は避けられないでしょう。\nダメージを受けてもすぐに回復できるような陣形を\n作ることが重要です。\n \nまた、一度に複数の仲間を攻撃する%c80:0:0%『複数攻撃』%c%という\n特殊攻撃を繰り出してくるので、注意が必要です。":
    "The enemy has high HP, making a long battle inevitable.\nIt is vital to set up a formation that can quickly heal damage.\n \nAdditionally, watch out for their %c80:0:0%[Multi-Attack]%c% special\naction, which strikes multiple allies at once.",

    "この魔物は、ローテーション直後の攻撃が\n通常よりも強力になる%c80:0:0%『初回攻撃』%c%という能力を持った\n厄介な魔物です。\n \n攻撃力と初回攻撃力を足したものが、\nこの魔物の最大攻撃力になるので、注意してください。":
    "This troublesome monster possesses an ability called\n%c80:0:0%[First Attack]%c%, which boosts its offensive power\nimmediately following a rotation.\n \nBe careful, as its maximum attack power will equal\nits base Attack Power plus this First Attack bonus.",

    "カーソルを仲間に合わせたときに、\nＨＰの上に表示されているアイコンと数字が\n%c80:0:0%『疲労度』%c%の表示です。\n \n戦闘でダメージを受け、『疲労度』を蓄積した仲間は、\nこの表示がマイナスになり、能力が低下してしまいます。\n \n『疲労度』をためていない別の仲間と入れ替えるなどして\n全体の強さの維持に努めましょう。":
    "The icon and number shown above a unit's HP when hovering\nover them represents their %c80:0:0%[Fatigue]%c%.\n \nAllies who accumulate Fatigue from taking damage will suffer\nstat penalties, represented by negative values.\n \nMaintain your party's overall strength by swapping them out\nwith fresh allies who have no accumulated Fatigue.",

    "この魔物は、ローテーション直後の\n攻撃フェーズの始まりに、受ける攻撃のダメージを\n一定量防ぐ能力%c80:0:0%『初回防御』%c%を持っています。\n \nみかけより、倒すのに時間がかかると\n考えた方がいいでしょう。":
    "At the start of the attack phase right after rotating,\nthis monster uses %c80:0:0%[First Defense]%c% to negate\na set amount of incoming damage.\n \nExpect it to take longer to defeat than its appearance suggests.",

    "この魔物は、時折、前列にいる仲間全員に対して、\n一度にダメージを与える%c80:0:0%『列攻撃』%c%を繰り出してくるので\n注意してください。\n \nなお特殊な攻撃を繰り出すタイミングは、\n敵の情報画面の%c80:0:0%『攻撃パターン』%c%で見ることができます。":
    "This monster will occasionally perform a %c80:0:0%[Row Attack]%c%,\ndealing damage to all Front Row allies at once.\n \nYou can check the timing of their special attacks under\nthe %c80:0:0%[Attack Patterns]%c% on the enemy information screen.",

    "この魔物は、時折、通常の攻撃力の\n１．５～２倍のダメージを与える攻撃%c80:0:0%『怒りの一撃』%c%を\n繰り出してくるので気をつけましょう。\n \nなお特殊な攻撃を繰り出すタイミングは、\n敵の情報画面の『攻撃パターン』で見ることができます。":
    "Be on guard, as this monster will occasionally unleash an\n%c80:0:0%[Anger Strike]%c% that inflicts 1.5 to 2 times its\nnormal damage.\n \nYou can view the timing of their special attacks under\n[Attack Patterns] on the enemy information screen.",

    "ここまでの戦いで、『疲労度』がたまり、\n調子を落としている仲間もいるかもしれません。\n \n今まで戦いに参加していない別の仲間と\n入れ替えることも戦略の一つです。":
    "After battling this far, some allies may have accumulated\nFatigue and had their performance drop.\n \nSwapping them out for allies who haven't participated in\ncombat yet is a sound strategic choice.",

    r" \x01": r" \x01",

    "属性を確認するには、編成画面のメニューを開いて\n%c80:0:0%『属性の確認』%c%を選ぶか、\nＬ２ボタンを押して出たマークで確かめてください。":
    "To check element attributes, open the menu in the Formation\nscreen and select %c80:0:0%[Confirm Attributes]%c%, or press\nthe L2 button to display their elemental symbols.",

    "この魔物は、時折、２回分の攻撃力を１回に集約させた\n強力な%c80:0:0%『力を溜める攻撃』%c%を繰り出してきます。\n敵が攻撃を仕掛けて来ずに、力を溜めるアクションをしたら、\n次回の攻撃には要注意です。\n \nなお\n特殊な攻撃を繰り出すタイミングは、\n敵の情報画面の『攻撃パターン』で見ることができます。":
    "This monster will occasionally prepare a powerful %c80:0:0%[Charge Attack]%c%,\nconcentrating two attacks' worth of power into a single strike.\nIf the enemy charges power instead of attacking, prepare for the next turn.\n \nYou can view the timing of their special attacks under\n[Attack Patterns] on the enemy information screen.",

    "この森の敵は、攻撃力が高いわりに、\n比較的ＨＰが低いものが多いようです。\nローテーションをしないで\n一気に片をつける陣形を取るのも\n戦法のひとつでしょう。":
    "While the enemies in this forest have high Attack Power,\nmost have relatively low HP.\nSetting up a formation to defeat them quickly without\nrotating is a viable strategy.",

    "この魔物は、時折、前列の特定の仲間を狙って、\n連続で攻撃を仕掛ける%c80:0:0%『連続攻撃』%c%を繰り出してくるので、\n注意が必要です。":
    "This monster will occasionally focus its strikes on a specific Front Row\nally, executing a %c80:0:0%[Consecutive Attack]%c%. Stay alert!",

    "この魔物は、時折、\nダメージを与えると同時に、\n回復者の能力を封じてしまう\n%c80:0:0%『死の呪い攻撃』%c%を繰り出してくるので、\n注意が必要です。\nなお、回復不能の呪いは、\n一度ローテーションして\n後列を通過すると解除されます。":
    "This monster will occasionally inflict a %c80:0:0%[Death Curse Attack]%c%,\ndealing damage and sealing the target's healing abilities.\n \nThis heal-blocking curse can be cured by rotating the unit\nthrough the Back Row once.",

    "この魔物は、時折、\n仲間のＨＰを１になるまで吸収して、\nその分だけ自分が回復する%c80:0:0%『生命力奪取攻撃』%c%を\n繰り出してくるので、注意が必要です。\nなお、『生命力奪取攻撃』は、\n防御補助があっても、回避することはできません。":
    "This monster will occasionally perform a %c80:0:0%[Lifesteal Attack]%c%,\ndraining an ally's HP down to 1 and healing itself by that amount.\n \nNote that this Lifesteal Attack cannot be blocked,\neven with Defend Assist.",

    "この魔物は、時折、\nすべての列にいる仲間全員にダメージを与える\n%c80:0:0%『全体攻撃』%c%を繰り出してくるので。\n注意が必要です。\nなお、この攻撃には防御補助は無効です。":
    "This monster will occasionally unleash a %c80:0:0%[All-Out Attack]%c%,\ninflicting damage on all allies across all rows.\n \nPlease note that Defend Assist will not block this attack.",

    "この魔物は、時折、\n攻撃を一回休み、その後の攻撃力を\n増加させる%c80:0:0%『攻撃力強化』%c%の特殊能力を\n発揮します。\n \nこの能力は、%c80:0:0%『力を溜める』%c%攻撃と違い\n増加した攻撃力が、戦闘終了まで持続します。\n \nまた、攻撃力強化を行った後に攻撃力強化を行うと、\nさらに攻撃力が増加します。":
    "This monster occasionally skips a turn to execute an %c80:0:0%[Attack Power Boost]%c%,\nincreasing its offensive power for subsequent turns.\n \nUnlike a %c80:0:0%[Charge]%c% action, this attack power increase\npersists until the end of the battle.\n \nFurthermore, stacking multiple boosts will increase its Attack Power even further.",

    "この魔物は、時折、\n前列の仲間を攻撃をした時に\nその位置に火柱を残す\n%c80:0:0%『煉獄の炎』%c%攻撃を繰り出してくるので、\n注意が必要です。\nなお、火柱の位置にいる仲間は、\n攻撃フェーズ開始時にダメージを受けてしまいます。\n火柱は戦闘フェーズを数回経過すると消えます。":
    "This monster will occasionally strike Front Row allies and leave\na column of fire behind, called the %c80:0:0%[Purgatory Flame]%c%.\n \nAllies standing in the burning spots will take damage at the\nstart of each attack phase.\nThe fire columns will dissipate after several combat phases pass.",

    "この魔物は、時折、祈祷師と同様、相手を固める\n%c80:0:0%『石化攻撃』%c%攻撃を繰り出してきます。\n \n石化状態になると、通常時より\nダメージを受けやすくなるので注意が必要です。":
    "Like Shaman units, this monster can inflict a petrifying %c80:0:0%[Petrification Attack]%c%.\n \nBe careful, as petrified units will take significantly more\ndamage than usual.",

    "この%c80:0:0%盗賊団%c%は、\n魔物である誘惑者と複数の人間で構成されていますが、\n人間たちは魔物に操られているだけなので、\n \nリーダーである誘惑者を倒した時点で\n騎士団の勝利となります。\n \nまた、盗賊団は戦闘時にローテーションも行います。":
    "This %c80:0:0%Thief Guild%c% consists of a monster known as the Temptress\nand several humans. Since the humans are merely being manipulated,\n \ndefeating the leader, the Temptress, will instantly secure\nvictory for your Order.\n \nNote that the Thief Guild will also rotate during battle.",

    "この魔物は、時折、\n前列の仲間のだれかを消し去ってしまう\n%c80:0:0%『異次元追放』%c%攻撃を繰り出してくるので、\n注意が必要です。\n消されてしまった仲間は\n数ターン後、元の位置へ戻ってきます。\nなお、この攻撃は防御補助で防ぐことはできません。":
    "This monster will occasionally banish a Front Row ally to another dimension,\nusing an action called %c80:0:0%[Dimensional Banish]%c%.\nThe vanished ally will return to their position after several turns.\nNote that this attack cannot be blocked by Defend Assist.",

    "この魔物は、聖騎士レイスにしか倒すことが出来ません。\nほかの仲間が止めを刺しても、魔物はすぐに復活してしまうので、\n騎士団の負けになります。\n\u3000\nうまく編成して、聖騎士レイスに最後の止めを刺させましょう。":
    "This monster can only be defeated by the Paladin Wraith.\nIf any other ally deals the finishing blow, the monster will immediately\nrevive, resulting in defeat for your Order.\n \nArrange your formation carefully so that the Paladin Wraith deals the final blow."
}

def main():
    csv_path = "translation_catalog_split/Tutorial_FHMText.csv"
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
        # Clean potential whitespace variations
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
        print(f"[+] All {len(rows)} FHM entries successfully mapped!")

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Successfully wrote {translated_count} translations to {csv_path}.")

if __name__ == "__main__":
    main()
