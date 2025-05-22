# Amarillo's Outfit Manager

What is this?
=============
A helper addon that makes switching between "outfits" easier. This is made for my Patreon supporters as a convenient way to change my characters' outfits.

What exactly does this do?
==========================
It lets you create a simple database of outfits. An "outfit" is a container of the following data:
* One collection (the same ones you create in the Outliner).
* A list of Shape Keys, their values and the object they belong to

When you switch to an outfit using this addon, the following will happen:
* The collections for every other outfit will be disabled
* The shape keys defined inside each outfit will default back to 0
* The collection for the selected outfit will be enabled
* The shape keys defined insdie the selected outfit will have their values assigned to whatever you defined

When is this behavior useful?
=============================
It is useful is you have one character with many outfits organized each in their own collection. And also is each outfit has Shape Keys that should be enabled/disabled to accomodate the body of the charater to it.

Usage instructions
==================
1) Select a collection in the outliner
2) Press the + button in the Outfits list
3) In case you have shape keys you need to manage, select the object with the shape keys and press the + button in the Managed Models list
4) When selecting an outfit, select the shape key of which the value you want to register in the outfit along with Managed Model that contains the shape key, then press the + button on the Shape Keys list
5) Repeat the previous step for each shape key you want to register as part of that outfit
