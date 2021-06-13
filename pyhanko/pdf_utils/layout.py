"""Layout utilities (to be expanded)"""

import enum
import logging
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

__all__ = [
    'BoxSpecificationError', 'BoxConstraints', 'AxisAlignment',
    'SimpleBoxLayoutRule', 'Positioning'
]

from pyhanko.pdf_utils.config_utils import ConfigurableMixin

logger = logging.getLogger(__name__)


class LayoutError(ValueError):
    pass


class BoxSpecificationError(LayoutError):
    """Raised when a box constraint is over/underspecified."""
    pass


class BoxConstraints:
    """Represents a box of potentially variable width and height.
    Among other uses, this can be leveraged to produce a variably sized
    box with a fixed aspect ratio.

    If width/height are not defined yet, they can be set by assigning to the
    :attr:`width` and :attr:`height` attributes.
    """

    _width: Optional[int]
    _height: Optional[int]
    _ar: Optional[Fraction]
    _fully_specified: bool

    def __init__(self, width=None, height=None, aspect_ratio: Fraction = None):
        self._width = int(width) if width is not None else None
        self._height = int(height) if height is not None else None

        fully_specified = False

        self._ar = None
        if width is None and height is None and aspect_ratio is None:
            return
        elif width is not None and height is not None:
            if aspect_ratio is not None:
                raise BoxSpecificationError  # overspecified
            self._ar = Fraction(self._width, self._height)
            fully_specified = True
        elif aspect_ratio is not None:
            self._ar = aspect_ratio
            if height is not None:
                self._width = height * aspect_ratio
            elif width is not None:
                self._height = width / aspect_ratio

        self._fully_specified = fully_specified

    def _recalculate(self):
        if self._width is not None and self._height is not None:
            self._ar = Fraction(self._width, self._height)
            self._fully_specified = True
        elif self._ar is not None:
            if self._height is not None:
                self._width = int(self._height * self._ar)
                self._fully_specified = True
            elif self._width is not None:
                self._height = int(self._width / self._ar)
                self._fully_specified = True

    @property
    def width(self) -> int:
        """
        :return:
            The width of the box.
        :raises BoxSpecificationError:
            if the box's width could not be determined.
        """
        if self._width is not None:
            return self._width
        else:
            raise BoxSpecificationError

    @width.setter
    def width(self, width):
        if self._width is None:
            self._width = width
            self._recalculate()
        else:
            raise BoxSpecificationError

    @property
    def width_defined(self) -> bool:
        """
        :return:
            ``True`` if the box currently has a well-defined width,
            ``False`` otherwise.
        """
        return self._width is not None

    @property
    def height(self) -> int:
        """
        :return:
            The height of the box.
        :raises BoxSpecificationError:
            if the box's height could not be determined.
        """
        if self._height is not None:
            return self._height
        else:
            raise BoxSpecificationError

    @height.setter
    def height(self, height):
        if self._height is None:
            self._height = height
            self._recalculate()
        else:
            raise BoxSpecificationError

    @property
    def height_defined(self) -> bool:
        """
        :return:
            ``True`` if the box currently has a well-defined height,
            ``False`` otherwise.
        """
        return self._height is not None

    @property
    def aspect_ratio(self) -> Fraction:
        """
        :return:
            The aspect ratio of the box.
        :raises BoxSpecificationError:
            if the box's aspect ratio could not be determined.
        """
        if self._ar is not None:
            return self._ar
        else:
            raise BoxSpecificationError

    @property
    def aspect_ratio_defined(self) -> bool:
        """
        :return:
            ``True`` if the box currently has a well-defined aspect ratio,
            ``False`` otherwise.
        """
        return self._ar is not None


class InnerScaling(enum.Enum):
    NO_SCALING = enum.auto()
    """Never scale content."""

    STRETCH_FILL = enum.auto()
    """Scale content to fill the entire container."""

    STRETCH_TO_FIT = enum.auto()
    """
    Scale content while preserving aspect ratio until either the maximal 
    width or maximal height is reached.
    """

    SHRINK_TO_FIT = enum.auto()
    """
    Scale content down to fit in the container, while preserving the original
    aspect ratio.
    """


class AxisAlignment(enum.Enum):
    ALIGN_MIN = enum.auto()
    """
    Align maximally towards the negative end of the axis.
    """

    ALIGN_MID = enum.auto()
    """
    Center content along the axis.
    """

    ALIGN_MAX = enum.auto()
    """
    Align maximally towards the positive end of the axis.
    """

    @property
    def flipped(self):
        return _alignment_opposites[self]

    def align(self, container_len: int, inner_len: int,
              pre_margin, post_margin) -> int:

        effective_max_len = Margins.effective(
            'length', container_len, pre_margin, post_margin
        )

        if self == AxisAlignment.ALIGN_MAX:
            # we want to start as far up the axis as possible.
            # Ignoring margins, that would be at container_len - inner_len
            # This computation makes sure that there's room for post_margin
            # in the back.
            return container_len - inner_len - post_margin
        elif self == AxisAlignment.ALIGN_MIN:
            return pre_margin
        elif inner_len > effective_max_len:
            logger.warning(
                f"Content box width/height {inner_len} is too wide for "
                f"container size {container_len} with margins "
                f"({pre_margin}, {post_margin}); post_margin will be ignored"
            )
            return pre_margin
        elif self == AxisAlignment.ALIGN_MID:
            # we'll center the inner content *within* the margins
            inner_offset = (effective_max_len - inner_len) // 2
            return pre_margin + inner_offset


# Class variables in enums are weird, so let's put this here
_alignment_opposites = {
    AxisAlignment.ALIGN_MID: AxisAlignment.ALIGN_MID,
    AxisAlignment.ALIGN_MIN: AxisAlignment.ALIGN_MAX,
    AxisAlignment.ALIGN_MAX: AxisAlignment.ALIGN_MIN
}


@dataclass(frozen=True)
class Positioning(ConfigurableMixin):
    x_pos: int
    y_pos: int
    x_scale: float
    y_scale: float

    def as_cm(self):
        return b'%g 0 0 %g %g %g cm' % (
            self.x_scale, self.y_scale, self.x_pos, self.y_pos
        )


def _aln_width(alignment: AxisAlignment, container_box: BoxConstraints,
               inner_nat_width: int, pre_margin: int, post_margin: int):
    if container_box.width_defined:
        return alignment.align(
            container_box.width, inner_nat_width, pre_margin, post_margin
        )
    else:
        container_box.width = inner_nat_width + pre_margin + post_margin
        return pre_margin


def _aln_height(alignment: AxisAlignment, container_box: BoxConstraints,
                inner_nat_height: int, pre_margin: int, post_margin: int):
    if container_box.height_defined:
        return alignment.align(
            container_box.height, inner_nat_height, pre_margin, post_margin
        )
    else:
        container_box.height = inner_nat_height + pre_margin + post_margin
        return pre_margin


@dataclass(frozen=True)
class Margins(ConfigurableMixin):
    left: int = 0

    right: int = 0

    top: int = 0

    bottom: int = 0

    @classmethod
    def uniform(cls, num):
        return Margins(num, num, num, num)

    @staticmethod
    def effective(dim_name, container_len, pre, post):
        eff = container_len - pre - post
        if eff < 0:
            raise LayoutError(
                f"Margins ({pre}, {post}) too wide for container "
                f"{dim_name} {container_len}."
            )
        return eff

    def effective_width(self, width):
        return Margins.effective('width', width, self.left, self.right)

    def effective_height(self, height):
        return Margins.effective('height', height, self.bottom, self.top)


# TODO implement ConfigurableMixin for these parameters


# TODO explain that this is about box alignment, not text alignment

@dataclass(frozen=True)
class SimpleBoxLayoutRule:
    x_align: AxisAlignment
    """
    Horizontal alignment settings.
    """

    y_align: AxisAlignment
    """
    Vertical alignment settings.
    """

    margins: Margins = Margins()
    """
    Container (inner) margins. Defaults to all zeroes.
    """

    inner_content_scaling: InnerScaling = InnerScaling.SHRINK_TO_FIT
    """
    Inner content scaling rule.
    """

    def substitute_margins(self, new_margins: Margins) -> 'SimpleBoxLayoutRule':
        return SimpleBoxLayoutRule(
            x_align=self.x_align, y_align=self.y_align,
            margins=new_margins,
            inner_content_scaling=self.inner_content_scaling
        )

    def fit(self, container_box: BoxConstraints,
            inner_nat_width: int, inner_nat_height: int) -> Positioning:

        margins = self.margins
        scaling = self.inner_content_scaling
        x_scale = y_scale = 1
        if scaling != InnerScaling.NO_SCALING and \
                container_box.width_defined and container_box.height_defined:
            eff_width = margins.effective_width(container_box.width)
            eff_height = margins.effective_height(container_box.height)

            x_scale = eff_width / inner_nat_width
            y_scale = eff_height / inner_nat_height
            if scaling == InnerScaling.STRETCH_TO_FIT:
                x_scale = y_scale = min(x_scale, y_scale)
            elif scaling == InnerScaling.SHRINK_TO_FIT:
                # same as stretch to fit, with the additional stipulation
                # that it can't scale up, only down.
                x_scale = y_scale = min(x_scale, y_scale, 1)

        x_pos = _aln_width(
            self.x_align, container_box,
            inner_nat_width * x_scale,
            margins.left, margins.right
        )
        y_pos = _aln_height(
            self.y_align, container_box,
            inner_nat_height * y_scale,
            margins.bottom, margins.top
        )
        return Positioning(
            x_pos=x_pos, y_pos=y_pos, x_scale=x_scale, y_scale=y_scale
        )
