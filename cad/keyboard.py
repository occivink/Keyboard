#!/bin/python3

from solid import *
from solid.utils import *
import sys
import math
import bezier

eps = 0.001
layer_height = 0.2

def bezier_visualize(points, diameter, width):
    res = cube(0)
    i = 0
    while i < len(points):
        p1 = points[i]
        p2 = points[i+1]
        p3 = points[i+2]
        p4 = points[(i+3) % len(points)]
        res += translate(p1)(circle(d=diameter))
        res += translate(p4)(circle(d=diameter))
        res += line2d.line2d(p1, p2, width=width)
        res += line2d.line2d(p4, p3, width=width)
        i += 3
    return res

def bezier_from_points(points):
    if len(points) != 4:
        raise ValueError
    xs = [points[0][0], points[1][0], points[2][0], points[3][0]]
    ys = [points[0][1], points[1][1], points[2][1], points[3][1]]
    return bezier.Curve([xs, ys], degree=3)

def sample_bezier_evenly(curve, precision):
    coords = []
    tangents = []
    x = 0.0
    while True:
        p = curve.evaluate(x)
        coords.append([p[0][0], p[1][0]])
        tangent = curve.evaluate_hodograph(x)
        tangents.append([tangent[0][0], tangent[1][0]])
        if x == 1.0:
            break
        x = min(x + precision, 1.0)
    return coords, tangents

def convert_bezier_points(points):
    res=[]
    trivial = True
    for i in range(0, len(points)):
        if (i % 3) == 0:
            res.append(points[i])
        else:
            handle = points[i]
            point = points[i - 1] if (i % 3) == 1 else points[(i + 1) % len(points)]
            if type(handle[0]) == str:
                if handle[0] == "SHARP":
                    res.append(point)
                elif handle[0] == "RELATIVE":
                    trivial = False
                    res.append([point[0] + handle[1], point[1] + handle[2]])
                elif handle[0] == "POLAR":
                    trivial = False
                    r = handle[1]
                    angle = handle[2] * math.pi / 180.
                    res.append([point[0] + r * math.cos(angle), point[1] + r * math.sin(angle)])
                else:
                    print(handle)
                    raise ValueError
            else:
                trivial = False
                res.append(handle)
    return res, trivial

def bezier_lines(points, precision):
    res = []
    offset = 0
    while offset + 2 < len(points):
        p1 = points[offset]
        h1 = points[offset+1]
        h2 = points[offset+2]
        p2 = points[(offset+3) % len(points)]
        subset, trivial = convert_bezier_points([p1, h1, h2, p2])
        if trivial:
            res.append(p1)
            res.append(p2)
        else:
            curve = bezier_from_points(subset)
            sampled, _ = sample_bezier_evenly(curve, precision)
            res += sampled
        offset += 3
    return res

def sum_coords(*args):
    res = [0 for i in range(0, len(args[0]))]
    for a in args:
        for i in range(0, len(res)):
            res[i] += a[i]
    return res

def diff_coords(*args):
    res = [args[0][i] for i in range(0, len(args[0]))]
    for a in range(1, len(args)):
        arg = args[a]
        for i in range(0, len(res)):
            res[i] -= arg[i]
    return res

class ThumbCluster:
    def __init__(self,
            key_count,
            bezier_points,
            position,
            offset,
            keycap_size,
            keycap_spacing,
            switch_hole_size,
            precision):
        self.key_count = key_count
        self.keycap_size = keycap_size
        self.keycap_spacing = keycap_spacing
        self.switch_hole_size = switch_hole_size
        points_converted, _ = convert_bezier_points(bezier_points)
        self.bezier_curve = bezier_from_points(points_converted)
        self.curve_target_length = (key_count - 1) * (self.keycap_size[0] + self.keycap_spacing)
        self.curve_scale_factor = self.curve_target_length / self.bezier_curve.length
        self.thumb_curve_points, self.thumb_curve_tangents = sample_bezier_evenly(self.bezier_curve, precision)
        self.position = position
        self.offset = offset

        for i in range(0,len(self.thumb_curve_points)):
            self.thumb_curve_points[i] = [
                position[0] + self.curve_scale_factor * self.thumb_curve_points[i][0],
                position[1] + self.curve_scale_factor * self.thumb_curve_points[i][1],
            ]

    def get_key_count(self):
        return self.key_count

    def get_thumb_keys_pos(self):
        res = []
        length = 0
        dist_between_keys_center = self.curve_target_length / (self.key_count - 1)
        for i in range(0,len(self.thumb_curve_points)-1):
            p1 = self.thumb_curve_points[i]
            p2 = self.thumb_curve_points[i+1]
            t1 = self.thumb_curve_tangents[i]
            t2 = self.thumb_curve_tangents[i+1]
            seg_length = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
            t = None
            if i == 0:
                t = 0
            elif i + 1 == len(self.thumb_curve_points) - 1:
                t = 1
            elif length % dist_between_keys_center > (length + seg_length) % dist_between_keys_center:
                t = 1 - ((length + seg_length) % dist_between_keys_center) / seg_length
            if t is not None:
                p = [(1 - t) * p1[0] + t * p2[0], (1 - t) * p1[1] + t * p2[1]]
                t = [(1 - t) * t1[0] + t * t2[0], (1 - t) * t1[1] + t * t2[1]]
                angle = math.atan2(t[1], t[0])
                res.append([p, angle])
            length += seg_length
        return res

    def get_key_coord(self, key_index, tangent_offset = 0, perpendicular_offset = 0):
        thumb_keys_pos = self.get_thumb_keys_pos()
        key = thumb_keys_pos[key_index]
        cap_angle = key[1]
        # the line is defined along the bottom edge of the keycap, so we add an offset
        po = perpendicular_offset + self.keycap_size[1]/2
        return [sum_coords(
            key[0],
            [tangent_offset * math.cos(cap_angle), tangent_offset * math.sin(cap_angle)],
            [po * math.cos(cap_angle + math.pi/2), po * math.sin(cap_angle + math.pi/2)]
        ), cap_angle]

    def make_shape(self):
        shape = square(0)
        obj = square([self.keycap_size[1] + 2 * self.offset, self.keycap_size[0] + 2 * self.offset], center=True)
        for i in range(0,len(self.thumb_curve_points)):
            pos = self.thumb_curve_points[i]
            tangent = self.thumb_curve_tangents[i]
            angle = math.atan2(tangent[1], tangent[0])
            angle += math.pi/2
            offset_perp = self.keycap_size[1]/2
            pos = sum_coords(pos, [math.cos(angle) * offset_perp, math.sin(angle) * offset_perp])
            rot = rotate([0,0,angle/math.pi*180])(obj)
            shape += translate(pos)(rot)
        return shape

    def get_shape_points(self):
        res = []
        for i in range(0,len(self.thumb_curve_points)):
            pos = self.thumb_curve_points[i]
            tangent = self.thumb_curve_tangents[i]
            angle = math.atan2(tangent[1], tangent[0])
            angle += math.pi/2
            offset_perp = -self.offset
            pos = sum_coords(pos, [math.cos(angle) * offset_perp, math.sin(angle) * offset_perp])
            res.append(pos)
        res.reverse()
        return res


    def make_switch_holes(self):
        shape = square(0)
        for i in range(0, self.get_key_count()):
            key_pos, key_angle = self.get_key_coord(i, 0, 0)
            shape += translate(key_pos)(rotate([0,0,key_angle / math.pi * 180])(
                square(self.switch_hole_size, center=True)))
        return shape

    def switches_positions(self):
        res = []
        for i in range(0, self.get_key_count()):
            key_pos, key_angle = self.get_key_coord(i, 0, 0)
            res.append([key_pos, key_angle / math.pi * 180])
        return res

    def get_top_left(self):
        return self.get_key_coord(0, -self.keycap_size[0]/2 - self.offset, self.keycap_size[1]/2 + self.offset)[0]

    def get_top_right(self):
        return self.get_key_coord(self.key_count - 1, self.keycap_size[0]/2 + self.offset, self.keycap_size[1]/2 + self.offset)[0]

    def get_bottom_left(self):
        return self.get_key_coord(0, -self.keycap_size[0]/2 - self.offset, -self.keycap_size[1]/2 - self.offset)[0]

    def get_bottom_right(self):
        return self.get_key_coord(self.key_count - 1, self.keycap_size[0]/2 + self.offset, -self.keycap_size[1]/2 - self.offset)[0]

class Shell:
    def __init__(self, rows, columns, keycap_size, thumb_cluster, keycap_dist, switch_hole_size, column_stagger, shell_offset, precision):
        self.rows = rows
        self.columns = columns
        self.keycap_size = keycap_size
        self.keycap_dist = keycap_dist
        self.thumb_cluster = thumb_cluster
        self.switch_hole_size = switch_hole_size
        self.switch_hole_dist = diff_coords(
            sum_coords(self.keycap_size, self.keycap_dist), self.switch_hole_size)

        self.column_stagger = column_stagger
        self.shell_offset = shell_offset
        self.precision = precision

        casepoints = [ # goes clockwise, starting from bottom left
            self.thumb_cluster.get_bottom_left(),
                ["RELATIVE", 0, 15],
                ["RELATIVE", 5, 0],
            sum_coords(self.get_key_position(0,0), [2*self.keycap_size[1], -shell_offset]),
                ["SHARP"],
                ["SHARP"],
            sum_coords(self.get_key_position(0,0), [-self.shell_offset, -self.shell_offset]), # BOTTOM LEFT
                ["SHARP"],
                ["SHARP"],
            sum_coords(self.get_key_position(rows-1,0), [-self.shell_offset, self.keycap_size[1] + self.shell_offset]), # TOP LEFT
                ["RELATIVE", 25, 0],
                ["RELATIVE", -25, 0],
            sum_coords(self.get_key_position(rows-1,3), [0, self.keycap_size[1] + self.shell_offset]),
                ["SHARP"],
                ["SHARP"],
            sum_coords(self.get_key_position(rows-1,3), self.keycap_size, [0, self.shell_offset]),
                ["POLAR", 15, 0],
                ["POLAR", 15, 180],
            [self.panel_left(), self.panel_top()],
                ["SHARP"],
                ["SHARP"],
            [self.panel_left() + self.panel_width(), self.panel_top()], # TOP RIGHT
                ["SHARP"],
                ["SHARP"],
            [self.panel_left() + self.panel_width(), 0],
                ["RELATIVE", 0, -8],
                ["POLAR", 8, 125],
            self.thumb_cluster.get_top_right(), # THUMB CLUSTER, TOP RIGHT
                ["SHARP"],
                ["SHARP"],
            self.thumb_cluster.get_bottom_right(),
        ]

        self.bezier_curve = bezier_lines(casepoints, self.precision)


    def panel_top(self):
        return  self.get_key_position(self.rows-1,self.columns-1)[1] + self.keycap_size[1] + self.shell_offset
    def panel_width(self):
        return 24
    def panel_height(self):
        return 92
    def panel_left(self):
        return  self.get_key_position(0,self.columns-1)[0] + self.keycap_size[0]
    def panel_right(self):
        return  self.panel_left() + self.panel_width()

    def get_key_position(self, row, col, center=False):
        return sum_coords(
            [self.keycap_size[0]/2, self.keycap_size[1]/2] if center else [0,0],
            [self.shell_offset, self.shell_offset],
            [
                col * (self.switch_hole_size[0] + self.switch_hole_dist[0]),
                row * (self.switch_hole_size[1] + self.switch_hole_dist[1]) + self.column_stagger[col],
            ]
        )

    def get_shape_points(self):
        return self.bezier_curve

    def make_switch_holes(self):
        res = square(0)
        for row in range(0, self.rows):
            for col in range(0, self.columns):
                key_pos = self.get_key_position(row,  col,  center=True)
                res += translate(key_pos)(square(self.switch_hole_size, center=True))
        return res

    def switches_positions(self):
        res = []
        for row in range(0, self.rows):
            for col in range(0, self.columns):
                key_pos = self.get_key_position(row,  col,  center=True)
                res.append([key_pos, 0])
        return res

class WeightedDisc:
    disc_height=1.6
    disc_diam=35.3
    disc_hole_diam=8.4

    def __init__(self, pos, number, extra_diam, disc_dist_from_bot, disc_dist_to_top):
        self.pos = pos
        self.number_discs = number
        self.extra_diam = extra_diam
        self.disc_dist_from_bot = disc_dist_from_bot
        self.disc_dist_to_top = disc_dist_to_top

    def make_discs(self):
        discs = cylinder(d=self.disc_diam, h=self.number_discs * self.disc_height, segments=60)
        discs -= cylinder(d=self.disc_hole_diam, h=self.number_discs * self.disc_height, segments=60)
        return translate([0,0,self.disc_dist_from_bot])(translate(self.pos)(discs))

    def get_diameter(self):
        return self.disc_diam + self.extra_diam

    def make_shape(self):
        return translate(self.pos)(cylinder(d = self.disc_diam + self.extra_diam,
            h = self.number_discs * self.disc_height + self.disc_dist_from_bot + self.disc_dist_to_top, segments=60))

class Controller:
    board_width = 21
    board_length = 51.2
    board_height = 1.1

    holes_diam = 2.1
    holes_dist_to_side_edge = 4.8
    holes_dist_to_top_edge = 2

    pin_hole_diam = 1
    button_dist_to_left = 7
    button_dist_to_top = 12

    usb_height = 3.2
    usb_width = 8.5
    usb_length = 5.7

    usb_protursion = 1.5

    board_edge_to_cable_shell = 2.5 # distance between board edge to cable shell
    usb_bottom_from_board_bottom = 0.5 # distance from board bottom to usb socket bottom

    def __init__(self, pos, usb_top_height, total_height, pillar_diam, mirror):
        self.pos = pos
        self.mirror = mirror
        self.board_z_pos = usb_top_height - (self.usb_bottom_from_board_bottom + self.usb_height)
        self.total_height = total_height
        self.pillar_diam = pillar_diam

    def make_shape(self):
        board = cube([self.board_width, self.board_length, self.board_height])
        for x in [self.holes_dist_to_side_edge, self.board_width - self.holes_dist_to_side_edge]:
            for y in [self.holes_dist_to_top_edge, self.board_length - self.holes_dist_to_top_edge]:
                board -= translate([x,y])(cylinder(d=self.holes_diam, h=self.board_height, segments=20))

        usb = cube([self.usb_width, self.usb_length, self.usb_height])
        usb = translate([self.board_width/2-self.usb_width/2, 0])(usb)
        usb = translate([0, self.board_length - self.usb_length + self.usb_protursion])(usb)
        usb = translate([0,0,self.usb_bottom_from_board_bottom])(usb)

        board += usb

        return self.move_into_place(board + usb)

    def make_top_hole(self):
        usb = cube([self.usb_width, self.usb_length * 2, self.usb_height])
        usb = translate([self.board_width/2-self.usb_width/2, 0])(usb)
        usb = translate([0, self.board_length - self.usb_length + self.usb_protursion])(usb)
        usb = translate([0,0,self.usb_bottom_from_board_bottom])(usb)

        pin_hole = cylinder(d=self.pin_hole_diam, h=self.total_height - self.board_height - self.board_z_pos, segments = 10)
        pin_hole = translate([
                self.button_dist_to_left if not self.mirror else self.board_width - self.button_dist_to_left,
                self.board_length - self.button_dist_to_top,
                self.board_height
            ])(pin_hole)

        return self.move_into_place(usb + pin_hole)

    def move_into_place(self, obj, with_height = True):
        obj = translate([-self.board_width,-self.board_length - self.board_edge_to_cable_shell])(obj)
        return translate(self.pos)(translate([0,0,self.board_z_pos if with_height else 0])(obj))

    def make_bottom_support(self):
        res = cube(0)
        for x in [self.holes_dist_to_side_edge, self.board_width - self.holes_dist_to_side_edge]:
            for y in [self.holes_dist_to_top_edge, self.board_length - self.holes_dist_to_top_edge]:
                res += translate([x,y])(cylinder(d=self.pillar_diam, h=self.board_z_pos - layer_height, segments=20))
        return self.move_into_place(res, with_height = False)

    def make_top_support(self):
        res = cube(0)
        for x in [self.holes_dist_to_side_edge, self.board_width - self.holes_dist_to_side_edge]:
            for y in [self.holes_dist_to_top_edge, self.board_length - self.holes_dist_to_top_edge]:
                res += translate([x,y])(cylinder(d=self.holes_diam, h=self.board_height, segments=20))
                res += translate([x,y,self.board_height])(
                    cylinder(d=self.pillar_diam, h=self.total_height - self.board_height - self.board_z_pos, segments=20))
        return self.move_into_place(res)

class Screw:
    thread_diameter = 2.2
    thread_height = 6
    head_height = 2
    head_diameter = 4

    nut_height = 1.2
    nut_flat_width = 4.2

    extra_support_height_bot = 1

    nut_diameter = 2.3094 * nut_flat_width / 2
    nut_holder_diameter =  1.2 * nut_diameter

    def __init__(self, xy_pos, pillar_diam, z_elevation):
        self.xy_pos = xy_pos
        self.pillar_diam = pillar_diam
        self.z_elevation = z_elevation

    def make_top_hole(self):
        # add some bridging to make it possible to print above the nut hole
        nut_z_pos = self.z_elevation + self.head_height + self.thread_height - self.nut_height
        nut_hole = cylinder(d=self.nut_diameter, h=self.nut_height, segments=6)
        nut_hole = translate([0,0,nut_z_pos])(nut_hole)
        nut_hole += translate([0,0,nut_z_pos - layer_height])(linear_extrude(layer_height)(
            square([self.thread_diameter, self.nut_diameter], center=True)))
        nut_hole += translate([0,0,nut_z_pos - 2 * layer_height])(linear_extrude(layer_height)(
            square([self.thread_diameter, self.thread_diameter], center=True)))
        thread_hole = cylinder(d=self.thread_diameter, h=self.thread_height, segments=30)
        thread_hole = translate([0,0,self.z_elevation + self.head_height])(thread_hole)
        return translate(self.xy_pos)(nut_hole + thread_hole)

    def make_bot_hole(self):
        # use the same trick as in make_top_hole()
        head_hole_height = self.head_height + self.z_elevation
        cyl = cylinder(d=self.head_diameter, h=head_hole_height, segments=30)
        cyl += up(head_hole_height)(linear_extrude(layer_height)(
            square([self.thread_diameter,self.head_diameter], center=True)))
        cyl += up(head_hole_height+layer_height)(linear_extrude(layer_height)(
            square([self.thread_diameter,self.thread_diameter], center=True)))
        cyl += translate([0,0,head_hole_height + 2 * layer_height])(
            cylinder(d=self.thread_diameter, h=self.thread_height, segments=30))
        return translate(self.xy_pos)(cyl)

    def make_top_shape(self):
        cyl = cylinder(d = self.pillar_diam, h = self.thread_height - self.extra_support_height_bot - layer_height, segments=20)
        cyl = translate([0,0,self.head_height + self.extra_support_height_bot + self.z_elevation + layer_height])(cyl)
        return translate(self.xy_pos)(cyl)

    def make_bot_shape(self):
        head_hole_height = self.head_height + self.z_elevation
        cyl = cylinder(d=self.pillar_diam, h=head_hole_height + self.extra_support_height_bot, segments=20)
        return translate(self.xy_pos)(cyl)

class JackSocket:
    outer_cyl_diam = 7.2
    outer_cyl_height = 5
    inner_cyl_1_diam = 9.2
    inner_cyl_1_height = 1.8
    inner_cyl_2_diam = 8
    inner_cyl_2_height = 10

    hex_nut_small_width = 10
    hex_nut_diam = hex_nut_small_width * 2.3094 / 2
    hex_nut_height = 2

    def __init__(self, pos, height, nut_offset):
        self.pos = pos
        self.height = height
        self.nut_offset = nut_offset

    def make_shape(self):
        res = cube(0)
        res += translate([0,0,-self.nut_offset-self.hex_nut_height])(
            rotate([0,0,90])(cylinder(d=self.hex_nut_diam, h=self.hex_nut_height, segments=6))
        )
        res += translate([0,0,-self.outer_cyl_height])(
            cylinder(d=self.outer_cyl_diam, h=self.outer_cyl_height, segments=30)
        )
        res += translate([0,0,0])(
            cylinder(d=self.inner_cyl_1_diam, h=self.inner_cyl_1_height, segments=30)
        )
        res += translate([0,0,self.inner_cyl_1_height])(
            cylinder(d=self.inner_cyl_2_diam, h=self.inner_cyl_2_height, segments=30)
        )
        res = rotate([0,-90,0])(res)
        res = translate(self.pos)(translate([0,0,self.height])(res))
        return res

    def make_bot_hole(self):
        res = translate([0,0,-self.outer_cyl_height])(
            cylinder(
                d=max(self.inner_cyl_1_diam, self.inner_cyl_2_diam),
                h=self.inner_cyl_1_height + self.inner_cyl_2_height + self.outer_cyl_height + 1,
                segments=40)
        )
        res = rotate([0,-90,0])(res)
        res = translate(self.pos)(translate([0,0,self.height])(res))
        return res

    def make_top_hole(self):
        res = cube(0)
        #res += translate([0,0,-self.nut_offset-self.hex_nut_height])(
        #    rotate([0,0,90])(cylinder(d=self.hex_nut_diam, h=self.hex_nut_height, segments=6))
        #)
        res += translate([0,0,-self.outer_cyl_height])(
            cylinder(d=self.outer_cyl_diam, h=self.outer_cyl_height, segments=40)
        )
        res += translate([0,0,0])(
            cylinder(
                d=max(self.inner_cyl_1_diam, self.inner_cyl_2_diam),
                h=self.inner_cyl_1_height + self.inner_cyl_2_height + 1,
                segments=40)
        )
        res = rotate([0,-90,0])(res)
        res = translate(self.pos)(translate([0,0,self.height])(res))
        return res

class Support:
    switch_nub_depth = 5.2 # for kailh choc
    switch_nub_diameter = 2.5

    def __init__(self, pos, height):
        self.pos = pos
        self.height = height

    def make_shape(self):
        return translate(self.pos)(
            cylinder(
                d=self.switch_nub_diameter,
                h=self.height - self.switch_nub_depth,
                segments=20
            )
        )

def make_channel(points, diam, segments):
    prev = cube(0)
    res = cube(0)
    line = cube(0)
    s = down(diam/2)(cylinder(d=diam, h=diam + eps, segments=15))
    for p in range(len(points) - 1):
        p1 = points[p]
        p2 = points[p+1]
        line += hull()(translate(p1)(s) + translate(p2)(s))
    return line

class SolderingJig:
    mid_nub_diam = 3
    aux_nub_diam = 1.5
    aux_nub_dist = 5.2
    top_pin_dist = 5.5
    left_pin_x_dist = 5
    left_pin_y_dist = 3.8
    pin_diam = 1
    wire_diam = 1.35
    diode_diam = 2.1
    diode_len = 3.5
    diode_wire_diam = .7

    def __init__(self, switches_pos, type, choc):
        self.switches_pos = switches_pos
        self.type = type
        self.choc = choc

    def make_shape(self):
        plate_height = 3
        holes = cube(0)
        plates = cube(0)
        channel = cube(0)

        if self.type == 'diode':
            res = cube([46, 10, 3])
            res += translate([0,10,0])(cube([8, 4, 4]))
            res -= translate([0,12,2.2])(rotate([0,90,0])(cylinder(d=2, h=8,segments=20)))
            diode = (rotate([-90,0,0])(cylinder(d=self.diode_diam, h=self.diode_len, segments=20)) +
                rotate([90,0,0])(down(50)(cylinder(d=self.diode_wire_diam, h=100, segments=20)))
            )

            for i in range(6):
                res -= translate([12 + i * 6, 5, plate_height])(diode)
            return res

        prev_plate = None
        for i in range(len(self.switches_pos)):
            p = self.switches_pos[i]
            plate = translate(p)(
                (translate([-8,-7])(cube([7,14,plate_height])))
                if self.type == 'vertical' else
                translate([-7,-7])(cube([14,9,plate_height]))
            )
            if prev_plate:
                plates += hull()(prev_plate + plate)
            prev_plate = plate

        if self.type == 'vertical':
            for i in range(len(self.switches_pos)):
                p = self.switches_pos[i]
                pos = [-self.left_pin_x_dist, self.left_pin_y_dist]
                channel += translate(p)(translate(pos)(down(self.wire_diam/2)(
                    cylinder(d=3, h=self.wire_diam+eps, segments=20))))
                holes += translate(p)(translate(pos)(cylinder(d=1.7, h=100, segments=20)))
        elif self.type == 'horizontal':
            for i in range(len(self.switches_pos)):
                p = self.switches_pos[i]
                pos = [4, -4]
                plates += translate(p)(translate([4-4/2,-2.5])(
                    cube([4,5,plate_height + .6])))
                holes += translate(p)(translate([4-4/2,-10])(
                    cube([4,7.5,plate_height])))
                channel += translate(p)(translate(pos)(rotate([90,0,0])(
                    down(50)(cylinder(d=1.8, h=100, segments=20)))))

        wire_curve_points = []
        for i in range(len(self.switches_pos)):
            p = self.switches_pos[i]
            if self.type == 'vertical':
                if i == 0:
                    wire_curve_points.append(sum_coords(p, [-8, -3]))
                    wire_curve_points.append(["SHARP"])
                    wire_curve_points.append(["RELATIVE", 0, -2])
                else:
                    wire_curve_points.append(["SHARP"])
                    wire_curve_points.append(["SHARP"])
                wire_curve_points.append(sum_coords(p, [-self.aux_nub_dist +self.aux_nub_diam/2 + self.wire_diam/2, 0]))
                wire_curve_points.append(["RELATIVE", 0, 1])
                wire_curve_points.append(["RELATIVE", 0, -1])
                wire_curve_points.append(sum_coords(p, [-self.left_pin_x_dist-.4, self.left_pin_y_dist]))
                if i == len(self.switches_pos) - 1:
                    wire_curve_points.append(["SHARP"])
                    wire_curve_points.append(["SHARP"])
                    wire_curve_points.append(sum_coords(p, [-5,7]))
            elif self.type == 'horizontal':
                if i == 0:
                    wire_curve_points.append(sum_coords(p, [-7, -4]))
                    wire_curve_points.append(["SHARP"])
                wire_curve_points.append(["RELATIVE", -12, 0])
                wire_curve_points.append(sum_coords(p, [4, -4]))
                wire_curve_points.append(["RELATIVE", 12, 0])
                if i == len(self.switches_pos) - 1:
                    wire_curve_points.append(["SHARP"])
                    wire_curve_points.append(sum_coords(p, [7, -4]))

        channel += make_channel(bezier_lines(wire_curve_points, 0.1), diam = self.wire_diam, segments=20)

        channel = up(plate_height)(channel)
        channel = down(self.wire_diam/2)(channel)
        #holes = holes + up(.2)(holes) + up(.4)(holes)
        return (plates - channel - holes)

def make_top_and_bot(
        shape_no_holes,
        top_shape,
        top_height,
        top_things,
        top_holes,
        bot_shape,
        bot_height,
        bot_things,
        bot_holes,
        wall_full_width,
        wall_outer_width,
        bottom_recess,
        height,
    ):
    bot_shape = offset(delta=-wall_outer_width)(bot_shape)
    bot = linear_extrude(height=bot_height, convexity=2)(bot_shape)
    bot += bot_things
    bot -= bot_holes
    bot *= linear_extrude(height=height, convexity=2)(bot_shape) # cut off protruding things (screws, for example

    wall = linear_extrude(height=height, convexity=2)(
        shape_no_holes - offset(delta=-wall_full_width)(shape_no_holes))

    top = linear_extrude(height=top_height, convexity=2)(top_shape)
    top = translate([0,0,height-top_height])(top)
    top += (wall - bot) # make sure that the wall does not overlap with the bottom
    top += top_things
    top -= top_holes
    #top -= bot_holes
    bot *= linear_extrude(height=height, convexity=2)(offset(delta=-bottom_recess)(bot_shape))

    return top, bot

def main() -> int:
    shell_offset = 1 # the 'border'
    keycap_dist = [1,1]
    switch_hole_size = [13.7,13.7]
    thumb_keycap_spacing = .4
    height = 10 # total height, including bot and top plates
    top_height = 2
    bot_height = 2
    wall_inner_width = 1 # the bottom plate is below the 'inner' wall
    wall_outer_width = 1 # but not below the out wall, which encloses it
    bottom_recess = 0.04 # shrink the bottom plate by this much all around, so that the fit is
                         # not as tight
    rows = 4
    columns = 6
    column_stagger = [0, 0, 4.5, 9, 4.5, 18 * .15]
    thumb_cluster_key_count = 4
    roundness = 1
    precision = 0.01
    right_hand = True
    choc_switches = True
    keycap_size = [18,17 if choc_switches else 18]

    choc_shape = (cube(0)
        + translate([-7,-7,-2.2])(cube([14,14,2.2])) # bottom
        + translate([-7.5,-7.5,0])(cube([15,15,.8])) # lip
        + translate([-7,-7,.8])(cube([14,14,2])) # top
        + translate([-10.3/2,-4.5/2,2.8])(cube([10.3,4.5,3])) # actuator
        + translate([-9,-8.5,11-2.2-4])(linear_extrude(height=4)(offset(r=1)(offset(r=-1)(square([18,17]))))) # cap
    )
    mx_shape = (cube(0)
        + translate([-7,-7,-4.5])(cube([14,14,4.5])) # bottom
        + translate([-15.6/2,-15.6/2,0])(cube([15.6,15.6,1])) # lip
        + up(1)(hull()( # top
            translate([-14/2,-14/2])(cube([14,14,eps]))
            + translate([-10/2,-10/2,5.4])(cube([10,10,eps]))
            )) # cap
        + translate([-4/2,-4/2,6.4])(cube([4,4,4.5])) # actuator
        + up(14-8)(hull()( # cap
            translate([-18.3/2,-18.3/2])(cube([18.3,18.3,eps]))
            + translate([-12/2,-12/2,8])(cube([12,12,eps]))
            )) # cap
    )
    switch_and_keycap = choc_shape if choc_switches else mx_shape

    tc = ThumbCluster(
        key_count = thumb_cluster_key_count,
        #bezier_points = [ [0,0], ["POLAR", 3, -5], ["POLAR", 3, 125], [7,-4] ],
         bezier_points = [ [0,0], ["POLAR", 30, -5], ["POLAR", 30, 122], [67.5,-42.5] ],
        #bezier_points = [ [0,0], ["POLAR", 3, -5], ["POLAR", 3, 120], [6.5,-4.5] ],
        #bezier_points = [ [0,0], ["POLAR", 3, -10], ["POLAR", 2, 115], [5.5,-4.5] ],
        keycap_size = keycap_size,
        keycap_spacing = thumb_keycap_spacing,
        switch_hole_size = switch_hole_size,
        #position = [77, -12.5],
         position = [77, -14],
        offset = shell_offset,
        precision = precision,
    )

    sh = Shell(rows = rows,
        columns = columns,
        keycap_size = keycap_size,
        keycap_dist = keycap_dist,
        switch_hole_size = switch_hole_size,
        thumb_cluster = tc,
        column_stagger = column_stagger,
        shell_offset = shell_offset,
        precision = precision,
    )

    wall_full_width=wall_outer_width + wall_inner_width

    jack = JackSocket(
        pos = [sh.panel_right() - wall_full_width , 6],
        height = height/2,
        nut_offset = wall_full_width,
    )

    controller = Controller(
        pos = [sh.panel_right() - wall_full_width,sh.panel_top()],
        usb_top_height = height - top_height,
        total_height = height,
        pillar_diam = 4,
        mirror = right_hand,
    )

    weights = []
    for pos in [
        [22,20], [22, 56],
        [60,21], [60, 60],
        [98,10],
        #[98,55], # maybe?
    ]:
        weights.append(WeightedDisc(
            pos = pos,
            number = 1,
            extra_diam = 2,
            disc_dist_from_bot = 0.4,
            disc_dist_to_top = 0.4))

    screws = []
    for pos in [
        [40,4],      # bot left
        [35,74],     # top left
        [77.5,78.2], # top right
        [132,17],    # bot right
        [133,-19],   # bot right
    ]:
        screws.append(Screw(
            xy_pos = pos,
            pillar_diam = 7,
            z_elevation = 1))

    supports = []
    for row in range(rows):
        for col in range(columns):
            supports.append(Support(
                pos = sh.get_key_position(row = row, col = col, center=True),
                height = height,
            ))
    for c in range(thumb_cluster_key_count):
        pos = tc.get_key_coord(c)[0]
        supports.append(Support(pos = pos, height = height))

    shape = polygon(points = sh.get_shape_points() + tc.get_shape_points(), convexity=4)
    if roundness > 0:
        shape = offset(r=roundness,segments=20)(offset(r=-roundness,segments=20)(shape))

    top_things = cube(0)
    top_things += controller.make_top_support()
    for screw in screws:
        top_things += screw.make_top_shape()

    top_holes = cube(0)
    top_holes += jack.make_top_hole()
    top_holes += controller.make_top_hole()
    for screw in screws:
        top_holes += screw.make_top_hole()

    bot_things = cube(0)
    for weight in weights:
        bot_things += weight.make_shape()
    for screw in screws:
        bot_things += screw.make_bot_shape()
    for support in supports:
        bot_things += support.make_shape()
    bot_things += controller.make_bottom_support()

    bot_holes = cube(0)
    bot_holes += jack.make_bot_hole()
    for weight in weights:
        bot_holes += weight.make_discs()
    for screw in screws:
        bot_holes += screw.make_bot_hole()

    top, bot = make_top_and_bot(
        shape_no_holes = shape,
        top_shape = shape - (tc.make_switch_holes() + sh.make_switch_holes()),
        top_things = top_things,
        top_holes = top_holes,
        bot_shape = shape,
        bot_things = bot_things,
        bot_holes = bot_holes,
        wall_full_width = wall_full_width,
        wall_outer_width = wall_outer_width,
        top_height = top_height,
        bot_height = bot_height,
        bottom_recess = bottom_recess,
        height = height,
    )

    alphanum_keys = cube(0)
    other_keys = cube(0)
    for i, pos in enumerate(sh.switches_positions()):
        key = up(height)(translate(pos[0])(rotate([0,0,pos[1]])(switch_and_keycap)))
        if i % 6 == 0:
            other_keys += key
        else:
            alphanum_keys += key
    for pos in tc.switches_positions():
        other_keys += up(height)(translate(pos[0])(rotate([0,0,pos[1]])(switch_and_keycap)))
    phantoms = cube(0)
    phantoms += controller.make_shape()
    phantoms += jack.make_shape()

    black = "#404040"
    white = "#ffffff"
    beige = "#eadebb"
    gold = "#ffdf00"
    gray = "#c9c9c9"
    dark_gray = "#9a9a9a"
    color_shell = black
    color_middle_shell = beige
    color_bottom_shell = black
    color_alnum_keys = white
    color_other_keys = gray

    color_strip_height = 1.4
    top = color(color_shell)(top)
    top_middle = color(color_middle_shell)(up(color_strip_height)(linear_extrude(height - 2 * color_strip_height)(
        offset(r=10 * eps)(projection(cut=True)(top)))))
    top_bottom = color(color_bottom_shell)(linear_extrude(color_strip_height)(offset(r=10 * eps)(projection(cut=True)(top))))
    bot = color(color_bottom_shell)(bot)
    keys = color(color_alnum_keys)(alphanum_keys) + color(color_other_keys)(other_keys)
    phantoms = color(gray)(phantoms)

    phantoms = phantoms.set_modifier('%')
    keys = keys.set_modifier('%')

    out = (cube(0)
         + top
         + top_middle
         + top_bottom
         #+ bot
         + phantoms
         + keys
    )

    if right_hand:
        out = scale([-1,1,1])(out)

    jig = SolderingJig(
        switches_pos = [sh.get_key_position(row = r, col = 0, center=True) for r in range(rows)],
        type = 'vertical',
        choc = choc_switches
    )
    jig2 = SolderingJig(
        switches_pos = [sh.get_key_position(row = 0, col = c, center=True) for c in range(columns)],
        type = 'horizontal',
        choc = choc_switches
    )
    jig3 = SolderingJig(
        switches_pos = [],
        type = 'diode',
        choc = choc_switches
    )
    #out = (cube(0)
    #     + jig.make_shape()
    #     + right(30)(jig2.make_shape())
    #     + translate([30,30])(jig3.make_shape())
    #)

    scad_render_to_file(out, "out.scad")


    return 0

if __name__ == '__main__':
    sys.exit(main())
