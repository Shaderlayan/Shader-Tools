#!/usr/bin/env python3

from binary_reader import BinaryReader
import os
import shpkdict
import shpkstruct
import sys
from typing import NoReturn

def usage() -> NoReturn:
    print('Usage:')
    print()
    print('  %s list input.shpk' % (sys.argv[0],))
    print('    Displays information about the given ShPk, including but not limited to valid shader IDs')
    print()
    print('  %s extract input.shpk [shader_id1 [shader_id2 [...]]]' % (sys.argv[0],))
    print('    Extracts the specified shaders (or all of them) from the given ShPk')
    print('    They will be stored in a subdirectory with the same name as the ShPk')
    print()
    print('  %s update input.shpk output.shpk shader_id1 file1 [shader_id2 file2 [...]]' % (sys.argv[0],))
    print('    Updates the given ShPk, replacing the specified shaders by the given files')
    print('    Adding new shaders is also supported by specifying vsNEW/ORIG or psNEW/ORIG')
    print('    Some special values are accepted instead of shader IDs and file names:')
    print('      mp+ name:start:size[:defaultvalue]')
    print('      mk+ name:defaultvalue:value1,vsNEW/ORIG,...,psNEW/ORIG,...:value2,...:...')
    print('      ct= name:type')
    print('      st= name:type')
    print('      tt= name:type')
    print('      ut= name:type')
    sys.exit(1)

if len(sys.argv) < 3:
    usage()

def read_file_bytes(path: str) -> bytes:
    with open(path, 'rb') as fd:
        return fd.read()

def write_file_bytes(path: str, data: bytes) -> None:
    with open(path, 'wb') as fd:
        fd.write(data)

def read_shpk(path: str) -> shpkstruct.ShPk:
    return shpkstruct.ShPk.read(BinaryReader(read_file_bytes(path)))

def write_shpk(path: str, shpk: shpkstruct.ShPk) -> None:
    writer = BinaryReader()
    shpk.write(writer)
    write_file_bytes(path, bytes(writer.buffer()))

def crc32(name: str, prefixed_calc = None) -> int:
    if name.startswith('0x'):
        return int(name[2:], base=16)
    name_b = bytes(name, 'utf-8')
    hash = shpkstruct.crc32(name_b) if prefixed_calc is None else prefixed_calc.checksum(name_b)
    print('0x%08X  %s%s' % (hash, '' if prefixed_calc is None else '…', name))
    return hash

def parse_mat_param(param: str) -> shpkstruct.MatParam:
    tokens = param.split(':')
    id = crc32(tokens[0])
    newparam = shpkstruct.MatParam({
        'id': id,
        'offset': (int(tokens[1][:-1]) * 4 + 'xyzw'.index(tokens[1][-1])) * 4,
        'size': int(tokens[2]) * 4,
    })
    if len(tokens) >= 4:
        newparam.__dict__['defaultvalue'] = tokens[3]
    else:
        newparam.__dict__['defaultvalue'] = 0.0
    return newparam

def parse_mat_key(param: str) -> tuple[int, int, dict]:
    tokens = param.split(':')
    key = crc32(tokens[0])
    prefixed_calc = shpkstruct.crc32_prefixed_calc(key)
    default_value = crc32(tokens[1], prefixed_calc)
    replacements = {}
    for token in tokens[2:]:
        subtokens = token.split(',')
        value = crc32(subtokens[0], prefixed_calc)
        vs_replacements = {}
        ps_replacements = {}
        for subtoken in subtokens[1:]:
            if subtoken.startswith('vs'):
                s_replacements = vs_replacements
                rest = subtoken[2:]
            elif subtoken.startswith('ps'):
                s_replacements = ps_replacements
                rest = subtoken[2:]
            else:
                raise ValueError()
            slash = rest.index('/')
            s_replacements[int(rest[(slash + 1):])] = int(rest[:slash])
        replacements[value] = (vs_replacements, ps_replacements)
    return (key, default_value, replacements)

def parse_resource_type_assignment(assignment: str) -> tuple[bytes, int]:
    tokens = assignment.split(':')
    return (bytes(tokens[0], 'utf-8'), int(tokens[1]))

def create_resource(name: bytes, is_texture: bool) -> shpkstruct.Resource:
    return shpkstruct.Resource({
        'id': shpkstruct.crc32(name),
        'name_offset': 0,
        'name_size': 0,
        'unk': 1 if is_texture else 0,
        'slot': 0,
        'size': 0,
    }, name)

def get_shader(shpk: shpkstruct.ShPk, shader_id: str) -> shpkstruct.Shader:
    if shader_id.startswith('vs'):
        shader_pool = shpk.vertex_shaders
        rest = shader_id[2:]
    elif shader_id.startswith('ps'):
        shader_pool = shpk.pixel_shaders
        rest = shader_id[2:]
    else:
        raise ValueError()
    slash = rest.find('/')
    if slash >= 0:
        if int(rest[:slash]) != len(shader_pool):
            raise ValueError()
        original = shader_pool[int(rest[(slash + 1):])]
        duplicate = original.new_variant()
        shader_pool.append(duplicate)
        return duplicate
    else:
        return shader_pool[int(rest)]

verb = sys.argv[1]
input_path = sys.argv[2]
extra_args = sys.argv[3:]
shader_pack = read_shpk(sys.argv[2])

match verb:
    case 'list' | 'toc' | 'ls' | 't':
        print("This is a ShPk for version %d" % (7 if shader_pack.is_7 else 6,))
        print()
        print("Valid shader IDs in this ShPk:")
        print("  vs0 .. vs%d" % (len(shader_pack.vertex_shaders) - 1,))
        print("  ps0 .. ps%d" % (len(shader_pack.pixel_shaders) - 1,))
        print()
        print("Material parameters for this ShPk: %d registers (%d bytes)" % (shader_pack.file_header.mat_params_size / 16, shader_pack.file_header.mat_params_size))
        mp_name_suffix_length = 0
        mp_location_str_length = 0
        for mat_param in shader_pack.mat_params:
            name = shpkdict.resolve(mat_param.id)
            if name is not None:
                mp_name_suffix_length = max(mp_name_suffix_length, len(name) + 3)
            if (mat_param.offset & 3) == 0 or (mat_param.size & 3) == 0:
                mp_location_str_length = max(mp_location_str_length, len(str(mat_param.offset >> 2)) + len(str(mat_param.size >> 2)) + 4)
        for mat_param in shader_pack.mat_params:
            name = shpkdict.resolve(mat_param.id)
            name_suffix = (" : %s" % (name,) if name is not None else "").ljust(mp_name_suffix_length)
            if (mat_param.offset & 3) != 0 or (mat_param.size & 3) != 0:
                print("  0x%08X%s is unaligned (offset %d, size %d)" % (mat_param.id, name_suffix, mat_param.offset, mat_param.size))
            else:
                mp_start = mat_param.offset >> 2
                mp_size = mat_param.size >> 2
                mp_location_str = ("(%d%s:%d)" % (mp_start >> 2, "xyzw"[mp_start & 3], mp_size)).rjust(mp_location_str_length)
                if shader_pack.mat_param_defaults is not None:
                    print("  0x%08X%s %s : %s" % (mat_param.id, name_suffix, mp_location_str, ", ".join("%10.3f" % (value,) for value in shader_pack.mat_param_defaults[mp_start:(mp_start + mp_size)])))
                else:
                    print("  0x%08X%s %s" % (mat_param.id, name_suffix, mp_location_str))
        print()
        print("Samplers and textures used in this ShPk:")
        if shader_pack.is_7:
            for sampler in shader_pack.samplers:
                has_texture = "T" if shader_pack.has_texture_id(sampler.id) else " "
                print("  0x%08X [S%s] : %s" % (sampler.id, has_texture, sampler.name.decode('utf-8')))
            for texture in shader_pack.textures:
                if not shader_pack.has_sampler_id(texture.id):
                    print("  0x%08X [ T] : %s" % (texture.id, texture.name.decode('utf-8')))
        else:
            for sampler in shader_pack.samplers:
                print("  0x%08X : %s" % (sampler.id, sampler.name.decode('utf-8')))
        exit()
    case 'update' | 'u':
        if len(extra_args) % 2 != 1:
            usage()
        output_path = extra_args[0]
        with_flags = set()
        update_global_resources = False
        for i in range(1, len(extra_args), 2):
            shader_id = extra_args[i]
            new_shader_path = extra_args[i + 1]
            match shader_id:
                case 'with':
                    with_flags.add(new_shader_path)
                case 'without':
                    with_flags.remove(new_shader_path)
                case 'mp+':
                    matparam = parse_mat_param(new_shader_path)
                    shader_pack.mat_params.append(matparam)
                    if not matparam.__dict__["defaultvalue"] == 0.0:
                        mpspl = matparam.__dict__["defaultvalue"].split(",")
                        if len(mpspl) * 4 == matparam.__dict__["size"]:
                            for i, num in enumerate(mpspl):
                                shader_pack.extra_defaults[int(matparam.__dict__["offset"] / 4 + i)] = float(num)
                        else:
                            print("WARNING:" + new_shader_path + " has wrong default parameters! They are defaulted to 0...")
                    update_global_resources = True
                case 'mk+':
                    shader_pack.add_mat_key(*parse_mat_key(new_shader_path))
                case 'ct=':
                    (res_name, res_type) = parse_resource_type_assignment(new_shader_path)
                    constant = shader_pack.get_constant_by_name(res_name)
                    if constant is None:
                        constant = create_resource(res_name, False)
                        shader_pack.constants.append(constant)
                        update_global_resources = True
                    constant.slot = res_type
                case 'st=':
                    (res_name, res_type) = parse_resource_type_assignment(new_shader_path)
                    sampler = shader_pack.get_sampler_by_name(res_name)
                    if sampler is None:
                        sampler = create_resource(res_name, False)
                        shader_pack.samplers.append(sampler)
                        update_global_resources = True
                    sampler.slot = res_type
                case 'tt=':
                    (res_name, res_type) = parse_resource_type_assignment(new_shader_path)
                    texture = shader_pack.get_texture_by_name(res_name)
                    if texture is None:
                        texture = create_resource(res_name, True)
                        shader_pack.textures.append(texture)
                        update_global_resources = True
                    texture.slot = res_type
                case 'ut=':
                    (res_name, res_type) = parse_resource_type_assignment(new_shader_path)
                    uav = shader_pack.get_uav_by_name(res_name)
                    if uav is None:
                        uav = create_resource(res_name, False)
                        shader_pack.uavs.append(uav)
                        update_global_resources = True
                    uav.slot = res_type
                case _:
                    shader = get_shader(shader_pack, shader_id)
                    shader.blob = read_file_bytes(new_shader_path)
                    shader.update_resources(shader_pack, new_shader_path, 'pre-disasm' in with_flags)
                    update_global_resources = True
        if update_global_resources:
            shader_pack.update_resources()
        write_shpk(output_path, shader_pack)
        exit()
    case 'extract' | 'get' | 'x':
        (outdir, _) = os.path.splitext(input_path)
        os.makedirs(outdir, exist_ok=True)
        if len(extra_args) == 0:
            wanted_shaders = ['vs' + str(i) for i in range(len(shader_pack.vertex_shaders))]
            wanted_shaders.extend(['ps' + str(i) for i in range(len(shader_pack.pixel_shaders))])
        else:
            wanted_shaders = extra_args
        ext = '.dxbc' if shader_pack.file_header.graphics_platform == b'DX11' else '.cso'
        for shader_id in wanted_shaders:
            shader = get_shader(shader_pack, shader_id)
            suffix = '.ps' if shader.stage == shpkstruct.stages.STAGE_PIXEL else '.vs'
            outpath = os.path.join(outdir, shader_id + suffix + ext)
            print('Extracting %s' % (outpath,))
            write_file_bytes(outpath, shader.blob)
        exit()
    case 'crc' | 'hash' | 'c':
        for arg in extra_args:
            print('0x%08X  %s' % (shpkstruct.crc32(bytes(arg, 'utf-8')), arg))
        exit()
    case 'test':
        pass
    case _:
        usage()
