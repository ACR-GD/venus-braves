#!/usr/bin/env python3
import os
import csv

# We map each part by its index from 0 to 124 to avoid whitespace mismatch issues.
TRANSLATIONS = {
    0: "「The Calamity of Beginnings」",
    1: "Year 999\nThe most wicked demon of the Dark Kin shall awaken.\nHe shall awaken in the southern lands and wander through time,\nsowing the seeds of despair across the world.\n",
    2: "「Fall of the Frontier Town」",
    3: "Year of the Moon. Year of Fire.\nRotten bats shall plague the stone mound.\nAnd in the Year of Fire, the black, infinite calamity awakened in the south\nshall crush the stone mound, soon dyeing all southern lands\nin crimson red.\n",
    4: "「The Starving Calamity」",
    5: "Year of the Night\nUgly sediment shall settle upon the southern mound of abundance.\nAn impure melody of the harp shall flow from the womb of the stone.\nThe melody echoing across the earth shall bring great impotence,\nand the souls who have lost their sustenance shall perish.\n",
    6: "「Calamity of the Water City」",
    7: "The pedestal of the spear that records time, floating upon the leaf veins.\nIts amniotic fluid shall be defiled by black sediment.\nThe impurity shall cover the world in an instant, singing a song of ruin.\n",
    8: "「Calamity of the Misty Valley」",
    9: "Year 1020: The \"black, infinite calamity\" awakened in the south\nshall fold its wings upon the misty green world.\n",
    10: "「The Beginning of Famine」",
    11: "The south of the earth shall be covered in barrenness, and even the scarce sustenance\nshall be seized by the ugly sediment.\nPeople shall writhe in starvation, and plunderers shall appear.\nThe plunderers shall fall to darkness, continuing to multiply their cohorts.\n",
    12: "「Ravage of the Demon General」",
    13: "The black, infinite calamity shall sharpen its claws and fly away to the west.\nThe western lands shall endure a night of nightmare and become a world of death.\n",
    14: "「The Maiden's Unreached Prayer」",
    15: "At the boundary separating the crest of the earth and its cheek, the sediment\nshall fall. The stagnant dregs shall fester upon that cheek, and the defiled dregs shall defile the maiden.\n",
    16: "「The Destroyed Clock Tower」",
    17: "The spear, protected by the pedestal floating on water, shall find favor with the infinite calamity.\nThe spear that recorded past friendship and parting shall be shattered to pieces by innocent playing of soldiers.\n\nThe lost contract shall never be restored.\n",
    18: "「The Unreturning Souls」",
    19: "The violated waters and the invaded sacred river\nshall further derail the path of the maddened souls.\nThe souls with nowhere to go shall scatter, soon becoming things of darkness.\n",
    20: "「The Closed Prayer」",
    21: "People shall fear prayer.\nThe teachings shall close their gates, and faith shall be thrown into disarray.\nSoon they shall suspect their brethren, fight, and accelerate toward calamity.\n",
    22: "「Attack on the Royal Capital」",
    23: "The calamity shall be summoned to the capital at the center of the continent.\nBats, mold, nightmares, lamentations, despair.\nThe calamity shall fold its wings, the prey shall be easily devoured, and when its nest is gone, the world of death shall arrive in the blink of an eye.\nFor even the prey scattered to all places shall be captured.\n",
    24: "「The Annihilation of Lion」",
    25: "The earth shall rot, reaching the south-western lands.\nThe decayed land shall become one with the forest inhabited by succubi, creating further festering.\n",
    26: "「The Drying of the Water City」",
    27: "The town that has lost time shall soon lose its moisture.\nThe parched soil shall not welcome the lives of the people.\n",
    28: "「The Calamity Looming Over the Capital」",
    29: "The yearning calamity shall gaze enviously at the center of the continent from within the pitch-black green.\nBut soon it shall fail to endure, ruining the painted colors.\nThe central lands shall become a battlefield overnight, leaving not a single soldier.\n",
    30: "「Country of Famine and Thieves」",
    31: "A barren wind shall blow across all lands.\nThe plunderers shall form a country, and a great conflict shall begin.\n",
    32: "「The Demonic Capital」",
    33: "The central capital shall become a perfect roost for the black, infinite calamity.\nThe calamity shall dye the capital black and immediately head toward all the world.\n",
    34: "「Lost Order」",
    35: "The capital shall be gravely wounded, and those who govern the people shall be lost.\nPeople shall be thrown into chaos, fighting until the end of the world.\n",
    36: "「The Cursed Seven Braves」",
    37: "The realm of calamity shall reach the land of the Seven Braves as well.\nThe unearthed Seven Braves shall bring forth new calamities of seven colors.\nThe stirred and mixed seven colors shall soon be stained with evil, painting over the world.\n",
    38: "「Gate of the Demon World」",
    39: "In the ruins of the lost capital, the evil sediment shall continue to stagnate.\nAt last, the sediment shall corrode further, creating yet another fissure in the earth.\nFrom there, defiled souls shall continue to escape, soon covering the world in sorrowful blue.\n",
    40: "「Chaos of the Mountain Town」",
    41: "The mountain town that has lost goodwill shall become a nest of thieves.\nIt shall soon perish by its own hand.\n",
    42: "「The Knights of Ruin」",
    43: "Upon the rock floating in the north-western sea, evil souls shall gather.\nWith many souls gathered, they shall become the Knights of Ruin.\n\nCalamity is not merely the stagnant sediment.\nA multitude of souls who have forgotten themselves shall form a group, turning their fangs even upon parents and children.\n",
    44: "「The Monsters' Lair」",
    45: "In the place where the misty forest once stood, demons shall gather.\nSoon, a massive distortion shall emerge there.\n",
    46: "「Crisis of the North Sea」",
    47: "In the North Sea beyond time, the black, infinite calamity shall arrive.\nThe wings shall use their power to bring disaster, drawing the curtain of victory.\n\nOpaque waves. Dance of the drowned.\n\nThey shall be sucked into the lusterless scales.\n",
    48: "「The Calamity of the Seven Braves」",
    49: "The seven heroes once unearthed shall take up their weapons again, reaping the souls on earth.\nHalf the people of the land shall lose their heads to the now-maddened former heroes.\n",
    50: "「The Cursed Coastal City」",
    51: "A calamity shall wash ashore on the eastern coast.\nShips shall become ghost ships, and the town shall become a city of the dead.\n\nConsolations shall never end.\n",
    52: "「The Defiled Port」",
    53: "The defiled port shall continue to carry people of despair into the world.\n",
    54: "「Rule of the Knights of Ruin」",
    55: "The Knights of Ruin shall secure rule over the land, continuing to destroy their own brethren.\n",
    56: "「The Prince of Darkness」",
    57: "Upon the ruins where holy women once gathered, the Prince of Darkness shall descend.\n\nWith a single swing of his sword, the Prince of Darkness shall reap thousands of souls.\n",
    58: "「The Great Forest Fire」",
    59: "A small nightmare shall visit the forest in the valley.\nThe forest shall be enchanted by the nightmare, burning with a crimson flame.\nBefore realizing that love was a mistake, the forest shall be turned to a scorched field.\n\nThe thousand charred corpses lined up shall sing a requiem.\n",
    60: "「Fall of the Coastal City」",
    61: "The sediment that stared at the eastern coast shall enter through its wound, gradually causing the earth to necrotize.\n\nThe body unable to overcome the decayed cells\nshall become a perfect stage to rot all the world.\n",
    62: "\n「Starvation and Monsters」",  # Wait, let's verify if 62 has a leading newline
    63: "In the world, there are only monsters and starving humans.\nMankind shall split into those who step onto paths that must never be trodden, and those who throw their souls into a new world.\n",
    64: "「The New Demon」",
    65: "The black prayer and the sorrow-colored soul shall resonate, continuing to spawn new demons.\nOvernight, demons shall ravage all lands.\n",
    66: "「The Praying One」",
    67: "The immortal woman who stepped into the eternal world that must never be violated shall become a great banner for fools and the weak.\nMany souls shall discard their bodies of their own accord in search of a new world. But those souls shall never be purified, instead absorbed by the infinite calamity, becoming the triggers of the Great Catastrophe.\n",
    68: "「The Decimation of Humanity」",
    69: "Fools and the weak across the world shall sacrifice their bodies, and it shall breed new despair in the world.\nThe black robe who accomplished the great feat shall obtain what he has long desired.\n",
    70: "「The Gathering of the Seven Braves and Calamities」",
    71: "The cursed Seven Braves shall become one with all calamities, awaiting the bell of catastrophe.\n",
    72: "「The Town Burned to Ashes」",
    73: "The nightmare shall return, and the town shall be enchanted.\nThe blazing town shall perish alongside the fools.\n",
    74: "「The Great Catastrophe of Ruin」",
    75: "Year 1099\nAll the worlds.\nSandy-brown sky. Steel-colored moon.\nAn unceasing discordance. The earth trembling at its spear.\nThe calamity shall fold its wings where it roams, spreading black roots.\n\nDripping tears. The pierced saint.\nThe world is painted in despair.\n\nYear 1099\nAnd, all the worlds shall die.",
    76: "\n",
    77: "Year of the Night\nUgly sediment shall settle upon the southern mound of abundance.\nHowever, the sediment shall be washed away by the few heroes led by the immortal, and the melody shall neutralize the calamity that is about to flow from the womb of the stone.\nThe fertile land shall continue to bring forth souls!",
    78: "The pedestal of the spear that records time, floating upon the leaf veins.\nThe washed-away sediment shall wash ashore, and its amniotic fluid shall be defiled.\nThe impurity shall cover the world in an instant, singing a song of ruin. The song shall summon unceasing bloodshed, and no gag can stop it.\nThere, only ruins floating on the water shall remain.\n\n@\nMonsters shall appear in the Water City Sukure.\nSukure shall be destroyed, and the calamity shall spread across the world.",
    79: "Year 1020: The black, infinite calamity awakened in the south\nshall fold its wings upon the misty green world.",
    80: "A barren wind shall blow across all lands.\nThe plunderers shall form a country, and a great conflict shall begin. DUMMY",
    81: "The pedestal of the spear that records time, floating upon the leaf veins.\nThe washed-away sediment shall wash ashore, and its amniotic fluid shall be defiled.\nThe soldiers guided by the one in the eternal world shall remove the impurity and never allow the song of ruin to be sung. The spear that records time shall indeed shine toward the full moon!",
    82: "\nYear 1020: The black, infinite calamity awakened in the south\nshall fold its wings upon the misty green world.\nThe green world shall be lost in an instant, losing all life. All the worlds shall writhe and distort, and soon the green shall be dyed in red.\n@\nThe Tigor Valley shall be attacked by the Demon General.\nThe valley shall be annihilated in a single night. No survivors.",
    83: "Year 1020: The black, infinite calamity awakened in the south, shall fold its wings upon the misty green world.\n\nBut it shall be repelled by the red-eyed knight and his soldiers.\n\nThe green world shall preserve its radiance!\n\nThe black, infinite calamity shall fall asleep, and soon awaken as something even more sinister.",
    84: "At the boundary separating the crest of the earth and its cheek, the sediment shall fall. The stagnant dregs shall fester upon that cheek, and the festering shall defile the maiden. The prayers of the maidens shall not reach the heavens; the maidens shall be eradicated, and even their stronghold shall leave no trace.\n\n@\nThe monastery at the foothills shall be attacked, and the nuns shall perish.",
    85: "At the boundary separating the crest of the earth and its cheek, the sediment shall fall. But it shall be treated by the red-eyed immortal and the soldiers before any festering occurs.\nThe maidens' prayers shall reach the heavens, and their stronghold shall never cease to be!",
    86: "The awakened black, infinite calamity shall first lay eyes upon the spear protected by the pedestal floating on water.\nThe spear that recorded past friendship and parting shall be shattered to pieces by innocent playing of soldiers.\nThe lost contract shall never be restored.\nThe black, infinite calamity shall unleash an unprecedentedly sinister roar, and the spear shall be utterly destroyed beyond recovery.\n\n@\n\nBy the hand of the now more sinister Demon General, the clock tower of the Water City shall be destroyed without a trace.",
    87: "「Drop of Darkness」",
    88: "Year 1099\nInto the fissure of the earth, the drop of darkness shall fall.",
    89: "The awakened black, infinite calamity shall first lay eyes upon the spear protected by the pedestal floating on water.\nHowever, the spear that recorded past friendship and parting shall be put back to sleep by the group led by the immortal man. The clock tower shall continue to tower toward the moonlit night. Yet, the slumber of the black, infinite calamity shall be shallow.",
    90: "The calamity shall be summoned to the capital at the center of the continent. Bats, mold, nightmares, lamentations, despair. The calamity shall fold its wings, the prey shall be easily devoured, and when its nest is gone, the world of death shall arrive in the blink of an eye. For even the prey scattered to all places shall be captured.\nThe \"Wings of Calamity\" shall start with this, clawing at the world and continuing to multiply wounds that never heal.\n\n@\nThe Royal Capital shall become the center of calamity. It shall suffer attacks from monsters, and furthermore, the <Calamity of Power> shall show itself.",
    91: "The calamity shall be summoned to the capital at the center of the continent. However, the capital shall preserve its form, bathed in the light of the sun, by the Order led by the immortal man.\nYet the \"Wings of Calamity\" shall mingle in the darkness, clawing at the world and continuing to multiply wounds that never heal.",
    92: "The yearning calamity shall gaze enviously at the center of the continent from within the pitch-black green.\nBut soon it shall fail to endure, ruining the painted colors.\nThe central lands shall become a battlefield overnight, leaving not a single soldier.\n\n@\nMonsters shall visit near the Royal Capital.\nThe calamity shall loom over the Royal Capital, eventually bringing it to ruin.",
    93: "The yearning calamity shall gaze enviously at the center of the continent. The calamity was supposed to ruin the painted colors, but it shall be punished beforehand by the Order led by the immortal. And the capital shall shine with the radiance of the full moon!",
    94: "The central capital shall become a perfect roost for the black, infinite calamity. The calamity shall dye the capital black and immediately head toward all the world.\n\n@\nThe Demon General shall appear in the Royal Capital, destroying it.\nSoon, the calamity shall spread across the entire continent.",
    95: "The central capital shall become a perfect roost for the black, infinite calamity. However, the calamity shall fall back into a temporary slumber before the swords wielded by the red-eyed hero and his allies.\n\nThe black, infinite calamity shall awaken shortly, becoming the ruler of all.",
    96: "The calamity shall roam the world with its wings, and the realm of calamity shall reach the land of the Seven Braves as well.\nThe Seven Braves unearthed by the \"Calamity of Power\" shall bring forth new calamities of seven colors. The stirred and mixed seven colors shall soon be stained with evil, painting over the world.\n\n@\nThe calamity shall reach the land of the Seven Braves, Acrarind.\nThe Seven Braves shall be resurrected by a curse, turning into a cohort of death that destroys the world.",
    97: "In the North Sea beyond time, the \"Calamity of Power\" shall descend, awaiting the awakening of the black, infinite calamity.\nThe wings shall use their power to bring disaster, drawing the curtain of victory. Opaque waves. Dance of the drowned. They shall be sucked into the lusterless scales.\n\nThe black, infinite calamity that rules all shall consume the world in no time.",
    98: "The calamity shall roam the world with its wings, and the realm of calamity shall reach the land of the Seven Braves as well.\nBut the calamity shall be destroyed by the heroes who cross even the seas, and the Seven Braves shall preserve their peaceful, eternal slumber!",
    99: "Upon the rock floating in the north-western sea, evil souls shall gather. With many souls gathered, they shall become the Knights of Ruin. The calamity is not merely the stagnant sediment. A multitude of souls who have forgotten themselves shall form a group, turning their fangs even upon parents and children.\n\nThe Knights of Ruin shall grow in number, filling the world and awaiting the Great Catastrophe.\n\n@\nA calamity shall appear in Ilgull, the north-western island.\nIt does not seem to be an ordinary monster.\nSoon, they shall grow in number, to the point of filling the world.",
    100: "Upon the rock floating in the north-western sea, evil souls shall gather. With many souls gathered, they shall become the Knights of Ruin. But the Knights of Ruin shall be purified by the red-eyed Order.\n\nA few wandering souls shall remain in the world.",
    101: "In the North Sea beyond time, the \"Calamity of Power\" shall descend, awaiting the awakening of the black, infinite calamity.\n\nThe wings shall use their power to bring disaster, drawing the curtain of victory. Opaque waves. Dance of the drowned. They shall be sucked into the lusterless scales.\n\nThe black, infinite calamity that rules all shall consume the world in no time.\nWith preparations complete without delay, the Great Catastrophe shall visit.\n\n@\n\nIn north-western Ilgull, the <Calamity of Power> shall descend. The Demon General shall awaken there as well.\n\nBy the <Wings of Calamity>, humanity shall eventually be destroyed, and the terror of the Demon General shall cover the world.\nThey shall trigger the Great Catastrophe.",
    102: "Year 1099\nInto the fissure of the earth, the drop of darkness shall fall. \nThe black, infinite calamity and the Wings of Calamity shall gather together, beginning their dominion over the world.",
    103: "In the North Sea beyond time, the \"Calamity of Power\" shall descend, awaiting the awakening of the black, infinite calamity.\nAlong the path to the Great Catastrophe, the Order led by the immortal shall stand in the way, thwarting the \"Calamity of Power\" and putting the newly awakened black, infinite calamity back to sleep.\nThe Wings of Calamity shall lose their balance, but the black, infinite calamity shall devour all souls upon its next awakening.",
    104: "A calamity shall wash ashore on the eastern coast.\nShips shall become ghost ships, and the town shall become a city of the dead. The mourning shall never end.\nThe unceasing weeping shall continue until the Great Catastrophe.\n\n@\nA calamity shall strike the Coastal City Mezonea.\nThe people's panic shall continue until the Great Catastrophe.",
    105: "A small nightmare shall visit the forest in the valley.\n\nForest shall be enchanted by the nightmare, burning with a crimson flame. Before realizing that love was a mistake, the forest shall be turned to a scorched field.\n\nThe thousand charred corpses lined up shall sing a requiem. The requiem shall soon play a discordance, continuing until the end of the world.",
    106: "The sediment that stared at the eastern coast shall enter through its wound, gradually causing the earth to necrotize. The body unable to overcome the decayed cells shall become a perfect stage to rot all the world. The corrosion shall not stop, continuing to advance until the death of the world.",
    107: "The immortal woman who stepped into the eternal world that must never be violated shall become a great banner for fools and the weak.\nThe city of prayer shall become a city of the dead, and many souls shall discard their bodies of their own accord in search of a new world.\nThe souls fearing the creeping death shall never be purified, instead absorbed by the infinite calamity, becoming the triggers of the Great Catastrophe.",
    108: "Year 1099\nInto the fissure of the earth, the drop of darkness shall fall.\nThe Demon General who wandered through time shall awaken, finally obtaining absolute power.",
    109: "The calamity washed ashore on the eastern coast shall be averted by the red-eyed knights. The ship shall sail toward the morning sun!",
    110: "A small nightmare shall visit the forest in the valley.\n\nThe forest shall be enchanted by the nightmare, burning with a crimson flame. Before realizing that love was a mistake, the forest shall be turned to a scorched field.\n\nThe thousand charred corpses lined up shall sing a requiem. The requiem shall soon play a discordance, continuing until the end of the world.\n\n@\nThe forest in the north-eastern valley shall be turned to a scorched field.\nAll residents shall burn to death.",
    111: "The sediment that stared at the eastern coast shall enter through its wound, gradually causing the earth to necrotize. The body unable to overcome the decayed cells shall become a perfect stage to rot all the world. The corrosion shall not stop, continuing to advance until the death of the world.",
    112: "The immortal woman who stepped into the eternal world that must never be violated shall become a great banner for fools and the weak.\nThe city of prayer shall become a city of the dead, and many souls shall discard their bodies of their own accord in search of a new world.\n\nThe souls fearing the creeping death shall never be purified, instead absorbed by the infinite calamity, becoming the triggers of the Great Catastrophe.",
    113: "A small nightmare shall visit the forest in the valley.\nThe forest shall be enchanted by the nightmare, burning with a crimson flame and turning to a scorched field.\n\nBut the nightmare shall be repelled by the red-eyed heroes, and the forest shall one day harbor a new brilliance!",
    114: "The sediment that stared at the eastern coast shall enter through its wound, gradually causing the earth to necrotize. The body unable to overcome the decayed cells shall become a perfect stage to rot all the world. The corrosion shall not stop, continuing to advance until the death of the world.\n\n@\nA calamity shall strike the Coastal City Mezonea once again.",
    115: "The sediment that stared at the eastern coast shall enter through its wound, but the group led by the immortal shall stop its corrosion. The eastern coast shall preserve its antibody, overcoming the calamity!",
    116: "The immortal woman who stepped into the eternal world that must never be violated shall become a great banner for fools and the weak.\nThe city of prayer shall become a city of the dead, and many souls shall discard their bodies of their own accord in search of a new world.\n\nThe souls fearing the creeping death shall never be purified, instead absorbed by the infinite calamity, becoming the triggers of the Great Catastrophe.\n\nThe \"Black Calamity\" shall accomplish all this, becoming the architect of the catastrophe.\n\n@\nIn what has become a city of the dead, a ritual of prayer shall be held.\nMany lost masses shall gather there, throwing away their lives.\n\nThe cause of it all is the <Black Calamity>.",
    117: "The immortal woman who stepped into the eternal world that must never be violated shall become a great banner for fools and the weak.\nThe city of prayer shall become a city of the dead, and many souls shall discard their bodies of their own accord in search of a new world.\n\nHowever, the \"Black Calamity\" who accomplished all this shall be laid to rest by the heroes led by the immortal.",
    118: "Year 1099\nInto the fissure of the earth, the drop of darkness shall fall.\nThe drop shall become the tears of souls, and the Demon General shall awaken, obtaining absolute power.\nThe festival that brings death to the world shall begin.\n\n@\nFrom the drop of darkness, the Great Catastrophe shall begin.",
    119: "The calamity shall be summoned to the capital at the center of the continent. However, the capital shall preserve its form, bathed in the light of the sun, by the Order led by the immortal man.\nYet the \"Wings of Calamity\" shall mingle in the darkness, clawing at the world and continuing to multiply wounds that never heal.",
    120: "Year 1099\nInto the fissure of the earth, the drop of darkness shall fall.\nThe drop shall become the tears of souls, and the Demon General shall awaken, obtaining absolute power.\nThe festival that brings death to the world shall begin.",
    121: "「The Maddened Ancestor」",
    122: "Year 1099\nBy the Order led by the immortal, the breath of the black, infinite calamity shall be cut short.\nThe clock that carves souls, expressing friendship and grief, shall stop moving; the sediment, the distillate, and the souls shall all be released into the same world.\nThe mad descendant of the progenitor shall attempt to create a new world.\n\nThe devouring antibody shall ravage the world, consuming all foreign matter.\n\nYear 1099\nAll the worlds.\nSandy-brown sky. Steel-colored moon.\nAn unceasing discordance. The earth trembling at its spear.\n\nThe descendant of the mad progenitor shall appear once more, concluding the final act of the festival.\n\nDripping tears. The pierced saint.\nThe world is painted in despair.",
    123: "「Death of the World」",
    124: "Year 1115\nAnd, all the worlds shall die.\n\n@\nBy the Creator of Destruction, all life shall vanish from all the worlds."
}

def main():
    csv_path = "translation_catalog_split/Story_Prophecy.csv"
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

    # Reconstruct the text block
    orig_text = rows[0][2]
    orig_parts = orig_text.split("\\x00")
    
    trans_parts = []
    for idx, part in enumerate(orig_parts):
        if idx in TRANSLATIONS:
            trans_parts.append(TRANSLATIONS[idx])
        else:
            print(f"[-] Missing mapping for part {idx}!")
            trans_parts.append(part)

    english_text = "\\x00".join(trans_parts)
    rows[0][3] = english_text

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"[+] Reconstructed prophecy successfully and wrote to {csv_path}.")

if __name__ == "__main__":
    main()
