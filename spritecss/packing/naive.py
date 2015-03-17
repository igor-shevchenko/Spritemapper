import re
import operator
import itertools
import collections

from ..image import Image


InputImageBase = collections.namedtuple(
    'InputImage', 'image width height'.split())


class InputImage(InputImageBase):
    dimensions = property(lambda self: (self.width, self.height))
    area = property(lambda self: self.width * self.height)


Position = collections.namedtuple('Position', 'left top'.split())


class PackedImage(object):
    def __init__(self, im, pos):
        self._im = im
        self._pos = pos

    def __getattr__(self, attr):
        try:
            return getattr(self._im, attr)
        except AttributeError:
            return getattr(self._pos, attr)

    right = property(lambda self: self.left + self.width)
    bottom = property(lambda self: self.top + self.height)


def histogram(xs, attr):
    key = operator.attrgetter(attr)
    xs = sorted(xs, key=key)
    return [(k, list(vs)) for k, vs in itertools.groupby(xs, key=key)]


class Packing(object):
    def __init__(self, sprites):
        self.sprites = sprites
        self.input_area = sum(im.area for im in sprites)
        self.top = min(im.top for im in sprites)
        self.left = min(im.left for im in sprites)
        self.bottom = max(im.bottom for im in sprites)
        self.right = max(im.right for im in sprites)
        self.width = self.right - self.left
        self.height = self.bottom - self.top
        self.area = self.width * self.height


def pack_rows(by_height):
    def bins_for_width(width):
        bins = []
        for height, ims in by_height:
            row = None
            rows = []
            row_width = width
            for im in ims:
                if row_width + im.width > width:
                    row = []
                    rows.append(row)
                    row_width = 0
                row.append(im)
                row_width += im.width
            bins.append((height, rows))
        return bins

    def packing_for_width(width):
        bins = bins_for_width(width)
        packing = []
        y = 0
        for height, rows in bins:
            for row in rows:
                x = 0
                max_height = 0
                for im in row:
                    packing.append(PackedImage(im, Position(x, y)))
                    max_height = max(max_height, im.height)
                    x += im.width
                y += max_height
        return Packing(packing)

    min_width = max(im.width for h, ims in by_height for im in ims)
    max_width = max(sum(im.width for im in ims) for h, ims in by_height)

    width = max_width
    packings = []
    while width >= min_width:
        p = packing_for_width(width)
        # print("Computed packing for width %s" % p.width)
        width = p.width - 1
        packings.append(p)
    best = min(packings, key=operator.attrgetter('area'))
    print("pack_rows: Best is width %s at area %s" %
          (best.width, best.area))
    return best


def write_packing(packing, filename):
    with open(filename, 'w') as fp:
        for image in packing.sprites:
            fp.write(
                ('<img src="{im.filename}" ' +
                 'style="position:absolute;' +
                 'left:{im.left}px;top:{im.top}px"/>\n').format(im=image))


def small_height_reduction(by_height):
    packings = []
    for i in range(len(by_height)):
        collapsed = []
        for j in range(i + 1):
            collapsed += by_height[j][1]
        collapsed_by_height = [(by_height[i][0], collapsed)] + by_height[i + 1:]
        packing = pack_rows(collapsed_by_height)
        print("Collapse all smaller than %s => %s" % (by_height[i][0], packing.area))
        packings.append(packing)
    best = min(packings, key=operator.attrgetter('area'))
    print("small_height_reduction: Best is area %s" % (best.area,))
    return best


def and_the_transpose(f, sprites):
    im_transpose = []
    for im in sprites:
        im_transpose.append(
            InputImage(image=im.image, width=im.height, height=im.width))
    p1 = f(histogram(sprites, 'height'))
    p2 = f(histogram(im_transpose, 'height'))
    if p1.area <= p2.area:
        return p1
    packing_transpose = []
    for pim in p2.sprites:
        im = InputImage(
            image=pim.image, width=pim.height, height=pim.width)
        pos = Position(top=pim.left, left=pim.top)
        packing_transpose.append(PackedImage(im, pos))
    return Packing(packing_transpose)


def naive_packing(sprites):
    images = [
        InputImage(image=sprite, width=sprite.outer_width, height=sprite.outer_height)
        for sprite in sprites
    ]
    packing = and_the_transpose(small_height_reduction, images)
    bd = 8
    meta = {"bitdepth": bd, "alpha": True}
    rows = [bytearray((packing.width * 4)) for i in range(packing.height)]
    placements = []
    for pim in packing.sprites:
        placements.append(((pim.left, pim.top), pim.image))
        pixel_rows = pim.image.im.pixels
        for i, pixels in enumerate(pixel_rows):
            row = rows[pim.top + i - packing.top]
            a1 = pim.left * 4
            a2 = a1 + len(pixels)
            row[a1:a2] = pixels
    im = Image(packing.width, packing.height, rows, meta)
    return im, placements
