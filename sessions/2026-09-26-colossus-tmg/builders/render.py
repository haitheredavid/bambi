# Render scene: Protoss palette (gold armour, dark khaydarin-purple body, gunmetal trim, blue glow), studio lights, 3 cameras.
import bpy, math
from mathutils import Vector

PAL = {  # base colour, metallic, roughness, emission strength
    'M_Armor': ((0.83, 0.58, 0.22, 1), 1.0, 0.32, 0),
    'M_Body': ((0.06, 0.05, 0.085, 1), 0.3, 0.5, 0),
    'M_Metal': ((0.30, 0.31, 0.34, 1), 1.0, 0.45, 0),
    'M_Glow': ((0.10, 0.50, 1.00, 1), 0.0, 0.40, 4.0),
    'M_Base': ((0.12, 0.11, 0.10, 1), 0.0, 0.85, 0),
}


def shade(name):
    col, met, rough, em = PAL[name]
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = col; bsdf.inputs['Metallic'].default_value = met
    bsdf.inputs['Roughness'].default_value = rough
    if em:
        bsdf.inputs['Emission Color'].default_value = col; bsdf.inputs['Emission Strength'].default_value = em
    m.diffuse_color = col
    return m


def scene():
    sc = bpy.data.scenes.get('Render') or bpy.data.scenes.new('Render')
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 0.001
    try:
        sc.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 1200, 1500
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'; sc.view_settings.exposure = -0.8
    w = sc.world or bpy.data.worlds.new('RenderWorld'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.035, 0.04, 0.05, 1); bg.inputs['Strength'].default_value = 1.0
    for n in PAL:
        shade(n)

    def obj(name, data):
        o = bpy.data.objects.get(name) or bpy.data.objects.new(name, data)
        if o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
        return o
    # lights: key warm, rim cool, fill
    for name, loc, energy, col, size in (('Key', (300, -60, 330), 4.0e6, (1, .93, .85), 120),
                                         ('Rim', (-280, 180, 260), 5.0e6, (.6, .75, 1), 80),
                                         ('Fill', (60, 320, 90), 0.9e6, (1, 1, 1), 200)):
        L = bpy.data.lights.get(name) or bpy.data.lights.new(name, 'AREA')
        L.energy, L.color, L.size = energy, col, size
        o = obj(name, L); o.location = loc
        o.rotation_euler = (Vector((0, 0, 85)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    # floor
    if 'Floor' not in bpy.data.objects:
        import bmesh
        me = bpy.data.meshes.new('Floor'); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1000)
        bm.to_mesh(me); bm.free(); f = bpy.data.objects.new('Floor', me)
        fm = bpy.data.materials.get('M_Floor') or bpy.data.materials.new('M_Floor'); fm.use_nodes = True
        b = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b.inputs['Base Color'].default_value = (0.05, 0.055, 0.065, 1); b.inputs['Roughness'].default_value = 0.6
        me.materials.append(fm)
    obj('Floor', bpy.data.objects['Floor'].data).location = (0, 0, -0.05)
    cam_d = bpy.data.cameras.get('RenderCam') or bpy.data.cameras.new('RenderCam'); cam_d.lens = 85
    cam = obj('RenderCam', cam_d); sc.camera = cam
    return sc


def aim(sc, az_deg, el_deg, dist, target=(0, 0, 88), lens=85):
    cam = sc.camera; cam.data.lens = lens; t = Vector(target); a, e = math.radians(az_deg), math.radians(el_deg)
    cam.location = t + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()


def shoot(sc, path, az, el, dist, target=(0, 0, 88), lens=85, res=(1200, 1500)):
    aim(sc, az, el, dist, target, lens); sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path; sc.render.image_settings.file_format = 'PNG'
    win = bpy.context.window; prev = win.scene
    bpy.ops.render.render(write_still=True, scene=sc.name)
    win.scene = prev


def link_only(sc, names):
    """show exactly these objects (plus lights/cam/floor) in the render scene."""
    keep = set(names) | {'Key', 'Rim', 'Fill', 'Floor', 'RenderCam'}
    for o in list(sc.collection.objects):
        if o.name not in keep:
            sc.collection.objects.unlink(o)
    for n in names:
        if n not in sc.collection.objects:
            sc.collection.objects.link(bpy.data.objects[n])


bpy.app.driver_namespace['cz2'].update(r_scene=scene, r_shoot=shoot, r_link=link_only, r_shade=shade)
print('render ok')
