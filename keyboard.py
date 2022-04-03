#!/bin/python

from solid import *
from solid.utils import *
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

def make_switch_hole(pos, angle, switch_hole_size, keycap_size):
    switch = square(switch_hole_size, center=True).set_modifier('#')
    #cap = translate([0,0,3])(
    #            square(keycap_size, center=True))).set_modifier('#')
    return  translate(pos)(rotate([0,0,angle / math.pi * 180])(switch))


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
        obj = square([self.keycap_size[0] + 2 * self.offset, self.keycap_size[1] + 2 * self.offset], center=True)
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
        for i in range(0, tc.get_key_count()):
            key_pos, key_angle = tc.get_key_coord(i, 0, 0)
            #(pos, angle, height, switch_hole_size, keycap_size)
            shape += make_switch_hole(
                key_pos,
                key_angle,
                self.switch_hole_size,
                self.keycap_size)
        return shape

    def make_keycap(self, key_index):
        pos, angle = self.get_key_coord(key_index, 0, 0)
        return translate(pos)(rotate([0,0,angle*180/math.pi])(square(self.keycap_size, center=True)))

    def get_top_left(self):
        return self.get_key_coord(0, -self.keycap_size[0]/2 - self.offset, self.keycap_size[1]/2 + self.offset)[0]

    def get_top_right(self):
        return self.get_key_coord(self.key_count - 1, self.keycap_size[0]/2 + self.offset, self.keycap_size[1]/2 + self.offset)[0]

    def get_bottom_left(self):
        return self.get_key_coord(0, -self.keycap_size[0]/2 - self.offset, -self.keycap_size[1]/2 - self.offset)[0]

    def get_bottom_right(self):
        return self.get_key_coord(self.key_count - 1, self.keycap_size[0]/2 + self.offset, -self.keycap_size[1]/2 - self.offset)[0]

class Shell:
    def __init__(self, rows, columns, keycap_size, keycap_dist, switch_hole_size, column_stagger, shell_offset, precision):
        self.rows = rows
        self.columns = columns
        self.keycap_size = keycap_size
        self.keycap_dist = keycap_dist
        self.switch_hole_size = switch_hole_size
        self.switch_hole_dist = diff_coords(
            sum_coords(self.keycap_size, self.keycap_dist), self.switch_hole_size)

        self.column_stagger = column_stagger
        self.shell_offset = shell_offset
        self.precision = precision

        panel_top = self.get_key_position(rows-1,columns-1)[1] + self.keycap_size[1] + self.shell_offset
        panel_width=22
        panel_height=92
        panel_left = self.get_key_position(0,columns-1)[0] + self.keycap_size[0]
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
            [panel_left, panel_top],
                ["SHARP"],
                ["SHARP"],
            [panel_left + panel_width, panel_top], # TOP RIGHT
                ["SHARP"],
                ["SHARP"],
            [panel_left + panel_width, 0],
                ["RELATIVE", 0, -8],
                ["POLAR", 12, 125],
            tc.get_top_right(), # THUMB CLUSTER, TOP RIGHT
                ["SHARP"],
                ["SHARP"],
            tc.get_bottom_right(),
                ["RELATIVE", 0, 40], # random control points
                ["RELATIVE", 40, 0], # random control points
            tc.get_bottom_left(),
                ["RELATIVE", 0, 15],
                ["RELATIVE", 5, 0],
            sum_coords(self.get_key_position(0,0), [2*keycap_size[1], -shell_offset]),
                ["SHARP"],
                ["SHARP"],
        ]

        self.bezier_curve = bezier_closed_line(casepoints, self.precision)


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
        #(pos, angle, height, switch_hole_size, keycap_size)

        for row in range(0, self.rows):
            for col in range(0, self.columns):
                res += make_switch_hole(
                    self.get_key_position(row,  col,  center=True),
                    0,
                    self.switch_hole_size,
                    self.keycap_size)

        return res

shell_offset = 0.5 # the 'border'
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
    precision = 0.02
)

sh = Shell(rows = 4,
    columns = 6,
    keycap_size = keycap_size,
    keycap_dist = keycap_dist,
    switch_hole_size = switch_hole_size,
    column_stagger = [0,  0,  0.25,  0.5,  0.25,  0.15],
    shell_offset = shell_offset,
    precision = 0.02
)

height=10
top_height=2
bot_height=2
wall_width=1
bottom_recess=0.1

shape = square(0)
shape += tc.make_shape()
shape += sh.make_shape()

wall = shape - offset(delta=-wall_width)(shape)
wall = linear_extrude(height=10)(wall)

bot = linear_extrude(height=bot_height)(offset(delta=-(wall_width+bottom_recess))(shape))
shape -= tc.make_switch_holes()
shape -= sh.make_switch_holes()
top = translate([0,0,height-top_height])(linear_extrude(height=top_height)(shape))

scad_render_to_file(cube(0)
    #+ shape
    + wall
    + top
    + bot
, "out.scad")
