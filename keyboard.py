#!/bin/python

from solid import *
from solid.utils import *
import sys
import math
import bezier
import triangle as tr

eps = 0.001

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
    res = []
    x = 0
    while True:
        p = curve.evaluate(x)
        res.append([p[0][0], p[1][0]])
        if x == 1.0:
            break
        x = min(x + precision, 1.0)
    return res

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

def bezier_closed_line(points, precision):
    if len(points) < 6 or len(points) % 3 != 0:
        raise ValueError
    res = []
    offset = 0
    while offset < len(points):
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
            res += sample_bezier_evenly(curve, precision)
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
            keycap_dist,
            switch_hole_size,
            precision):
        self.key_count = key_count
        self.keycap_size = keycap_size
        self.keycap_dist = keycap_dist
        self.switch_hole_size = switch_hole_size
        self.switch_hole_dist = diff_coords(
            sum_coords(self.keycap_size, self.keycap_dist), self.switch_hole_size)
        points_converted, _ = convert_bezier_points(bezier_points)
        self.bezier_curve = bezier_from_points(points_converted)
        self.curve_target_length = (key_count - 1) * (self.keycap_size[0] + self.keycap_dist[0])
        self.curve_scale_factor = self.curve_target_length / self.bezier_curve.length
        self.thumb_curve_points = sample_bezier_evenly(self.bezier_curve, precision)
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
            t1 = self.thumb_curve_points[i]
            t2 = self.thumb_curve_points[i+1]
            seg_length = math.sqrt((t1[0] - t2[0]) ** 2 + (t1[1] - t2[1]) ** 2)
            t = None
            if i == 0:
                t = 0
            elif i + 1 == len(self.thumb_curve_points) - 1:
                t = 1
            elif length % dist_between_keys_center > (length + seg_length) % dist_between_keys_center:
                t = 1 - ((length + seg_length) % dist_between_keys_center) / seg_length
            if t is not None:
                m = [(1 - t) * t1[0] + t * t2[0], (1 - t) * t1[1] + t * t2[1]]
                angle = math.atan2(t2[1] - t1[1], t2[0] - t1[0])
                res.append([m, angle])
            length += seg_length
        return res

    def get_line(self):
        line = cube(0)
        for i in range(0,len(self.thumb_curve_points)-1):
            line += line2d.line2d(
                self.thumb_curve_points[i],
                self.thumb_curve_points[i+1],
                width=1)
        return line

    def get_key_coord(self, key_index, tangent_offset, perpendicular_offset):
        thumb_keys_pos = self.get_thumb_keys_pos()
        key = thumb_keys_pos[key_index]
        cap_angle = key[1]
        cap_bottom_middle = key[1]
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
            vec = \
                diff_coords(self.thumb_curve_points[i+1], self.thumb_curve_points[i]) \
                if i < len(self.thumb_curve_points) - 1 else \
                diff_coords(self.thumb_curve_points[i], self.thumb_curve_points[i-1])
            angle = math.atan2(vec[1], vec[0])
            angle += math.pi/2
            offset_perp = self.keycap_size[1]/2
            pos = sum_coords(pos, [math.cos(angle) * offset_perp, math.sin(angle) * offset_perp])
            rot = rotate([0,0,angle/math.pi*180])(obj)
            shape += translate(pos)(rot)
        return shape


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
                ["RELATIVE", 0, 40], # random control points
                ["RELATIVE", 40, 0], # random control points
            self.thumb_cluster.get_bottom_left(),
                ["RELATIVE", 0, 15],
                ["RELATIVE", 5, 0],
            sum_coords(self.get_key_position(0,0), [2*self.keycap_size[1], -shell_offset]),
                ["SHARP"],
                ["SHARP"],
        ]

        self.bezier_curve = bezier_closed_line(casepoints, self.precision)


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

    def make_shape(self):
        bez = self.bezier_curve
        segments=[[i, (i+1)%len(bez)] for i in range(0,len(bez))]
        tris = tr.triangulate({'vertices':bez, 'segments': segments}, 'p')
        shape = square(0)
        for tri in tris['triangles'].tolist():
            shape += polygon([bez[tri[0]], bez[tri[1]], bez[tri[2]]])
        return shape

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
    disc_diam=35.4
    disc_hole_diam=9

    def __init__(self, pos, number, extra_diam, disc_dist_from_bot, disc_dist_to_top):
        self.pos = pos
        self.number_discs = number
        self.extra_diam = extra_diam
        self.disc_dist_from_bot = disc_dist_from_bot
        self.disc_dist_to_top = disc_dist_to_top

    def make_discs(self):
        discs = cylinder(d=self.disc_diam, h=self.number_discs * self.disc_height, segments=40)
        discs -= cylinder(d=self.disc_hole_diam, h=self.number_discs * self.disc_height, segments=40)
        return translate([0,0,self.disc_dist_from_bot])(translate(self.pos)(discs))

    def get_diameter(self):
        return self.disc_diam + self.extra_diam

    def make_shape(self):
        return translate(self.pos)(cylinder(d = self.disc_diam + self.extra_diam,
            h = self.number_discs * self.disc_height + self.disc_dist_from_bot + self.disc_dist_to_top, segments=40))

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

    def __init__(self, pos, height, total_height, pillar_diam):
        self.pos = pos
        self.height = height
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
        return translate(self.pos)(translate([0,0,self.height if with_height else 0])(obj))

    def make_bottom_support(self):
        res = cube(0)
        for x in [self.holes_dist_to_side_edge, self.board_width - self.holes_dist_to_side_edge]:
            for y in [self.holes_dist_to_top_edge, self.board_length - self.holes_dist_to_top_edge]:
                res += translate([x,y])(cylinder(d=self.pillar_diam, h=self.height,segments=20))
        return self.move_into_place(res, with_height = False)

    def make_top_support(self):
        res = cube(0)
        for x in [self.holes_dist_to_side_edge, self.board_width - self.holes_dist_to_side_edge]:
            for y in [self.holes_dist_to_top_edge, self.board_length - self.holes_dist_to_top_edge]:
                res += translate([x,y])(cylinder(d=self.holes_diam, h=self.board_height, segments=20))
                res += translate([x,y,self.board_height])(
                    cylinder(d=self.pillar_diam, h=self.total_height - self.height - self.board_height, segments=20))
        return self.move_into_place(res)

class Screw:
    thread_diameter = 2
    thread_height = 6
    head_height = 2
    head_diameter = 3.9

    nut_height = 1.2
    nut_flat_width = 4.1

    extra_support_height_bot = 1

    nut_diameter = 2.3094 * nut_flat_width / 2
    nut_holder_diameter =  1.2 * nut_diameter

    def __init__(self, xy_pos, pillar_diam, z_elevation, top_height):
        self.xy_pos = xy_pos
        self.pillar_diam = pillar_diam
        self.z_elevation = z_elevation
        self.top_height = top_height

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
        cyl = cylinder(d = self.pillar_diam, h = self.thread_height - self.extra_support_height_bot, segments=20)
        cyl = translate([0,0,self.head_height + self.extra_support_height_bot + self.z_elevation])(cyl)
        return translate(self.xy_pos)(cyl)

    def make_bot_shape(self):
        head_hole_height = self.head_height + self.z_elevation
        cyl = cylinder(d=self.pillar_diam, h=head_hole_height + self.extra_support_height_bot, segments=20)
        return translate(self.xy_pos)(cyl)

class JackSocket:
    outer_cyl_diam = 7
    outer_cyl_height = 5
    inner_cyl_1_diam = 9
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
            cylinder(d=self.outer_cyl_diam, h=self.outer_cyl_height, segments=20)
        )
        res += translate([0,0,0])(
            cylinder(d=self.inner_cyl_1_diam, h=self.inner_cyl_1_height, segments=20)
        )
        res += translate([0,0,self.inner_cyl_1_height])(
            cylinder(d=self.inner_cyl_2_diam, h=self.inner_cyl_2_height, segments=20)
        )
        res = rotate([0,-90,0])(res)
        res = translate(self.pos)(translate([0,0,self.height])(res))
        return res

    def make_hole(self):
        res = cube(0)
        #res += translate([0,0,-self.nut_offset-self.hex_nut_height])(
        #    rotate([0,0,90])(cylinder(d=self.hex_nut_diam, h=self.hex_nut_height, segments=6))
        #)
        res += translate([0,0,-self.outer_cyl_height])(
            cylinder(d=self.outer_cyl_diam, h=self.outer_cyl_height, segments=20)
        )
        res += translate([0,0,0])(
            cylinder(
                d=max(self.inner_cyl_1_diam, self.inner_cyl_2_diam),
                h=self.inner_cyl_1_height + self.inner_cyl_2_height + 1,
                segments=20)
        )
        res = rotate([0,-90,0])(res)
        res = translate(self.pos)(translate([0,0,self.height])(res))
        return res

def main() -> int:
    shell_offset = 1 # the 'border'
    keycap_size = [18,18]
    keycap_dist = [1,1]
    switch_hole_size = [14,14]

    tc = ThumbCluster(
        key_count = 4,
        bezier_points = [
            [0,0],
                ["POLAR", 3, -5],
                ["POLAR", 3, 125],
            [7,-4]
        ],
        keycap_size = keycap_size,
        keycap_dist = keycap_dist,
        switch_hole_size = switch_hole_size,
        position = [77, -14],
        offset = shell_offset,
        precision = 0.08
    )

    sh = Shell(rows = 4,
        columns = 6,
        keycap_size = keycap_size,
        keycap_dist = keycap_dist,
        switch_hole_size = switch_hole_size,
        thumb_cluster = tc,
        column_stagger = [0,  0,  0.25,  0.5,  0.25,  0.15],
        shell_offset = shell_offset,
        precision = 0.08
    )

    height=10
    top_height=2
    bot_height=2
    wall_outer_width=1
    wall_inner_width=1
    wall_full_width=wall_outer_width + wall_inner_width

    jack = JackSocket(
        pos = [sh.panel_right() - wall_full_width , 10],
        height = height/2,
        nut_offset = wall_full_width,
    )

    controller = Controller(
        pos = [sh.panel_right() - wall_full_width,sh.panel_top()],
        height = height/3,
        total_height = height,
        pillar_diam = 4,
    )

    weights = []
    for pos in [
        [22,21], [22, 57],
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
    for pos in [[40,4], [35,78], [77.8,82.2], [132,-4]]:
        screws.append(Screw(
            xy_pos = pos,
            pillar_diam = 7,
            z_elevation = 1,
            top_height = 1))

    shape = square(0)
    shape += tc.make_shape()
    shape += sh.make_shape()

    wall_inner = translate([0,0,bot_height])(linear_extrude(height=height - bot_height)(
        offset(delta=-wall_outer_width)(shape) - offset(delta=-wall_full_width)(shape)
    ))
    wall_outer = linear_extrude(height=height)(
        shape - offset(delta=-wall_outer_width)(shape)
    )
    jack_hole = jack.make_hole()
    wall = wall_inner + wall_outer

    bot_shape = offset(delta=-wall_outer_width)(shape)
    bot = linear_extrude(height=bot_height)(bot_shape)
    bot -= jack_hole
    for weight in weights:
        bot += weight.make_shape()
    for screw in screws:
        bot += screw.make_bot_shape()
    for weight in weights:
        bot -= weight.make_discs()
    for screw in screws:
        bot -= screw.make_bot_hole()
    bot += controller.make_bottom_support()
    bot *= linear_extrude(height=height)(bot_shape)

    switch_holes = tc.make_switch_holes() + sh.make_switch_holes()

    top = linear_extrude(height=top_height)(shape - switch_holes)
    top = translate([0,0,height-top_height])(top)
    top += (wall - bot)
    top += controller.make_top_support()
    for screw in screws:
        top += screw.make_top_shape()
    top -= jack_hole
    top -= controller.make_usb_hole()
    for screw in screws:
        top -= screw.make_top_hole()

    keycaps = tc.make_keycaps() + sh.make_keycaps()
    phantoms = cube(0)
    phantoms += translate([0,0,4])(linear_extrude(height=2)(keycaps))
    phantoms += linear_extrude(height=4)(switch_holes)
    phantoms = translate([0,0,height-top_height])(phantoms)
    phantoms += controller.make_shape()
    phantoms += jack.make_shape()
    phantoms = phantoms.set_modifier('%')

    #top *= translate([113,25])(cube([50,100,50])) # test the controller
    #top *= translate([116,0])(cube([50,20,50])) # test the jack
    #bot *= translate([0,0])(cube([43,42,50]))
    scad_render_to_file(cube(0)
        + top
        + phantoms
        + bot
    , "out.scad")

    return 0

if __name__ == '__main__':
    sys.exit(main())
