"""
Amarillo's Outfit Manager
A Blender addon for managing outfits and their associated shape keys
"""

import bpy  # type: ignore
import bmesh  # type: ignore
import math  # type: ignore
import mathutils  # type: ignore
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
    BoolVectorProperty,
)
from bpy.types import (
    Panel,
    Menu,
    Operator,
    PropertyGroup,
    UIList,
    Object,
    Collection,
)

bl_info = {
    "name": "Amarillo's Outfit Manager",
    "author": "Amarillo",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Amarillo",
    "description": "Manage outfits and their associated shape keys",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

# Data structures
class ShapeKeyEntry(PropertyGroup):
    name: StringProperty(name="Shape Key Name")
    value: FloatProperty(name="Value", default=0.0, min=0.0, max=1.0)
    model: PointerProperty(type=Object)  # Reference to which model this shape key belongs to

class NestedCollectionState(PropertyGroup):
    """Stores the state of a nested collection"""
    collection: PointerProperty(type=Collection)
    was_excluded: BoolProperty(default=True)

class OutfitEntry(PropertyGroup):
    name: StringProperty(name="Outfit Name")
    collection: PointerProperty(
        type=Collection,
        update=lambda self, context: setattr(self, 'name', self.collection.name if self.collection else self.name)
    )
    shape_keys: CollectionProperty(type=ShapeKeyEntry)
    active_shape_key_index: IntProperty()
    nested_states: CollectionProperty(type=NestedCollectionState)

class ManagedModelEntry(PropertyGroup):
    name: StringProperty(name="Model Name", options={'HIDDEN'})  # We'll use object's name directly
    object: PointerProperty(
        type=Object,
        # Don't update name when object changes - we only use object.name directly
    )

# Operators
class AMARILLO_OT_add_outfit(Operator):
    bl_idname = "amarillo.add_outfit"
    bl_label = "Add Outfit"
    bl_description = "Add a new outfit entry"
    
    def execute(self, context):
        outfits = context.scene.amarillo_outfits
        new_outfit = outfits.add()
        
        # Try to get collection from selection or active, even if disabled
        selected_collections = [obj for obj in context.selected_objects if obj.type == 'COLLECTION']
        if selected_collections:
            new_outfit.collection = selected_collections[0]
        elif context.collection:
            # Get the view layer collection that matches the active collection
            view_layer = context.view_layer
            layer_collection = view_layer.layer_collection
            
            def find_layer_collection(layer_coll, collection):
                if layer_coll.collection == collection:
                    return layer_coll
                for child in layer_coll.children:
                    result = find_layer_collection(child, collection)
                    if result:
                        return result
                return None
            
            layer_coll = find_layer_collection(layer_collection, context.collection)
            if layer_coll:
                new_outfit.collection = layer_coll.collection
            
        # Name will be automatically set by the collection update callback
        if not new_outfit.collection:
            new_outfit.name = f"Outfit {len(outfits)}"
            
        return {'FINISHED'}

class AMARILLO_OT_remove_outfit(Operator):
    bl_idname = "amarillo.remove_outfit"
    bl_label = "Remove Outfit"
    bl_description = "Remove the selected outfit entry"
    
    def execute(self, context):
        outfits = context.scene.amarillo_outfits
        outfit = outfits[context.scene.amarillo_active_outfit_index]
        
        # Clear shape key entries before removing outfit
        outfit.shape_keys.clear()
        
        context.scene.amarillo_active_outfit_index = max(0, context.scene.amarillo_active_outfit_index - 1)
        outfits.remove(context.scene.amarillo_active_outfit_index)
        return {'FINISHED'}

class AMARILLO_OT_add_managed_model(Operator):
    bl_idname = "amarillo.add_managed_model"
    bl_label = "Add Model"
    bl_description = "Add a new managed model"
    
    def execute(self, context):
        if context.active_object and context.active_object.type == 'MESH':
            models = context.scene.amarillo_managed_models
            
            # Check if model already exists
            for model in models:
                if model.object == context.active_object:
                    self.report({'WARNING'}, "Model already managed")
                    return {'CANCELLED'}
            
            new_model = models.add()
            new_model.object = context.active_object
            return {'FINISHED'}
        self.report({'WARNING'}, "Please select a mesh object")
        return {'CANCELLED'}

class AMARILLO_OT_remove_managed_model(Operator):
    bl_idname = "amarillo.remove_managed_model"
    bl_label = "Remove Model"
    bl_description = "Remove the selected managed model"
    
    def execute(self, context):
        models = context.scene.amarillo_managed_models
        active_index = context.scene.amarillo_active_model_index
        
        if active_index >= 0 and active_index < len(models):
            model = models[active_index]
            
            # Remove all shape key entries referencing this model from all outfits
            for outfit in context.scene.amarillo_outfits:
                # Create list of indices to remove
                to_remove = [i for i, sk in enumerate(outfit.shape_keys) if sk.model == model.object]
                # Remove from highest index to lowest to maintain index validity
                for i in reversed(to_remove):
                    outfit.shape_keys.remove(i)
                    if outfit.active_shape_key_index >= len(outfit.shape_keys):
                        outfit.active_shape_key_index = max(0, len(outfit.shape_keys) - 1)
            
            # Remove the model
            models.remove(active_index)
            context.scene.amarillo_active_model_index = max(0, active_index - 1)
            
            return {'FINISHED'}
        
        return {'CANCELLED'}

class AMARILLO_OT_add_shape_key(Operator):
    bl_idname = "amarillo.add_shape_key"
    bl_label = "Add Shape Key"
    bl_description = "Add a new shape key entry"
    
    def execute(self, context):
        outfit = context.scene.amarillo_outfits[context.scene.amarillo_active_outfit_index]
        if context.scene.amarillo_active_model_index >= 0:
            model = context.scene.amarillo_managed_models[context.scene.amarillo_active_model_index]
            if model.object and model.object.data.shape_keys:
                # Get active shape key name and value from the model
                active_key = model.object.active_shape_key
                if active_key and active_key.name != 'Basis':
                    new_shape_key = outfit.shape_keys.add()
                    new_shape_key.name = active_key.name
                    new_shape_key.value = active_key.value  # Copy the current value
                    new_shape_key.model = model.object
                    return {'FINISHED'}
                else:
                    self.report({'WARNING'}, "Please select a non-basis shape key")
                    return {'CANCELLED'}
        self.report({'WARNING'}, "Please select a model with shape keys")
        return {'CANCELLED'}

class AMARILLO_OT_remove_shape_key(Operator):
    bl_idname = "amarillo.remove_shape_key"
    bl_label = "Remove Shape Key"
    bl_description = "Remove the selected shape key entry"
    
    def execute(self, context):
        outfit = context.scene.amarillo_outfits[context.scene.amarillo_active_outfit_index]
        outfit.shape_keys.remove(outfit.active_shape_key_index)
        outfit.active_shape_key_index = max(0, outfit.active_shape_key_index - 1)
        return {'FINISHED'}

class AMARILLO_OT_move_outfit(Operator):
    bl_idname = "amarillo.move_outfit"
    bl_label = "Move Outfit"
    bl_description = "Move outfit up or down in the list"
    
    direction: EnumProperty(
        items=[
            ('UP', "Up", "Move outfit up"),
            ('DOWN', "Down", "Move outfit down")
        ]
    )
    
    def execute(self, context):
        outfits = context.scene.amarillo_outfits
        index = context.scene.amarillo_active_outfit_index
        
        if self.direction == 'UP' and index > 0:
            outfits.move(index, index - 1)
            context.scene.amarillo_active_outfit_index -= 1
        elif self.direction == 'DOWN' and index < len(outfits) - 1:
            outfits.move(index, index + 1)
            context.scene.amarillo_active_outfit_index += 1
            
        return {'FINISHED'}

class AMARILLO_OT_quick_activate_outfit(Operator):
    bl_idname = "amarillo.quick_activate_outfit"
    bl_label = "Quick Activate Outfit"
    bl_description = "Quickly activate this outfit"
    
    outfit_index: IntProperty()
    
    def reset_outfit_shape_keys(self, context, outfit):
        for shape_key_entry in outfit.shape_keys:
            if shape_key_entry.model and shape_key_entry.model.data.shape_keys:
                key_block = shape_key_entry.model.data.shape_keys.key_blocks.get(shape_key_entry.name)
                if key_block:
                    key_block.value = 0.0

    def find_layer_collection(self, layer_collection, collection):
        if layer_collection.collection == collection:
            return layer_collection
        for child in layer_collection.children:
            found = self.find_layer_collection(child, collection)
            if found:
                return found
        return None

    def get_all_nested_collections(self, collection):
        """Get all nested collections recursively"""
        result = []
        for child in collection.children:
            result.append(child)
            result.extend(self.get_all_nested_collections(child))
        return result

    def store_nested_states(self, context, outfit):
        """Store the current state of all nested collections"""
        if not outfit.collection:
            return

        # Clear previous states
        outfit.nested_states.clear()
        
        # Get all nested collections
        nested_colls = self.get_all_nested_collections(outfit.collection)
        
        # Store their states
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        for coll in nested_colls:
            layer_coll = self.find_layer_collection(layer_collection, coll)
            if layer_coll:
                state = outfit.nested_states.add()
                state.collection = coll
                state.was_excluded = layer_coll.exclude

    def restore_nested_states(self, context, outfit):
        """Restore the saved states of nested collections"""
        if not outfit.collection:
            return
            
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        for state in outfit.nested_states:
            if state.collection:
                layer_coll = self.find_layer_collection(layer_collection, state.collection)
                if layer_coll:
                    layer_coll.exclude = state.was_excluded
    
    def execute(self, context):
        outfits = context.scene.amarillo_outfits
        if self.outfit_index >= len(outfits):
            return {'CANCELLED'}
        
        # Get current and target outfits
        current_index = context.scene.amarillo_active_outfit_index
        current_outfit = outfits[current_index] if current_index < len(outfits) else None
        target_outfit = outfits[self.outfit_index]
        
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        # Store states and reset shape keys of current outfit
        if current_outfit:
            self.store_nested_states(context, current_outfit)
            self.reset_outfit_shape_keys(context, current_outfit)
        
        # Disable all outfit collections
        for outfit in outfits:
            if outfit.collection:
                layer_coll = self.find_layer_collection(layer_collection, outfit.collection)
                if layer_coll:
                    layer_coll.exclude = True
        
        # Enable target outfit's collection and restore nested states
        if target_outfit.collection:
            layer_coll = self.find_layer_collection(layer_collection, target_outfit.collection)
            if layer_coll:
                layer_coll.exclude = False
                self.restore_nested_states(context, target_outfit)
        
        # Apply shape key values for target outfit
        for shape_key_entry in target_outfit.shape_keys:
            if shape_key_entry.model and shape_key_entry.model.data.shape_keys:
                key_block = shape_key_entry.model.data.shape_keys.key_blocks.get(shape_key_entry.name)
                if key_block:
                    key_block.value = shape_key_entry.value
        
        # Update active index
        context.scene.amarillo_active_outfit_index = self.outfit_index
        return {'FINISHED'}

class AMARILLO_OT_activate_outfit(Operator):
    bl_idname = "amarillo.activate_outfit"
    bl_label = "Activate Outfit"
    bl_description = "Activate the selected outfit and apply shape key values"

    def reset_outfit_shape_keys(self, context, outfit):
        for shape_key_entry in outfit.shape_keys:
            if shape_key_entry.model and shape_key_entry.model.data.shape_keys:
                key_block = shape_key_entry.model.data.shape_keys.key_blocks.get(shape_key_entry.name)
                if key_block:
                    key_block.value = 0.0

    def find_layer_collection(self, layer_collection, collection):
        if layer_collection.collection == collection:
            return layer_collection
        for child in layer_collection.children:
            found = self.find_layer_collection(child, collection)
            if found:
                return found
        return None

    def get_all_nested_collections(self, collection):
        """Get all nested collections recursively"""
        result = []
        for child in collection.children:
            result.append(child)
            result.extend(self.get_all_nested_collections(child))
        return result

    def store_nested_states(self, context, outfit):
        """Store the current state of all nested collections"""
        if not outfit.collection:
            return

        # Clear previous states
        outfit.nested_states.clear()
        
        # Get all nested collections
        nested_colls = self.get_all_nested_collections(outfit.collection)
        
        # Store their states
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        for coll in nested_colls:
            layer_coll = self.find_layer_collection(layer_collection, coll)
            if layer_coll:
                state = outfit.nested_states.add()
                state.collection = coll
                state.was_excluded = layer_coll.exclude

    def restore_nested_states(self, context, outfit):
        """Restore the saved states of nested collections"""
        if not outfit.collection:
            return
            
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        for state in outfit.nested_states:
            if state.collection:
                layer_coll = self.find_layer_collection(layer_collection, state.collection)
                if layer_coll:
                    layer_coll.exclude = state.was_excluded

    def execute(self, context):
        outfits = context.scene.amarillo_outfits
        active_index = context.scene.amarillo_active_outfit_index
        current_outfit = outfits[active_index]
        
        view_layer = context.view_layer
        layer_collection = view_layer.layer_collection
        
        # Store states and reset shape keys of current outfit
        self.store_nested_states(context, current_outfit)
        self.reset_outfit_shape_keys(context, current_outfit)
        
        # Disable all outfit collections
        for outfit in outfits:
            if outfit.collection:
                layer_coll = self.find_layer_collection(layer_collection, outfit.collection)
                if layer_coll:
                    layer_coll.exclude = True
        
        # Enable the selected outfit's collection and restore nested states
        if current_outfit.collection:
            layer_coll = self.find_layer_collection(layer_collection, current_outfit.collection)
            if layer_coll:
                layer_coll.exclude = False
                self.restore_nested_states(context, current_outfit)
        
        # Apply shape key values
        for shape_key_entry in current_outfit.shape_keys:
            if shape_key_entry.model and shape_key_entry.model.data.shape_keys:
                key_block = shape_key_entry.model.data.shape_keys.key_blocks.get(shape_key_entry.name)
                if key_block:
                    key_block.value = shape_key_entry.value
        
        return {'FINISHED'}

# UI Lists
class AMARILLO_UL_outfits(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            
            # Quick load button - fix the index lookup
            op = row.operator("amarillo.quick_activate_outfit", text="", icon='PLAY', emboss=False)
            op.outfit_index = context.scene.amarillo_outfits.find(item.name)  # Fixed: use context.scene.amarillo_outfits
            
            # Name and collection
            sub = row.row()
            sub.prop(item, "name", text="", emboss=False)
            if item.collection:
                sub.label(text=item.collection.name)
            else:
                sub.label(text="No Collection Assigned")

class AMARILLO_UL_managed_models(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            if item.object:
                # Just display the object's name, don't allow editing
                row.label(text=item.object.name)
            else:
                row.label(text="Missing Object")

class AMARILLO_UL_shape_keys(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            if item.model:
                row.label(text=item.model.name + ":")
            row.prop(item, "name", text="", emboss=False)
            row.prop(item, "value", text="Value")

# Panel
class AMARILLO_PT_outfit_manager(Panel):
    bl_label = "Amarillo's Outfit Manager"
    bl_idname = "AMARILLO_PT_outfit_manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Amarillo'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Outfit list
        layout.label(text="Outfits:")
        row = layout.row()
        row.template_list("AMARILLO_UL_outfits", "", scene, "amarillo_outfits",
                         scene, "amarillo_active_outfit_index")
        
        col = row.column(align=True)
        col.operator("amarillo.add_outfit", icon='ADD', text="")
        col.operator("amarillo.remove_outfit", icon='REMOVE', text="")
        col.separator()
        col.operator("amarillo.move_outfit", icon='TRIA_UP', text="").direction = 'UP'
        col.operator("amarillo.move_outfit", icon='TRIA_DOWN', text="").direction = 'DOWN'
        
        if len(scene.amarillo_outfits) > 0:
            outfit = scene.amarillo_outfits[scene.amarillo_active_outfit_index]
            
            # Collection assignment
            layout.prop(outfit, "collection", text="Collection")
            
            # Shape keys list
            layout.label(text="Shape Keys:")
            row = layout.row()
            row.template_list("AMARILLO_UL_shape_keys", "", outfit, "shape_keys",
                            outfit, "active_shape_key_index")
            
            col = row.column(align=True)
            col.operator("amarillo.add_shape_key", icon='ADD', text="")
            col.operator("amarillo.remove_shape_key", icon='REMOVE', text="")
        
        layout.separator()
        
        # Managed Models list (smaller, at bottom)
        box = layout.box()
        row = box.row()
        row.label(text="Managed Models:")
        
        # Split into two rows to control scaling independently
        list_row = box.row()
        list_row.scale_y = 0.75  # Only scale the list
        list_row.template_list("AMARILLO_UL_managed_models", "", scene, "amarillo_managed_models",
                             scene, "amarillo_active_model_index", rows=2)
        
        # Button column at regular size
        button_col = list_row.column(align=True)
        button_col.operator("amarillo.add_managed_model", icon='ADD', text="")
        button_col.operator("amarillo.remove_managed_model", icon='REMOVE', text="")

# Registration
classes = (
    ShapeKeyEntry,
    NestedCollectionState,
    ManagedModelEntry,
    OutfitEntry,
    AMARILLO_OT_add_outfit,
    AMARILLO_OT_remove_outfit,
    AMARILLO_OT_add_managed_model,
    AMARILLO_OT_remove_managed_model,
    AMARILLO_OT_add_shape_key,
    AMARILLO_OT_remove_shape_key,
    AMARILLO_OT_activate_outfit,
    AMARILLO_OT_quick_activate_outfit,
    AMARILLO_OT_move_outfit,
    AMARILLO_UL_outfits,
    AMARILLO_UL_managed_models,
    AMARILLO_UL_shape_keys,
    AMARILLO_PT_outfit_manager,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.amarillo_outfits = CollectionProperty(type=OutfitEntry)
    bpy.types.Scene.amarillo_active_outfit_index = IntProperty()
    bpy.types.Scene.amarillo_managed_models = CollectionProperty(type=ManagedModelEntry)
    bpy.types.Scene.amarillo_active_model_index = IntProperty()

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.amarillo_outfits
    del bpy.types.Scene.amarillo_active_outfit_index
    del bpy.types.Scene.amarillo_managed_models
    del bpy.types.Scene.amarillo_active_model_index

if __name__ == "__main__":
    register() 
