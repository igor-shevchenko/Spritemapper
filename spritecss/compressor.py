"""
Based on https://github.com/miracle2k/webassets/blob/master/src/webassets/filter/spritemapper.py
"""
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
import datetime
import os

from six import StringIO
from contextlib import contextmanager
from compressor.conf import settings
from compressor.filters import FilterBase

try:
    from spritecss.main import CSSFile
    from spritecss.css import CSSParser
    from spritecss.css.parser import iter_print_css
    from spritecss.config import CSSConfig
    from spritecss.mapper import SpriteMapCollector
    from spritecss.packing import PackedBoxes, print_packed_size
    from spritecss.packing.sprites import open_sprites
    from spritecss.packing.naive import naive_packing
    from spritecss.stitch import stitch
    from spritecss.replacer import SpriteReplacer

except ImportError:
    spritecss_loaded = False

else:
    spritecss_loaded = True

    class FakeCSSFile(CSSFile):
        """
        A custom subclass of spritecss.main.CSSFile that accepts CSS input
        as string data, instead of requiring that a CSS file be read from
        disk.
        """

        def __init__(self, fname, conf=None, data=''):
            super(FakeCSSFile, self).__init__(fname, conf=conf)
            self.data = StringIO(data)

        @contextmanager
        def open_parser(self):
            yield CSSParser.read_file(self.data)

    class LocalCSSConfig(CSSConfig):
        def normpath(self, p):
            return super(LocalCSSConfig, self).normpath(p.lstrip(os.sep))

        def get_spritemap_url(self, fname):
            # Append version info to image - current timestamp
            return "".join([super(LocalCSSConfig, self).get_spritemap_url(fname), '?', datetime.datetime.now().strftime('%Y%m%d%H%M%S')])


__all__ = ('SpritemapperFilter',)


class SpritemapperFilter(FilterBase):
    """
    Generate CSS spritemaps using
    `Spritemapper <http://yostudios.github.com/Spritemapper/>`_, a Python
    utility that merges multiple images into one and generates CSS positioning
    for the corresponding slices. Installation is easy::

        pip install spritemapper

    Supported configuration options:

    COMPRESS_SPRITEMAPPER_PADDING
        A tuple of integers indicating the number of pixels of padding to
        place between sprites

    COMPRESS_SPRITEMAPPER_ANNEAL_STEPS
        Affects the number of combinations to be attempted by the box packer
        algorithm

    **Note:** Since the ``spritemapper`` command-line utility expects source
    and output files to be on the filesystem, this filter interfaces directly
    with library internals instead. It has been tested to work with
    Spritemapper version 1.0.
    """

    def __init__(self, *args, **kwargs):
        super(SpritemapperFilter, self).__init__(*args, **kwargs)
        if not spritecss_loaded:
            raise EnvironmentError(
                "The spritemapper package could not be found."
            )

        self.options = {}
        padding = getattr(settings, 'COMPRESS_SPRITEMAPPER_PADDING', None)
        if padding:
            self.options['padding'] = padding
        anneal_steps = getattr(settings, 'SPRITEMAPPER_ANNEAL_STEPS', 100)
        if anneal_steps:
            self.options['anneal_steps'] = anneal_steps

        self.options['output_image'] = os.path.join(settings.COMPRESS_OUTPUT_DIR, "sprite.png")
        self.options['base_url'] = settings.COMPRESS_URL

    def input(self, filename=None, **kwargs):
        if not filename or not filename.startswith(settings.COMPRESS_ROOT) or not filename.endswith(".scss"):
            return self.content

        source_path = filename

        # Save the input data for later
        css = self.content

        # Build config object
        conf = LocalCSSConfig(base=self.options, fname=source_path, root=settings.COMPRESS_ROOT)

        # Instantiate a dummy file instance
        cssfile = FakeCSSFile(fname=source_path, conf=conf, data=css)

        # Find spritemaps
        smaps = SpriteMapCollector(conf=conf)
        smaps.collect(cssfile.map_sprites())

        # Weed out single-image spritemaps
        smaps = [sm for sm in smaps if len(sm) > 1]

        # Generate spritemapped image
        # This code is almost verbatim from spritecss.main.spritemap
        sm_plcs = []
        for smap in smaps:
            with open_sprites(smap, pad=conf.padding) as sprites:
                print("packing sprites in mapping %s" % (smap.fname,))

                if conf.packer == 'annealing':
                    print("annealing %s in steps of %d" % (smap.fname, conf.anneal_steps))
                    packed = PackedBoxes(sprites, anneal_steps=conf.anneal_steps)
                    print_packed_size(packed)
                    sm_plcs.append((smap, packed.placements))
                    im = stitch(packed)

                elif conf.packer == 'naive':
                    print("Naive packing")
                    im, placements = naive_packing(sprites)
                    sm_plcs.append((smap, placements))

                print("writing spritemap image at %s" % (smap.fname,))
                with open(smap.fname, "wb") as fp:
                    im.save(fp)

        # Instantiate a fake file instance again
        cssfile = FakeCSSFile(fname=source_path, conf=conf, data=css)

        out = StringIO()

        # Output rewritten CSS with spritemapped URLs
        replacer = SpriteReplacer(sm_plcs)
        for data in iter_print_css(replacer(cssfile)):
            out.write(data)

        return out.getvalue()
