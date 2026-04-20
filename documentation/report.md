# Magic Set Viewer - MSV

---

# 1. Problem Analysis

## 1.1 Problem Context & Vision

The Magic Set Editor (MSE) allows its users to create custom Magic the Gathering (MTG) cards, that then are stored across different set files. However, after creating multiple set files, keeping track of what these files contain, as well as the hundreds of cards and mechanics across different files, can become cumbersome. For example, custom keywords that creators wish to reuse must be redefined per individual set file, and as such any modifications to keyword text must be repicated on each individual file containing that keyword, vulnerable to human error. Furthermore, for cards that have been already issued, any further modifications to the cards (such as balancing updates) require re-issuing, which could cause confusion and inconsistency across card versions.

The aim is to create a simple unified system that will aid card creators using MSE to keep track of their cards. The system should store the cards and allow for easy filtering among them, while also keeping track of any card modifications and any further actions the issuing party should take notice of. An interactive UI will be used by creators to interact with the various cards stored, and the system should offer less-privilege hooks which will be used by players to browse cards and select them for their decks, notifying the creators about issuing requests. 

Our system should deliver fast performance, while keeping data integrity. The UIs should be easy to use for both the card creators and the players. Conversion of data from MSE to the MSV should be error-free and capture all the essential data from the cards inputted.

The MSV aids MSE users keep track of their cards, notify them of any issuing actions required, and offer interactive UIs that will help filter through the cards for potential decks.

## 1.2 Use Cases

Our system is designed as a complete one-stop solution for item organization, ensuring that warehouse workers always know where an item should be stored or retrieved from. Therefore, we developed a series of scenarios that integrate the most common and predictable use case needs into one workflow.

1. __Storing Card Data__: The system should store all the card data into a persistent database
    - Users inputs their .mse-set files containing their cards.
    - System extracts all card data from those files, separates it into individual card properties, then stores that card.
    - Upon input of a card with the same properties as a card already in the database, system throws a warning and asks for review.
    - Users can query the database for cards with specific properties.
    - Users can update card properties.
    - Cards in the database will be associated with Power scores based on their attributes, set by the creator.
    - Users may dynamically assign Power scores to any subset of cards within a set file while inputting that set's card data.

2. __Storing Keywords__: The system should extract all the keywords from the input cards and store them separately.
    - Users may individually introduce card keywords, by stating their names and abilities.
    - When card data is inserted, if a keyword doesn't exist, the system extracts it and its functionality and stores it automatically.
    - When card data is inserted, if a keyword exists but its definition is modified, system throws a warning and asks for review.
    - Users can query the database for specific keywords, or cards bearing these keywords.
    - Users can update keyword definitions.
    - System is preloaded upon deployment with core official keywords.

3. __Storing Decks__: The system should store collections of cards, symbolizing MTG decks that use cards in the database.
    - Users may individually introduce deck files.
    - System extracts all cards in deck files, links to cards in the database, then stores decks as lists of references to cards.
    - Users can query the database for specific decks, and view cards in those decks.
    - Users can update decks.
    - Decks can hold additional information, such as theme, deck type, etc.
    - Users can generate exports of selected card data as text files in a consistent, predefined format.

4. __Update Workflows__: The system should notify users of need of print runs due to modifications to already existent objects.
    - Upon modification of a card or a keyword, system triggers an Update Workflow.
    - System searches for all decks containing that card / all cards containing that keyword, then for each of those decks/cards issues a notice message in an unread state regarding a new print run of the updated card.
    - User keeps a log of notices that can be in an unread, standby, issued or completed state.
    - Once a user reads a notice, it moves from an unread to a standby state.
    - Once a user has issued the print run, it can toggle the notice from standby to issued. 
    - Once a user delivers the updated card, it can toggle the notice from issued to completed.
    - For each notice in an issued state, users can add additional notes regarding the physical storage state of the new card print.

5. __Interactive Interface__: The system should offer a nice-looking, interactive interface.
    - Users can upload files to the system as input.
    - Users can perform queries on cards, keywords, and decks through an easy to use interface.
    - Users can view results of queries on cards, keywords, and decks in an easy to read format.
    - Users can interactively handle notice messages and their state.
    - Upon reviews being initiated, users will be presented with a diff of the existing version of the object in the database and the modified version of the object in the input.
    - Users will choose to accept or reject the input modifications. Upon accepting, system will trigger updates on all affected objects and issue notice according to the Update Workflow.

6. __Public Hooks__: <span style="color:pink">Coming Soon<sup>TM</sup></span>
    - <span style="color:pink">System should offer over-the-web, less privilege access to remote viewing users.</span>
    - <span style="color:pink">Viewers can query the databases for cards with specific properties.</span>
    - <span style="color:pink">Viewers can query the database for specific keywords, or cards bearing these keywords.</span>
    - <span style="color:pink">Viewers can query the database for specific decks, and view cards in those decks.</span>
    - <span style="color:pink">Viewers can request the printings of cards from the database, based on their Power allowance.</span>
    - <span style="color:pink">Viewers can suggest modifications to existent cards, keywords or decks.</span>

7. __Deckbuilder Support__: <span style="color:pink">Coming Soon<sup>TM</sup></span>
    - <span style="color:pink">Viewers can build decks using cards in their database, based on their Power allowance.</span>
    - <span style="color:pink">System offers an automated deck builder, that takes into account deck themes, card abilities, etc. and balances it against Power thresholds. </span>
  
8. __Backwards Compatibility__: Any field changes to the database structure will not break the database or query functionality, and will trigger reviews to the user to fill those fields for existing objects.


## 1.3 System Context

Within our system, we identified several essential, interdependent, internal components: 
- card management system – responsible for storing and managing all card-related data. Handles ingestion of .mse-set files, including parsing and extraction of individual card properties. System supports querying, updating, and version tracking of cards, ensuring consistency across modifications. Serves as the primary data source for both creators and external viewers through the user interface.
- keyword management system – maintains a unified repository of both official and custom keywords. Ensures consistency of keyword definitions across all cards by linking directly to the card data. System detects conflicts or modifications in keyword definitions and triggers review workflows when discrepancies arise.
- deck management system – organizes cards into structured collections representing decks or design groupings. Stores metadata such as deck themes and types, and maintains references to cards rather than duplicating data. System enables querying, updating, and exporting of decks into standardized formats.
- workflow & notification system – manages lifecycle events triggered by modifications to cards or keywords. Tracks dependencies between entities (e.g. cards within decks, keywords within cards) and generates notification tasks for required actions such as reprints. Maintains a stateful log of notices (unread, standby, issued, completed) and supports user interaction for progressing and annotating these workflows.
- user interface layer – provides an interactive frontend for both creators and external users. Supports file uploads, querying, visualization of cards/keywords/decks, and interaction with workflow notifications. Facilitates review processes by presenting differences between existing and modified data.
- <span style="color:pink">public access API – restricted-access interface intended for remote users. Exposes read-only querying capabilities for cards, keywords, and decks, as well as limited interaction features, such as requesting card printings or suggesting modifications. Enforces permission boundaries between creators and external users. </span>
- <span style="color:pink">deckbuilder & recommendation engine – higher-level system designed to assist users in constructing decks. Allows manual deck building under defined constraints (e.g., Power limits) and provides automated deck generation based on themes, card synergies, and balance considerations. </span>

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





