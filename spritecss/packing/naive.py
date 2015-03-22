import logging
import operator
import itertools

from spritecss.image import Image

logger = logging.getLogger('spritecss')


class Packing(object):
    def __init__(self, packing):
        placements, self.sprites = zip(*packing)
        self.input_area = sum(im.outer_width * im.outer_height
                              for im in self.sprites)

        # Offset such that top left image is (0, 0)
        xs, ys = zip(*placements)
        top = min(ys)
        left = min(xs)
        self.xs = [x - left for x in xs]
        self.ys = [y - top for y in ys]

        self.height = max(y + im.outer_height
                          for y, im in zip(self.ys, self.sprites))
        self.width = max(x + im.outer_width
                         for x, im in zip(self.xs, self.sprites))
        self.area = self.width * self.height

    outer_width = property(lambda self: self.width)
    outer_height = property(lambda self: self.height)

    def __iter__(self):
        return iter(zip(zip(self.xs, self.ys), self.sprites))

    def render(self):
        meta = {"bitdepth": 8, "alpha": True}
        rows = [bytearray((self.width * 4)) for i in range(self.height)]
        for (x, y), sprite in self:
            pixel_rows = sprite.im.pixels
            for i, pixels in enumerate(pixel_rows):
                row = rows[y + i]
                a1 = x * 4
                a2 = a1 + len(pixels)
                row[a1:a2] = pixels
        return Image(self.width, self.height, rows, meta)


def pack_rows(by_length, length_attr, depth_attr):
    def bins_for_depth(depth):
        bins = []
        for length, ims in by_length:
            row = None
            rows = []
            row_depth = depth
            for im in ims:
                if row_depth + getattr(im, depth_attr) > depth:
                    row = []
                    rows.append(row)
                    row_depth = 0
                row.append(im)
                row_depth += getattr(im, depth_attr)
            bins.append((length, rows))
        return bins

    def packing_for_depth(depth):
        bins = bins_for_depth(depth)
        packing = []
        y = 0
        for length, rows in bins:
            for row in rows:
                x = 0
                max_length = 0
                for im in row:
                    if 'height' in length_attr:
                        placement = (x, y)
                    else:
                        placement = (y, x)
                    packing.append((placement, im))
                    max_length = max(max_length, getattr(im, length_attr))
                    x += getattr(im, depth_attr)
                y += max_length
        return Packing(packing)

    min_depth = max(getattr(im, depth_attr)
                    for l, ims in by_length for im in ims)
    max_depth = max(sum(getattr(im, depth_attr) for im in ims)
                    for l, ims in by_length)

    depth = max_depth
    packings = []
    while depth >= min_depth:
        p = packing_for_depth(depth)
        p_depth = getattr(p, depth_attr)
        depth = p_depth - 1
        packings.append(p)
    best = min(packings, key=operator.attrgetter('area'))
    logger.debug("Tried %s thresholds for %s between %s and %s; best is %s",
                 len(packings), depth_attr, min_depth, max_depth,
                 getattr(best, depth_attr))
    return best


def small_length_reduction(sprites, length_attr, depth_attr):
    key = operator.attrgetter(length_attr)
    sprites = sorted(sprites, key=key)
    by_length = [(k, list(vs))
                 for k, vs in itertools.groupby(sprites, key=key)]

    packings = []
    for i in range(len(by_length)):
        collapsed = []
        for j in range(i + 1):
            collapsed += by_length[j][1]
        collapsed_by_length = ([(by_length[i][0], collapsed)] +
                               by_length[i + 1:])
        packing = pack_rows(collapsed_by_length, length_attr, depth_attr)
        logger.debug("Collapse all smaller than %s => %s",
                     by_length[i][0], packing.area)
        packings.append(packing)
    best = min(packings, key=operator.attrgetter('area'))
    logger.info("small_length_reduction: Best is area %s", best.area)
    return best


def naive_packing(sprites):
    p1 = small_length_reduction(sprites, 'outer_height', 'outer_width')
    p2 = small_length_reduction(sprites, 'outer_width', 'outer_height')
    packing = p1 if p1.area <= p2.area else p2
    im = packing.render()
    return im, list(packing)
