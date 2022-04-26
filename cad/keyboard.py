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

    def make_keycaps(self):
        shape = square(0)
        for i in range(0, self.get_key_count()):
            key_pos, key_angle = self.get_key_coord(i, 0, 0)
            shape += translate(key_pos)(rotate([0,0,key_angle / math.pi * 180])(
                square(self.keycap_size, center=True)))
        return shape

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
                ["POLAR", 12, 125],
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
                (row + self.column_stagger[col]) * (self.switch_hole_size[1] + self.switch_hole_dist[1]),
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

    def make_keycaps(self):
        res = square(0)
        for row in range(0, self.rows):
            for col in range(0, self.columns):
                key_pos = self.get_key_position(row,  col,  center=True)
                res += translate(key_pos)(square(self.keycap_size, center=True))
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

    button_dist_to_left = 7
    button_dist_to_top = 12.5

    usb_height = 3.2
    usb_width = 8.5
    usb_length = 5.7

    usb_protursion = 1.5

    board_edge_to_cable_shell = 2.5 # distance between board edge to cable shell
    usb_bottom_from_board_bottom = 0.5 # distance from board bottom to usb socket bottom

    def __init__(self, pos, usb_top_height, total_height, pillar_diam):
        self.pos = pos
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

    def make_usb_hole(self):
        usb = cube([self.usb_width, self.usb_length * 2, self.usb_height])
        usb = translate([self.board_width/2-self.usb_width/2, 0])(usb)
        usb = translate([0, self.board_length - self.usb_length + self.usb_protursion])(usb)
        usb = translate([0,0,self.usb_bottom_from_board_bottom])(usb)

        return self.move_into_place(usb)

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
        nut_z_pos = self.z_elevation + self.head_height + self.thread_height - self.nut_height
        nut_hole = cylinder(d=self.nut_diameter, h=self.nut_height, segments=6)
        res = translate([0,0,nut_z_pos])(nut_hole)
        thread_hole = cylinder(d=self.thread_diameter, h=self.thread_height, segments=20)
        res += translate([0,0,self.z_elevation + self.head_height])(thread_hole)
        return translate(self.xy_pos)(res)

    def make_bot_hole(self):
        head_hole_height = self.head_height + self.z_elevation
        cyl = cylinder(d=self.head_diameter, h=head_hole_height, segments=20)
        cyl += translate([0,0,head_hole_height])(cylinder(d=self.thread_diameter, h=self.thread_height, segments=20))
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
    bot = linear_extrude(height=bot_height)(bot_shape)
    bot += bot_things
    bot -= bot_holes
    bot *= linear_extrude(height=height)(bot_shape) # cut off protruding things (screws, for example

    wall = linear_extrude(height=height)(shape_no_holes - offset(delta=-wall_full_width)(shape_no_holes))

    top = linear_extrude(height=top_height)(top_shape)
    top = translate([0,0,height-top_height])(top)
    top += (wall - bot) # make sure that the wall does not overlap with the bottom
    top += top_things
    top -= top_holes
    bot *= linear_extrude(height=height)(offset(delta=-bottom_recess)(bot_shape))

    return top, bot

def main() -> int:
    shell_offset = 1 # the 'border'
    keycap_size = [18,17]
    keycap_dist = [1,1]
    switch_hole_size = [13.7,13.7]
    thumb_keycap_spacing = 1
    height = 10 # total height, including bot and top plates
    top_height = 2
    bot_height = 2
    wall_inner_width = 1 # the bottom plate is below the 'inner' wall
    wall_outer_width = 1 # but not below the out wall, which encloses it
    bottom_recess = 0.00 # shrink the bottom plate by this much all around, so that the fit is
                         # not as tight
    rows = 4
    columns = 6
    thumb_cluster_key_count = 4
    roundness = 1
    precision = 0.01

    tc = ThumbCluster(
        key_count = thumb_cluster_key_count,
        bezier_points = [
            [0,0],
                ["POLAR", 3, -5],
                ["POLAR", 3, 125],
            [7,-4]
        ],
        keycap_size = keycap_size,
        keycap_spacing = thumb_keycap_spacing,
        switch_hole_size = switch_hole_size,
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
        column_stagger = [0,  0,  0.25,  0.5,  0.25,  0.15],
        shell_offset = shell_offset,
        precision = precision,
    )

    wall_full_width=wall_outer_width + wall_inner_width

    jack = JackSocket(
        pos = [sh.panel_right() - wall_full_width , 10],
        height = height/2,
        nut_offset = wall_full_width,
    )

    controller = Controller(
        pos = [sh.panel_right() - wall_full_width,sh.panel_top()],
        usb_top_height = height - top_height,
        total_height = height,
        pillar_diam = 4,
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
        [77.8,78.2], # top right
        [132,-4]     # bot right
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
    top_holes += controller.make_usb_hole()
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

    keycaps = tc.make_keycaps() + sh.make_keycaps()
    phantoms = cube(0)
    phantoms += translate([0,0,4])(linear_extrude(height=2)(
        tc.make_keycaps() + sh.make_keycaps()))
    phantoms += linear_extrude(height=4)(
        tc.make_switch_holes() + sh.make_switch_holes())
    phantoms = translate([0,0,height-top_height])(phantoms)
    phantoms += controller.make_shape()
    phantoms += jack.make_shape()
    phantoms = phantoms.set_modifier('%')

    #plate = square([20,20]);
    #screw = Screw(
    #        xy_pos = [10,10],
    #        pillar_diam = 7,
    #        z_elevation = 1,
    #        top_height = 1)
    #top, bot = make_top_and_bot(
    #    shape_no_holes = plate,
    #    top_shape = plate,
    #    top_things = screw.make_top_shape(),
    #    top_holes = screw.make_top_hole() + right(18)(cube([20,20,20])),
    #    bot_shape = plate,
    #    bot_things = screw.make_bot_shape(),
    #    bot_holes = screw.make_bot_hole() + right(18)(cube([20,20,20])),
    #    wall_full_width = wall_full_width,
    #    wall_outer_width = wall_outer_width,
    #    top_height = top_height,
    #    bot_height = bot_height,
    #    bottom_recess = 0.04,
    #    height = height,
    #)
    #plate = square([30,60])
    #controller = Controller(pos = [25,60], usb_top_height = height - top_height - .4, total_height=height, pillar_diam=4)
    #top, bot = make_top_and_bot(
    #   shape_no_holes = plate,
    #   top_shape = plate,
    #   top_things = controller.make_top_support(),
    #   top_holes = controller.make_usb_hole() + right(28)(cube([100,100,100])),
    #   bot_shape = plate,
    #   bot_things = controller.make_bottom_support(),
    #   bot_holes = right(28)(cube([100,100,100])),
    #   wall_full_width = wall_full_width,
    #   wall_outer_width = wall_outer_width,
    #   top_height = top_height,
    #   bot_height = bot_height,
    #   bottom_recess = bottom_recess,
    #   height = height,
    #)

    out = (cube(0)
        + up(10)(top)
        + up(10)(phantoms)
        + bot
    )

    # add mirrored part
    #out = out + translate([320,0,0])(scale([-1,1,1])(out))

    scad_render_to_file(out, "out.scad")


    return 0

if __name__ == '__main__':
    sys.exit(main())
