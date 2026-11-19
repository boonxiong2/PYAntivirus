"""
PYAV Keyboard Generator — Blender Python script
⚠️  RUN IN A NEW FILE (File → New → General) — THIS DELETES THE ENTIRE SCENE
"""
import bpy, math

# Warn user and get confirmation
def draw_confirm(self, context):
    self.layout.label(text="This will DELETE the current scene and create a keyboard!")
    self.layout.label(text="Run in a NEW file (File → New → General) to keep your work.")

bpy.context.window_manager.popup_menu(draw_confirm, title="PYAV Keyboard Generator", icon='ERROR')

# Clean scene
try:
    bpy.ops.object.mode_set(mode='OBJECT')
except: pass
try:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
except: pass

# Dimensions (in Blender units, 1 unit ≈ 1m)
KEY_W  = 0.038  # key width (~38mm)
KEY_H  = 0.038  # key height
KEY_GAP = 0.006 # gap between keys
BASE_H = 0.010  # base plate height
KEY_CAP_H = 0.016 # key cap height

COLS = 15
ROWS = 5
KEY_DEPTH = KEY_H

# Base plate
bpy.ops.mesh.primitive_cube_add(size=1)
base = bpy.context.active_object
base.name = "Base"
base.location = (
    COLS * (KEY_W + KEY_GAP) / 2 - KEY_GAP/2,
    ROWS * (KEY_H + KEY_GAP) / 2 - KEY_GAP/2,
    BASE_H/2
)
base.scale = (
    COLS * (KEY_W + KEY_GAP) / 2,
    ROWS * (KEY_H + KEY_GAP) / 2,
    BASE_H/2
)
mat_base = bpy.data.materials.new("BaseMat")
mat_base.diffuse_color = (0.05, 0.05, 0.05, 1)
base.data.materials.append(mat_base)

# Key caps
mat_key = bpy.data.materials.new("KeyMat")
mat_key.diffuse_color = (0.15, 0.15, 0.15, 1)

for row in range(ROWS):
    cols_this_row = COLS
    # Standard row offsets
    if row == 0:   cols_this_row = COLS  # number row
    elif row == 4: cols_this_row = COLS - 1  # spacebar row (short)

    for col in range(cols_this_row):
        x = col * (KEY_W + KEY_GAP) + KEY_W/2
        # Row stagger
        y = row * (KEY_H + KEY_GAP) + KEY_H/2
        if row == 0: x += KEY_W * 0.25
        if row == 4: x += KEY_W * 0.75  # spacebar offset
        
        z = BASE_H + KEY_CAP_H/2
        
        bpy.ops.mesh.primitive_cube_add(size=1)
        cap = bpy.context.active_object
        cap.name = f"Key_R{row}C{col}"
        cap.location = (x, y, z)
        cap.scale = (KEY_W/2 * 0.9, KEY_H/2 * 0.9, KEY_CAP_H/2)
        cap.data.materials.append(mat_key)
        
        # Bevel for nicer look
        bpy.ops.object.modifier_add(type='BEVEL')
        if cap.modifiers:
            cap.modifiers[-1].width = 0.001
            cap.modifiers[-1].segments = 2

# Merge all keys for easy export
key_objs = [obj for obj in bpy.data.objects if obj.name.startswith("Key_")]
if key_objs and len(key_objs) > 1:
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in key_objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = key_objs[0]
    bpy.ops.object.join()

# Camera
bpy.ops.object.camera_add(location=(0.5, -0.4, 0.3))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(60), 0, math.radians(45))

bpy.context.scene.camera = cam

print("=== PYAV Keyboard generated! ===")
print("File -> Export -> FBX or OBJ")
