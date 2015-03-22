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


class SmallLengthReduction(object):
    def pack(self, sprites):
        sprites = sorted(sprites, key=self.get_length)
        by_length_iter = itertools.groupby(sprites, key=self.get_length)
        by_length = [(k, list(vs)) for k, vs in by_length_iter]

        packings = []
        for i in range(len(by_length)):
            collapsed = []
            for j in range(i + 1):
                collapsed += by_length[j][1]
            collapsed_by_length = ([(by_length[i][0], collapsed)] +
                                   by_length[i + 1:])
            packing = self.pack_rows(collapsed_by_length)
            logger.debug("Collapse all smaller than %s => %s",
                         by_length[i][0], packing.area)
            packings.append(packing)
        best = min(packings, key=operator.attrgetter('area'))
        logger.info("small_length_reduction: Best is area %s", best.area)
        return best

    def bins_for_depth(self, by_length, depth):
        bins = []
        for length, ims in by_length:
            row = None
            rows = []
            row_depth = depth
            for im in ims:
                if row_depth + self.get_depth(im) > depth:
                    row = []
                    rows.append(row)
                    row_depth = 0
                row.append(im)
                row_depth += self.get_depth(im)
            bins.append((length, rows))
        return bins

    def packing_for_depth(self, by_length, depth):
        bins = self.bins_for_depth(by_length, depth)
        packing = []
        y = 0
        for length, rows in bins:
            for row in rows:
                x = 0
                max_length = 0
                for im in row:
                    placement = self.placement_tuple(depth=x, length=y)
                    packing.append((placement, im))
                    max_length = max(max_length, self.get_length(im))
                    x += self.get_depth(im)
                y += max_length
        return Packing(packing)

    def pack_rows(self, by_length):
        min_depth = max(self.get_depth(im)
                        for l, ims in by_length for im in ims)
        max_depth = max(sum(self.get_depth(im) for im in ims)
                        for l, ims in by_length)

        depth = max_depth
        packings = []
        while depth >= min_depth:
            p = self.packing_for_depth(by_length, depth)
            depth = self.get_packing_depth(p) - 1
            packings.append(p)
        best = min(packings, key=operator.attrgetter('area'))
        logger.debug(
            "%s: Tried %s depth thresholds between %s and %s; best is %s",
            type(self).__name__, len(packings), min_depth, max_depth,
            self.get_packing_depth(best))
        return best

    def get_length(self, im):
        raise NotImplementedError

    def get_depth(self, im):
        raise NotImplementedError

    def get_packing_depth(self, packing):
        raise NotImplementedError

    def placement_tuple(self, depth, length):
        raise NotImplementedError


class SmallHeightReduction(SmallLengthReduction):
    def get_length(self, im):
        return im.outer_height

    def get_depth(self, im):
        return im.outer_width

    def get_packing_depth(self, packing):
        return packing.width

    def placement_tuple(self, depth, length):
        return (depth, length)


class SmallWidthReduction(SmallLengthReduction):
    def get_length(self, im):
        return im.outer_width

    def get_depth(self, im):
        return im.outer_height

    def get_packing_depth(self, packing):
        return packing.height

    def placement_tuple(self, depth, length):
        return (length, depth)


def naive_packing(sprites):
    p1 = SmallHeightReduction().pack(sprites)
    p2 = SmallWidthReduction().pack(sprites)
    packing = p1 if p1.area <= p2.area else p2
    image_area = sum(sprite.outer_width * sprite.outer_height
                     for sprite in sprites)
    whitespace = packing.area - image_area
    whitespace_fraction = 1.0 * whitespace / packing.area
    logger.info("naive_packing: %d/%d: %.2f%% whitespace",
                image_area, packing.area, 100 * whitespace_fraction)
    im = packing.render()
    return im, list(packing)
