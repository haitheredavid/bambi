# Rebuild everything over MCP: exec(open('<session>/builders/build_all.py').read(), {'__name__': 'build_all'})
import bpy, os
from mathutils import Matrix

HERE = os.path.join(os.path.dirname(bpy.data.filepath), 'builders')  # needs the session's model.blend open
D, O = bpy.data, bpy.data.objects
bpy.context.window.scene = D.scenes['Scene']
D.scenes['Scene'].view_layers[0].layer_collection.children['Work2'].exclude = False
run = lambda f: exec(open(os.path.join(HERE, f)).read(), {'__name__': f[:-3]})
run('lib.py')
for n in ('HeadNew', 'head_body', 'CoreNew', 'LegFull', 'LegHalf'):
    if n in O:
        O.remove(O[n])
run('head.py'); run('core_leg.py'); run('install.py'); run('render.py')

# animation scene follows the assembly; shade smooth for renders (STL export ignores normals)
ha = O['Head_asm'].data.copy(); ha.transform(Matrix.Translation((0, 0, -136))); ha.name = 'Head_anim_v4'
O['Anim_Head'].data = ha; O['Anim_Core'].data = O['Core_asm'].data
for k in ('FL', 'FR', 'BL', 'BR'):
    O[f'Anim_Leg_{k}'].data = O[f'Leg_{k}_asm'].data
for n in ('Anim_Head', 'Anim_Core', 'Anim_Leg_FL', 'Anim_Leg_FR', 'Anim_Leg_BL', 'Anim_Leg_BR'):
    for s in O[n].material_slots:
        s.link = 'DATA'
for me in {O[n].data for n in ('Head_asm', 'Core_asm', 'Leg_FL_asm', 'Anim_Head')}:
    me.shade_smooth(); me.set_sharp_from_angle(angle=0.6)
b = O['Base_asm']; b.material_slots[0].link = 'OBJECT'; b.material_slots[0].material = D.materials['M_Base']
for me in list(D.meshes):
    if me.users == 0:
        D.meshes.remove(me)
g = bpy.app.driver_namespace['cz2']
sc = g['r_scene']()
g['r_link'](sc, ['Head_asm', 'Core_asm', 'Base_asm'] + [f'Leg_{k}_asm' for k in ('FL', 'FR', 'BL', 'BR')])
bpy.context.window.scene = D.scenes['Scene']
print('build_all ok')
