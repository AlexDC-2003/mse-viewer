# Magic Set Viewer - MSV

---

# 1. Problem Analysis

## 1.1 Problem Context & Vision

The Magic Set Editor (MSE) allows its users to create custom Magic the Gathering (MTG) cards, that then are stored across different set files. However, after creating multiple set files, keeping track of what these files contain, as well as the hundreds of cards and mechanics across different files, can become cumbersome. For example, custom keywords that creators wish to reuse must be redefined per individual set file, and as such any modifications to keyword text must be repicated on each individual file containing that keyword, vulnerable to human error. Furthermore, for cards that have been already issued, any further modifications to the cards (such as balancing updates) require re-issuing, which could cause confusion and inconsistency across card versions.

The aim is to create a simple unified system that will aid card creators using MSE to keep track of their cards. The system should store the cards and allow for easy filtering among them, while also keeping track of any card modifications and any further actions the issuing party should take notice of. An interactive UI will be used by creators to interact with the various cards stored, and the system should offer less-privilege hooks which will be used by players to browse cards and select them for their decks, notifying the creators about issuing requests. 

Our system should deliver fast performance, while keeping data integrity. The UIs should be easy to use for both the card creators and the players. Conversion of data from MSE to the MSV should be error-free and capture all the essential data from the cards inputted.

The MSV aids MSE users keep track of their cards, notify them of any issuing actions required, and offer interactive UIs that will help filter through the cards for potential decks.

## 1.2 Stakeholder Identification

----

# 2. Solution Design

## 2.1 Technical Background Information

MSE stores its sets into files with the ".mse-set" extension. These files are, in fact, archives. After extracting, we obtain multiple "imageX" files that contain image data for the card pictures used in the cards, and a single "set" file. This "set" file contains text regarding all the card data: card names, stats and abilities, keyword definitions, set information.

The "set" file structured in the following way:

1. A "header", containing all the set metadata - MSE version and file timestamps, stylesheet information, and some template styling options active for that set (though some information regarding template is present in each card's metadata)
2. Card fields - a list of "card" fields. Each field corresponds to an individual card metadata, preceded by a "card:" identification string. It contains all the information about rules text, cost, stats. An example of a card field:
```
card:
	stylesheet: m15-altered-beyond
	stylesheet_version: 2020-09-04
	has_styling: false
	notes: 
	time_created: 2023-12-30 18:53:34
	time_modified: 2024-10-28 01:27:23
	card_color: black, green, hybrid, horizontal
	name: Baraggan King of Souls
	alias: Evo: Baraggan Louisenbairn
	casting_cost: BG
	image: 
	image_2: 
	mainframe_image: 
	mainframe_image_2: 
	super_type: <word-list-type-en>Evolution Creature</word-list-type-en>
	sub_type: <word-list-race-en>Menos</word-list-race-en><soft><atom-sep> </atom-sep></soft><word-list-class-en></word-list-class-en>
	rarity: uncommon
	rule_text:
		<kw-0><nospellcheck><key>Evolve: <param-name>Baraggan Louisenbairn</param-name></key></nospellcheck></kw-0>
		<kw-1><nospellcheck><key>Evocycling</key></nospellcheck><atom-reminder-custom> <i-auto>(Discard this card: Search your library for its unevolved form, put it in your hand, then shuffle your library.)</i-auto></atom-reminder-custom></kw-1>
		Creatures opponents control have -2/-2.
		Other creatures you control have +2/+2.
	flavor_text: <i-flavor></i-flavor>
	power: 4
	toughness: 5
	card_code_text: 
	card_code_text_2: 
	card_code_text_3: 
	copyright: 
	copyright_2: 
	copyright_3: 
```
3. Keyword definitions - contains all the custom defined keywords for that set file. An example of a keyword definition:
```
keyword:
	keyword: Evolution
	match: Evolve: <atom-param>name</atom-param>
	reminder: To cast this spell, you must transform a {param1}.
	rules: 
	mode: custom
```





