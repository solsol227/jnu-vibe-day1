"""
제주도 DEM + 물결치는 바다 + 이동하는 태양 (Blender 4.x / 5.x, Cycles)

실행 방법
  1) Blender > Scripting 탭 > Open 으로 이 파일을 열고 ▶ Run Script
  2) 또는 터미널에서
       blender -b -P jeju_ocean_sun.py -- --render-frame 120 --out C:/tmp/jeju.png
       blender -b -P jeju_ocean_sun.py -- --save C:/tmp/jeju.blend

구성
  - 지형 : 높이 지도(DEM)를 격자 메쉬로 변환. HEIGHTMAP_PATH 가 비어 있으면
           한라산 모양의 가짜 섬을 대신 만들어 줍니다(DEM 없이도 실행 가능).
  - 바다 : Ocean 모디파이어(실제 파도 시뮬레이션) 조각 + 수평선까지 이어지는 넓은 평면
  - 하늘 : Sky Texture(대기 산란). 태양 원판이 하늘에 떠 있고, 프레임마다 위치가 바뀜
  - 반사 : 바다 재질이 하늘/태양을 반사하므로 태양 아래로 반짝이는 빛길이 생김

DEM 준비 (HEIGHTMAP_PATH 또는 --dem 옵션)
  - 제주도 범위(대략 동경 126.15~126.97, 북위 33.11~33.57)를 잘라낸 DEM을
    이미지로 저장하세요. 이미지의 위쪽이 북쪽이어야 합니다.
      · 실수(float) 이미지(EXR 등)  : 값이 곧 미터 단위 고도 -> 그대로 사용
      · 8/16비트 이미지(PNG 등)     : 0~1로 정규화된 값 x MAX_ELEVATION(1947 m) 을 고도로 사용
  - 주의: SRTM 같은 Int16 GeoTIFF(원본이 미터 값)를 그대로 넣으면 고도가 틀려집니다.
    GDAL 로 먼저 16비트 PNG 로 바꾸세요. (0 m -> 0, 1947 m -> 65535)
        gdal_translate -of PNG -ot UInt16 -scale 0 1947 0 65535 jeju.tif jeju16.png
  - 해수면은 0 m 입니다. 1 m 미만(바다, nodata=0)은 바다로 취급해 바닥으로 내립니다.
  - DEM 출처 예: 국토지리정보원 수치표고모델, USGS EarthExplorer(SRTM),
    OpenTopography, Blender 애드온 BlenderGIS.

단위: 1 Blender 단위 = 1 m. 방위각은 북쪽 0도에서 시계방향(동 90, 남 180, 서 270).
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

# ======================================================================
# 설정
# ======================================================================
HEIGHTMAP_PATH = ""            # 예: r"C:\data\jeju_dem.tif"  (비우면 가짜 섬 생성)
TERRAIN_SIZE_X = 76000.0       # DEM이 덮는 동서 길이(m)
TERRAIN_SIZE_Y = 51000.0       # DEM이 덮는 남북 길이(m)
MAX_ELEVATION = 1947.0         # 정규화 이미지일 때 흰색(1.0)이 뜻하는 고도(m), 한라산
VERTICAL_EXAGGERATION = 1.0    # 높이 과장 배율
TERRAIN_RES = 700              # 지형 격자 수(한 변). 클수록 정밀/무거움
SEABED_DEPTH = 40.0            # 바다 밑바닥 깊이(m)

# --- 카메라: 섬 남쪽 해안에서 남쪽 바다를 바라봄 (한낮 태양은 남쪽 하늘) ---
CAM_X = 0.0                    # 카메라 동서 위치(m, 섬 중심 기준)
CAM_INLAND = 800.0             # 남쪽 해안선에서 섬 안쪽으로 떨어진 거리(m). 음수면 바다 쪽
CAM_HEIGHT_ABOVE_GROUND = 250.0
CAM_BEARING = 190.0            # 바라보는 방향(남남서)
CAM_PITCH = -2.0               # 위로 들어올린 각도(도). 음수면 아래를 봄
CAM_LENS = 20.0                # 초점거리(mm), 넓을수록 태양 이동 경로가 한 화면에 담김

# --- 태양: 동남쪽에서 떠서 서남쪽으로 지는 호(arc) ---
SUN_AZIMUTH_START = 152.0
SUN_AZIMUTH_END = 228.0
SUN_ELEVATION_MIN = 7.0        # 시작/끝의 낮은 고도(도)
SUN_ELEVATION_PEAK = 20.0      # 가운데 시점의 최고 고도(도)
SUN_DISC_SIZE_DEG = 1.0        # 하늘의 태양 원판 크기(실제는 약 0.53도)

# --- 바다 ---
OCEAN_TILE_SIZE = 160.0        # 파도 시뮬레이션 한 타일의 크기(m)
OCEAN_RESOLUTION = 8           # 렌더 해상도(타일 한 변 = 값의 제곱 칸, 8이면 64칸 ≈ 2.5 m)
OCEAN_VIEWPORT_RESOLUTION = 4  # 작업 화면(뷰포트)용 해상도
OCEAN_REPEAT_X = 20            # 타일을 동서로 반복(전체 폭 = 20 x 160 m = 3.2 km)
OCEAN_REPEAT_Y = 18            # 남북 반복(2.88 km). 늘리면 무거워짐
OCEAN_MID_TILE = 640.0         # 중간 거리 파도(성긴 격자): 타일 크기(m)
OCEAN_MID_RESOLUTION = 7       # 49칸 ≈ 13 m
OCEAN_MID_REPEAT = 12          # 12 x 640 m = 7.7 km 정사각형
WIND_VELOCITY = 12.0           # 풍속(m/s): 클수록 큰 파도
WAVE_SCALE = 1.2               # 파도 높이 배율
CHOPPINESS = 1.6               # 뾰족한 정도
WAVE_SPEED = 1.0               # 파도 진행 속도 배율

# --- 애니메이션 / 렌더 ---
FRAME_START = 1
FRAME_END = 240                # 24fps 기준 10초
FPS = 24
RESOLUTION = (1280, 720)
SAMPLES = 96
EXPOSURE = -3.0                # 밝기 보정. 너무 밝으면 더 낮추고(-4), 어두우면 올리세요(-2)
OUTPUT_DIR = "//render/"       # 애니메이션 렌더 결과 폴더(.blend 기준)

SEED = 7


# ======================================================================
# 유틸
# ======================================================================
def sun_vector(azimuth_deg, elevation_deg):
    """방위각(북 0도, 시계방향)과 고도에서 '태양이 있는 방향' 단위벡터."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


def sun_at(t):
    """t(0~1) 시점의 (방위각, 고도). 방위각은 선형, 고도는 사인 곡선으로 호를 그림."""
    az = SUN_AZIMUTH_START + (SUN_AZIMUTH_END - SUN_AZIMUTH_START) * t
    el = SUN_ELEVATION_MIN + (SUN_ELEVATION_PEAK - SUN_ELEVATION_MIN) * math.sin(math.pi * t)
    return az, el


def set_input(node, names, value):
    """버전마다 다른 소켓 이름을 차례로 시도해 값을 넣는다."""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def box_blur(a, r):
    """numpy만으로 만든 박스 블러(경계는 가장자리 값으로 확장)."""
    k = 2 * r + 1
    out = a
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r + 1, r)
        p = np.pad(out, pad, mode='edge')
        c = np.cumsum(p, axis=axis)
        hi = np.take(c, np.arange(k, c.shape[axis]), axis=axis)
        lo = np.take(c, np.arange(0, c.shape[axis] - k), axis=axis)
        out = (hi - lo) / k
    return out


def resample(a, ny, nx):
    """2차원 배열을 쌍선형 보간으로 (ny, nx) 크기로 만든다."""
    h, w = a.shape
    yi = np.linspace(0, h - 1, ny)
    xi = np.linspace(0, w - 1, nx)
    y0 = np.floor(yi).astype(int)
    x0 = np.floor(xi).astype(int)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    fy = (yi - y0)[:, None]
    fx = (xi - x0)[None, :]
    return (a[y0][:, x0] * (1 - fx) * (1 - fy) + a[y0][:, x1] * fx * (1 - fy)
            + a[y1][:, x0] * (1 - fx) * fy + a[y1][:, x1] * fx * fy)


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(coll):
            if item.users == 0:
                coll.remove(item)


# ======================================================================
# 1. 높이 지도(DEM)
# ======================================================================
def load_dem(path, ny, nx):
    """DEM 이미지를 읽어 미터 단위 고도 배열 (ny, nx) 로 돌려준다. 위쪽=북쪽."""
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = 'Non-Color'
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    a = px.reshape(h, w, 4)[:, :, 0]          # Blender 이미지는 0번 행이 '아래(남쪽)'
    is_float = bool(img.is_float)
    bpy.data.images.remove(img)

    if is_float and float(a.max()) > 2.0:
        meters = a.astype(np.float64)            # 이미 미터 단위
        print(f"[DEM] float 고도 사용 (최소 {meters.min():.0f} m ~ 최대 {meters.max():.0f} m)")
    else:
        meters = a.astype(np.float64) * MAX_ELEVATION
        print(f"[DEM] 정규화 이미지 x {MAX_ELEVATION:.0f} m 사용")
    return resample(meters, ny, nx)


def make_procedural_dem(ny, nx, seed=SEED):
    """DEM이 없을 때 쓰는 한라산 모양 섬(동서로 긴 타원 + 중앙 화산 + 기생화산 오름)."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(-1, 1, nx)
    ys = np.linspace(-1, 1, ny)
    X, Y = np.meshgrid(xs, ys)

    ax, ay = 0.80, 0.55
    ang = np.arctan2(Y / ay, X / ax)
    wobble = 1 + 0.06 * np.sin(3 * ang + 1.3) + 0.04 * np.sin(5 * ang + 0.4) + 0.03 * np.sin(9 * ang + 2.1)
    d = np.sqrt((X / ax) ** 2 + (Y / ay) ** 2) / wobble
    land = np.clip(1 - d, 0, None)

    shield = 520.0 * land ** 0.85
    r = np.sqrt((X / 0.28) ** 2 + (Y / 0.20) ** 2)
    cone = 1500.0 * np.clip(1 - r, 0, None) ** 1.5
    crater = 90.0 * np.exp(-(np.sqrt(X ** 2 + Y ** 2) / 0.02) ** 2)

    cones = np.zeros_like(X)
    for _ in range(70):                           # 기생화산(오름)
        while True:
            cx, cy = rng.uniform(-0.75, 0.75), rng.uniform(-0.5, 0.5)
            if (cx / ax) ** 2 + (cy / ay) ** 2 < 0.8:
                break
        rad = rng.uniform(0.008, 0.018)
        cones += rng.uniform(60, 190) * np.exp(-(((X - cx) ** 2 + (Y - cy) ** 2) / rad ** 2))

    noise = np.zeros_like(X)
    for octave in range(6):
        f = 2.0 ** (octave + 2)
        noise += (35.0 / 1.9 ** octave) * np.sin(f * np.pi * X + rng.uniform(0, 6.3)) * \
            np.sin(f * np.pi * Y + rng.uniform(0, 6.3))

    mask = np.clip(land * 8, 0, 1)
    h = shield + cone - crater + cones + noise * mask
    h[d >= 1.0] = 0.0
    print("[DEM] 파일이 없어 한라산 모양의 가짜 섬을 생성했습니다.")
    return np.clip(h, 0, None)


def prepare_heights(ny, nx):
    if HEIGHTMAP_PATH and os.path.isfile(bpy.path.abspath(HEIGHTMAP_PATH)):
        h = load_dem(bpy.path.abspath(HEIGHTMAP_PATH), ny, nx)
    else:
        if HEIGHTMAP_PATH:
            print(f"[DEM] 파일을 찾을 수 없어 가짜 섬을 사용합니다: {HEIGHTMAP_PATH}")
        h = make_procedural_dem(ny, nx)

    land = h >= 1.0                                # 1 m 미만은 바다로 취급(해수면 0 m)
    soft = box_blur(land.astype(np.float64), max(2, nx // 120))
    soft = box_blur(soft, max(2, nx // 120))
    seabed = -SEABED_DEPTH * (1.0 - soft) - 3.0    # 해안에서 서서히 깊어지는 바닥
    h = np.where(land, h, seabed)
    return h * VERTICAL_EXAGGERATION, land


# ======================================================================
# 2. 지형 메쉬 + 재질
# ======================================================================
def build_terrain(heights):
    ny, nx = heights.shape
    xs = np.linspace(-TERRAIN_SIZE_X / 2, TERRAIN_SIZE_X / 2, nx)
    ys = np.linspace(-TERRAIN_SIZE_Y / 2, TERRAIN_SIZE_Y / 2, ny)
    X, Y = np.meshgrid(xs, ys)
    verts = np.stack([X, Y, heights], axis=-1).reshape(-1, 3)

    idx = np.arange(ny * nx).reshape(ny, nx)
    v0 = idx[:-1, :-1].ravel()
    faces = np.stack([v0, v0 + 1, v0 + nx + 1, v0 + nx], axis=1)   # 위에서 볼 때 반시계

    me = bpy.data.meshes.new("JejuTerrain")
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.update()
    try:
        me.shade_smooth()
    except Exception:
        for p in me.polygons:
            p.use_smooth = True

    ob = bpy.data.objects.new("JejuTerrain", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(make_terrain_material())
    return ob


def make_terrain_material():
    mat = bpy.data.materials.new("JejuTerrainMat")
    nt = mat.node_tree
    if nt is None:
        mat.use_nodes = True
        nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    rng = nt.nodes.new('ShaderNodeMapRange')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    noise = nt.nodes.new('ShaderNodeTexNoise')
    mix = nt.nodes.new('ShaderNodeMix')

    top = max(MAX_ELEVATION * VERTICAL_EXAGGERATION, 1.0)
    rng.inputs['From Min'].default_value = 0.0
    rng.inputs['From Max'].default_value = top
    rng.clamp = True

    stops = [(0.000, (0.45, 0.38, 0.24, 1)),   # 모래/해안
             (0.012, (0.05, 0.11, 0.03, 1)),   # 진한 초록(숲)
             (0.300, (0.07, 0.17, 0.04, 1)),   # 초록
             (0.560, (0.17, 0.14, 0.08, 1)),   # 갈색(억새/풀밭)
             (0.800, (0.13, 0.12, 0.11, 1)),   # 현무암
             (1.000, (0.30, 0.28, 0.27, 1))]
    ramp.color_ramp.elements[0].position = stops[0][0]
    ramp.color_ramp.elements[0].color = stops[0][1]
    ramp.color_ramp.elements[1].position = stops[-1][0]
    ramp.color_ramp.elements[1].color = stops[-1][1]
    for pos, col in stops[1:-1]:
        e = ramp.color_ramp.elements.new(pos)
        e.color = col

    noise.inputs['Scale'].default_value = 0.004
    noise.inputs['Detail'].default_value = 6.0
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 0.55

    nt.links.new(geo.outputs['Position'], sep.inputs['Vector'])
    nt.links.new(geo.outputs['Position'], noise.inputs['Vector'])
    nt.links.new(sep.outputs['Z'], rng.inputs['Value'])
    nt.links.new(rng.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], mix.inputs['A'])
    nt.links.new(noise.outputs['Color'], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.92
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


# ======================================================================
# 3. 바다
# ======================================================================
def make_ocean_material(name="OceanMat", swell=False):
    """swell=True 는 먼 바다용: 진짜 파도 대신 큰 너울 무늬를 노멀로 흉내 낸다."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    if nt is None:
        mat.use_nodes = True
        nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    mapping = nt.nodes.new('ShaderNodeMapping')
    mapping.name = "RippleDrift"
    n1 = nt.nodes.new('ShaderNodeTexNoise')
    n2 = nt.nodes.new('ShaderNodeTexNoise')
    add = nt.nodes.new('ShaderNodeMath')
    bump = nt.nodes.new('ShaderNodeBump')

    # 작은 잔물결: 월드 좌표 기준이라 가까운 파도 조각과 먼 바다가 이어져 보임
    nt.links.new(geo.outputs['Position'], mapping.inputs['Vector'])
    nt.links.new(mapping.outputs['Vector'], n1.inputs['Vector'])
    nt.links.new(mapping.outputs['Vector'], n2.inputs['Vector'])
    n1.inputs['Scale'].default_value = 0.22
    n1.inputs['Detail'].default_value = 3.0
    n2.inputs['Scale'].default_value = 0.9
    n2.inputs['Detail'].default_value = 2.0
    add.operation = 'ADD'
    nt.links.new(n1.outputs['Fac'], add.inputs[0])
    nt.links.new(n2.outputs['Fac'], add.inputs[1])
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.6
    height_out = add.outputs['Value']
    if swell:
        n3 = nt.nodes.new('ShaderNodeTexNoise')
        n3.inputs['Scale'].default_value = 0.04
        n3.inputs['Detail'].default_value = 2.0
        nt.links.new(mapping.outputs['Vector'], n3.inputs['Vector'])
        big = nt.nodes.new('ShaderNodeMath')
        big.operation = 'MULTIPLY'
        big.inputs[1].default_value = 12.0
        nt.links.new(n3.outputs['Fac'], big.inputs[0])
        total = nt.nodes.new('ShaderNodeMath')
        total.operation = 'ADD'
        nt.links.new(add.outputs['Value'], total.inputs[0])
        nt.links.new(big.outputs['Value'], total.inputs[1])
        height_out = total.outputs['Value']
        bump.inputs['Distance'].default_value = 3.0
    nt.links.new(height_out, bump.inputs['Height'])

    set_input(bsdf, ['Base Color'], (0.004, 0.035, 0.060, 1))
    set_input(bsdf, ['Roughness'], 0.03)
    set_input(bsdf, ['IOR'], 1.333)
    set_input(bsdf, ['Metallic'], 0.0)
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat, mapping


def make_ocean_patch(name, tile, res, view_res, repeat_x, repeat_y, center, z, seed, mat):
    """Ocean 모디파이어로 (repeat_x*tile) x (repeat_y*tile) m 크기의 진짜 파도 표면을 만든다."""
    scene = bpy.context.scene
    me = bpy.data.meshes.new(name + "Base")
    me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    patch = bpy.data.objects.new(name, me)
    scene.collection.objects.link(patch)

    mod = patch.modifiers.new("Ocean", 'OCEAN')
    mod.geometry_mode = 'GENERATE'
    mod.spatial_size = int(tile)
    mod.resolution = res
    mod.viewport_resolution = view_res
    mod.repeat_x = repeat_x
    mod.repeat_y = repeat_y
    mod.wind_velocity = WIND_VELOCITY
    mod.wave_scale = WAVE_SCALE
    mod.choppiness = CHOPPINESS
    mod.depth = 200.0
    mod.damping = 0.4
    mod.wave_alignment = 0.5
    mod.wave_direction = math.radians(0.0)     # 파도가 북쪽에서 밀려오도록
    mod.use_normals = True
    mod.random_seed = seed
    mod.time = 0.0

    # 모디파이어가 만든 격자는 원점에서 +x, +y 쪽으로 뻗으므로 중심을 맞춰 옮김
    patch.location = (center[0] - repeat_x * tile / 2 + tile / 2,
                      center[1] - repeat_y * tile / 2 + tile / 2, z)
    patch.data.materials.append(mat)
    return patch


def build_ocean(center, ocean_mat, far_mat):
    """바다를 3겹으로 만든다.
       가까이: 촘촘한 진짜 파도 / 중간: 성긴 진짜 파도(경계를 수평선 쪽으로 밀어냄) /
       멀리: 넓은 평면 + 너울·잔물결 노멀"""
    near = make_ocean_patch("OceanNear", OCEAN_TILE_SIZE, OCEAN_RESOLUTION, OCEAN_VIEWPORT_RESOLUTION,
                            OCEAN_REPEAT_X, OCEAN_REPEAT_Y, center, 0.0, SEED, ocean_mat)
    mid_center = (center[0], center[1] - 2800.0)
    mid = make_ocean_patch("OceanMid", OCEAN_MID_TILE, OCEAN_MID_RESOLUTION, 4,
                           OCEAN_MID_REPEAT, OCEAN_MID_REPEAT, mid_center, -0.3, SEED + 1, ocean_mat)

    bpy.ops.mesh.primitive_plane_add(size=400000.0, location=(0, 0, -0.8))
    far = bpy.context.active_object
    far.name = "OceanFar"
    far.data.materials.append(far_mat)
    return [near, mid], far


# ======================================================================
# 4. 하늘 + 태양
# ======================================================================
def build_sky():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("JejuSky")
    scene.world = world
    nt = world.node_tree
    if nt is None:
        world.use_nodes = True
        nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.name = "SkySun"
    for sky_type in ('MULTIPLE_SCATTERING', 'SINGLE_SCATTERING', 'NISHITA'):
        try:
            sky.sky_type = sky_type
            break
        except TypeError:
            continue
    sky.sun_disc = True
    sky.sun_size = math.radians(SUN_DISC_SIZE_DEG)
    sky.sun_intensity = 1.0
    sky.altitude = 0.0
    bg = nt.nodes.new('ShaderNodeBackground')
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(sky.outputs[0], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    return world, sky


# ======================================================================
# 5. 카메라
# ======================================================================
def build_camera(pos, bearing_deg, pitch_deg):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("JejuCam")
    cam_data.lens = CAM_LENS
    cam_data.clip_start = 1.0
    cam_data.clip_end = 500000.0
    cam = bpy.data.objects.new("JejuCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = pos
    # 카메라는 기본이 아래(-Z)를 봄 -> X를 90도+pitch 로 눕히고, 방위는 Z축 회전(시계방향이라 음수)
    cam.rotation_euler = (math.radians(90 + pitch_deg), 0.0, -math.radians(bearing_deg))
    scene.camera = cam
    return cam


# ======================================================================
# 6. 애니메이션(태양 이동, 파도, 잔물결)
# ======================================================================
def animate(world, sky, patches, ripples):
    """ripples: [(재질, 매핑노드), ...] 잔물결 노이즈 좌표를 이동시킬 재질들."""
    scene = bpy.context.scene
    prefs = bpy.context.preferences.edit
    old_interp = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = 'LINEAR'

    nt = world.node_tree
    span = max(FRAME_END - FRAME_START, 1)
    seconds = span / FPS
    sky_path = f'nodes["{sky.name}"]'
    for f in range(FRAME_START, FRAME_END + 1, 2):
        t = (f - FRAME_START) / span
        az, el = sun_at(t)
        sky.sun_rotation = math.radians(az)     # 방위각(북 0도, 시계방향)
        sky.sun_elevation = math.radians(el)
        nt.keyframe_insert(data_path=sky_path + '.sun_rotation', frame=f)
        nt.keyframe_insert(data_path=sky_path + '.sun_elevation', frame=f)
    az, el = sun_at(1.0)
    sky.sun_rotation = math.radians(az)
    sky.sun_elevation = math.radians(el)
    nt.keyframe_insert(data_path=sky_path + '.sun_rotation', frame=FRAME_END)
    nt.keyframe_insert(data_path=sky_path + '.sun_elevation', frame=FRAME_END)

    # 파도: Ocean 모디파이어의 time 을 흘려보냄
    for patch in patches:
        mod = patch.modifiers["Ocean"]
        mod.time = 0.0
        patch.keyframe_insert(data_path='modifiers["Ocean"].time', frame=FRAME_START)
        mod.time = seconds * WAVE_SPEED
        patch.keyframe_insert(data_path='modifiers["Ocean"].time', frame=FRAME_END)

    # 잔물결: 노이즈 좌표를 천천히 이동
    for mat, mapping in ripples:
        mt = mat.node_tree
        loc = mapping.inputs['Location']
        path = f'nodes["{mapping.name}"].inputs[1].default_value'
        loc.default_value = (0.0, 0.0, 0.0)
        mt.keyframe_insert(data_path=path, frame=FRAME_START)
        loc.default_value = (seconds * 1.2, seconds * 0.7, 0.0)
        mt.keyframe_insert(data_path=path, frame=FRAME_END)

    prefs.keyframe_new_interpolation_type = old_interp
    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.frame_set(FRAME_START)


# ======================================================================
# 메인
# ======================================================================
def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    opts = {'render_frame': None, 'out': None, 'save': None, 'scale': 100, 'samples': SAMPLES,
            'exposure': EXPOSURE, 'dem': None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--render-frame':
            opts['render_frame'] = int(argv[i + 1]); i += 2
        elif a == '--out':
            opts['out'] = argv[i + 1]; i += 2
        elif a == '--save':
            opts['save'] = argv[i + 1]; i += 2
        elif a == '--scale':
            opts['scale'] = int(argv[i + 1]); i += 2
        elif a == '--samples':
            opts['samples'] = int(argv[i + 1]); i += 2
        elif a == '--exposure':
            opts['exposure'] = float(argv[i + 1]); i += 2
        elif a == '--dem':
            opts['dem'] = argv[i + 1]; i += 2
        else:
            i += 1
    return opts


def main():
    global HEIGHTMAP_PATH
    opts = parse_args()
    if opts['dem']:
        HEIGHTMAP_PATH = opts['dem']
    clear_scene()
    scene = bpy.context.scene

    # 지형
    heights, land = prepare_heights(TERRAIN_RES, TERRAIN_RES)
    terrain = build_terrain(heights)
    ny, nx = heights.shape

    # 카메라 위치: CAM_X 열에서 남쪽부터 훑어 첫 육지(해안선)를 찾고 CAM_INLAND 만큼 안쪽에 둠
    col = int(round((CAM_X / TERRAIN_SIZE_X + 0.5) * (nx - 1)))
    col = min(max(col, 0), nx - 1)
    rows = np.nonzero(land[:, col])[0]
    if rows.size:
        coast_y = -TERRAIN_SIZE_Y / 2 + rows[0] / (ny - 1) * TERRAIN_SIZE_Y
    else:
        coast_y = -TERRAIN_SIZE_Y * 0.3
    cam_y = coast_y + CAM_INLAND
    row = min(max(int(round((cam_y / TERRAIN_SIZE_Y + 0.5) * (ny - 1))), 0), ny - 1)
    ground = max(float(heights[row, col]), 0.0)
    cam_pos = (CAM_X, cam_y, ground + CAM_HEIGHT_ABOVE_GROUND)
    build_camera(cam_pos, CAM_BEARING, CAM_PITCH)

    # 바다: 해안선 앞(남쪽) 바다에 진짜 파도 조각을 둔다
    ocean_mat, ripple = make_ocean_material("OceanMat")
    far_mat, far_ripple = make_ocean_material("OceanFarMat", swell=True)
    patch_depth = OCEAN_REPEAT_Y * OCEAN_TILE_SIZE
    patches, far = build_ocean((CAM_X, coast_y - patch_depth / 2 + 250.0), ocean_mat, far_mat)

    # 하늘, 태양
    world, sky = build_sky()

    # 렌더 설정
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = opts['samples']
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = opts['scale']
    scene.render.fps = FPS
    scene.render.filepath = OUTPUT_DIR + "jeju_"
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.exposure = opts['exposure']

    animate(world, sky, patches, [(ocean_mat, ripple), (far_mat, far_ripple)])

    print(f"[Jeju] 지형 격자 {nx}x{ny}, 최고점 {heights.max():.0f} m, 해안선 y={coast_y:.0f} m, "
          f"카메라 {tuple(round(c) for c in cam_pos)}")
    print(f"[Jeju] 태양 경로: 방위 {SUN_AZIMUTH_START:.0f}->{SUN_AZIMUTH_END:.0f}도, 고도 {SUN_ELEVATION_MIN:.0f}~{SUN_ELEVATION_PEAK:.0f}도")

    if opts['save']:
        bpy.ops.wm.save_as_mainfile(filepath=opts['save'])
        print(f"[Jeju] 저장: {opts['save']}")

    if opts['render_frame'] is not None:
        scene.frame_set(opts['render_frame'])
        if opts['out']:
            scene.render.filepath = opts['out']
        bpy.ops.render.render(write_still=True)
        print(f"[Jeju] 프레임 {opts['render_frame']} 렌더 완료: {scene.render.filepath}")


main()
