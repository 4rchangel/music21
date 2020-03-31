# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Name:         note.py
# Purpose:      music21 classes for representing notes
#
# Authors:      Michael Scott Cuthbert
#               Christopher Ariza
#
# Copyright:    Copyright © 2006-2019 Michael Scott Cuthbert and the music21 Project
# License:      BSD, see license.txt
# ------------------------------------------------------------------------------
'''
Classes and functions for creating Notes, Rests, and Lyrics.

The :class:`~music21.pitch.Pitch` object is stored within,
and used to configure, :class:`~music21.note.Note` objects.
'''

import copy
import unittest
import re
import enum

from typing import Optional, List

from music21 import base
from music21 import beam
from music21 import common
from music21 import duration
from music21 import exceptions21
from music21 import expressions
from music21 import interval
from music21 import pitch
from music21 import prebase
from music21 import style
from music21 import tie
from music21 import volume

from music21 import environment
_MOD = 'note'
environLocal = environment.Environment(_MOD)

noteheadTypeNames = (
    'arrow down',
    'arrow up',
    'back slashed',
    'circle dot',
    'circle-x',
    'circled',
    'cluster',
    'cross',
    'diamond',
    'do',
    'fa',
    'inverted triangle',
    'la',
    'left triangle',
    'mi',
    'none',
    'normal',
    'other',
    're',
    'rectangle',
    'slash',
    'slashed',
    'so',
    'square',
    'ti',
    'triangle',
    'x',
)

stemDirectionNames = (
    'double',
    'down',
    'noStem',
    'none',
    'unspecified',
    'up',
)


# -----------------------------------------------------------------------------
class LyricException(exceptions21.Music21Exception):
    pass


class NoteException(exceptions21.Music21Exception):
    pass


class NotRestException(exceptions21.Music21Exception):
    pass

# ------------------------------------------------------------------------------
class LyricAbstraction(enum.Enum):
    humming = 'humming'
    laughing = 'laughing'

class LyricExtension(prebase.ProtoM21Object, style.StyleMixin):

    _styleClass = style.TextStylePlacement

    __slots__ = (
        '_extension_type',
    )

    class ExtensionType(enum.Enum):
        begin = 'start'
        middle = 'continue'
        end = 'stop'

    '''
    Representation of lyric extensions across several notes
    '''
    def __init__(self, extType : ExtensionType = None):
        super().__init__()
        self._extension_type = extType

    @property
    def extension_type(self):#
        return self._extension_type


class Textual(prebase.ProtoM21Object, style.StyleMixin):
    '''
    An object representing an atomic textual element of lyrics

    Text attached to a lyrics object can be decomposed into multiple parts with varying styles and
    may contain semantic annotations like grouping of text-parts into syllablles and words.
    A Textual represents the tiny-most atomic unit of text with a single consistent style and single syllabic semantic.
    Lyrical text can be represented as a list of textuals (as done in the Lyric class). Within such a list
    compact slices of Textuals can form semantic groups, i.e. syllables, by sharing a context instance.
    '''
    __slots__ = (
        'context',
        '_text'
    )

    class Context:
        '''
        An object to encode syllabic grouping and annotations to Textuals

        Textuals sharing a context object are considered as one syllabic unit [and should form a compact list slice]
        Attached
        '''
        __slots__ = (
            '_elision',
            '_syllabic',
        )
        def __init__(self):
            self._elision = None
            self._syllabic = None

        @property
        def elision(self) -> Optional['Textual']:
            '''
            The elision symbol following the syllabic group represented by this context

            None represents the absence of a elision
            Elisions can be written as arbitrary symbols [or texts], may be styled and belong to some syllabic context,
            as encoded in a Textual
            :return: Textual representing a [styled] elision symbol following the syllabic group
            '''
            return self._elision

        @elision.setter
        def elision(self, el : Optional['Textual']):
            '''
            sets the elision symbol at the end of the context and force the elisions context to point to this instance

            :param el: new value of type Textual [or str] or None
            :return:
            '''
            if el is None or isinstance(el, Textual):
                self._elision = el
            elif isinstance(el, str):
                self._elision = Textual(el, self)
            else:
                raise ValueError('Elisions must be encoded as Textual objects')

            # the elision is naturally part of the context => enforce a backreference
            if el and self._elision.context != self:
                if self._elision.context == None:
                    el.context = self
                else:
                    raise ValueError('Elisions may only be part of a single single context. Competitor detected')

        @property
        def syllabic(self) -> Optional[str]:
            '''
            encodes the syllabic semantic type of a group of textuals
            :return: one of ['single', 'begin', 'middle', 'end', None]
            '''
            return self._syllabic

        @syllabic.setter
        def syllabic(self, syl):
            # TODO: should better be implemented as an enum
            if syl in ['single', 'begin', 'middle', 'end', None]:
                self._syllabic = syl
            else:
                raise ValueError('unsupported value')

    def __init__(self, text : str, ctxt : Context):
        super().__init__()
        self.context = ctxt
        self.rawText = text

    @property
    def rawText(self) -> str:
        '''
        returns the text of the element
        :return: plaintext
        '''
        return self._text

    @rawText.setter
    def rawText(self, t):
        '''
        sets the contained text (converting it to 'str', if necessary)
        :param t: new plaintext
        :return:
        '''

        # possible might alter unicode or other string-like representations
        if not isinstance(t, str):
            t = str(t)
        self._text = t

class LyricText:
    __slots__ = (
        '_textuals',
        '_extension'
    )

    def __init__(self, text=None, **kwargs):
        super().__init__()
        self._textuals = []
        self._extension = kwargs.get('extension', None)
        if text:
            self.setTextAndSyllabic(text, **kwargs)

    @property
    def extension(self):
        return self._extension

    @extension.setter
    def extension(self, value):
        self._extension = value

    @property
    def textuals(self) -> List[Textual]:
        return self._textuals

    @property
    def syllabic(self) -> str:
        '''
        retrieve the syllabic type of the lyrics, for backwards compatibility
        for complex lyrics composed of several syllables, this will raise an exception,
        # TODO: humming, laughing, extend?
        :return: one of [None, 'single', 'begin', 'middle', 'end']
        '''
        if self._content and type(self._content) is LyricText:
            if not self._textuals or 0 == len(self._textuals):
                return None
            # a single context instance spanning over all _textuals indicates a unique syllabic type
            if self._textuals[0].context is self._textuals[-1].context:
                uniqueCtxt = self._textuals[0].context
                if not uniqueCtxt:
                    return None
                else:
                    return uniqueCtxt.syllabic
            raise RuntimeError('Lyric object contains complex syllabic substructure instead of unique syllabic type')

    def setTextAndSyllabic(self, rawText, **kwargs):
        '''
        splits a rawText into Textual elements with according syllabic type (as necessary)
        or creates a single Textual (applyRaw==True) [with a optionally specified syllabic type]

        >>> l = note.Lyric()
        >>> l.setTextAndSyllabic('hel-lo_world')
        >>> l.text

        :type rawText: str
        :type applyRaw: bool
        :rtype: None
        '''
        # do not want to do this unless we are sure this is not a string
        # possibly might alter unicode or other string-like representations
        if not isinstance(rawText, str):
            rawText = str(rawText)

        syllabic = kwargs.get('syllabic', None)
        applyRaw = kwargs.get('applyRaw', (True if syllabic else False))

        if applyRaw is True:
            ctxt = Textual.Context()
            ctxt.syllabic = syllabic
            self.textuals = [Textual(rawText, ctxt, applyRaw=True)]
        else:
            if syllabic:
                raise ValueError('Can not enforce a desired syllabic type while parsing the text (applyRaw==False)')
            # prepare a new context for first syllable
            ctxt = Textual.Context()
            ctxt.syllabic = 'single'
            # split into words according to hyphenation. Separators appear in the word list
            words = re.split(r'(\s+|_)', rawText.strip())
            for word in words:
                isSeparator = re.match(r'(?:\s+|_)', word)
                if ctxt and isSeparator:
                    # new word, new context
                    ctxt = Textual.Context()
                    ctxt.syllabic = 'single'
                    # detected separator: append a elision to the current context
                    ctxt.elision = Textual(word, ctxt=ctxt)
                elif not isSeparator:
                    syllables = re.split('(-)', word)
                    # in the case, that the string starts or ends with one of the separators,
                    # the list will contain empty strings '' at start or end, due to re.split's beavior
                    # => remove such, if they are not the only text!
                    # => e.g. the rawText '-' will yield syllables=[ '-', ''] which will generated a single textual '' of syllabic type "begin"
                    if 2<len(syllables) and syllables[0] == '':
                        syllables = syllables[1:]
                    if 2<len(syllables) and syllables[-1] == '':
                        syllables = syllables[:-1]

                    for syllTxt in syllables:
                        # the elision-string "-" starts a new syllable
                        # also the preceeding syllable needs to be adjusted to either 'middle' or 'begin' type
                        if syllTxt == '-':
                            if ctxt.syllabic == 'single':
                                ctxt.syllabic = 'begin'
                            elif ctxt.syllabic == 'end':
                                ctxt.syllabic = 'middle'
                            # strigs like 'asdf--ghjk' may be used to insert empty textuals.
                            if 0<len(self._textuals) and not ctxt is self._textuals[-1].context:
                                # append a empty textual to the list, in order not to save the context in the lise
                                self._textuals.append(Textual('', ctxt))
                            # a new syllabic element is started by creating the respective context object
                            ctxt = Textual.Context()
                            ctxt.syllabic = 'end'
                            ctxt.elision = Textual('-', ctxt)
                        else:
                            txt = Textual(syllTxt, ctxt)
                            self._textuals.append(txt)

    def composeText(self, elisions=True, sylStart='-', wordStart=' ') -> str:
        '''
        composes a text representation of the contained lyrics

        user can set whether and how elisions in the lyrics shall be represented in the returned text:
        if elisions==False, the elisions stored will not be inserted into the output text.
        if elisions==True, the stored elision representation is inserted, and sylStart and wordStart in absence of text
        elisions may also be set to a string, which will overwrite the internal representation.
        This may be used to enforce consistent output or to avoid rare unicode symbols potentially used in elisions
        independent
        if elisions==False, always sylStart and wordStart will be still be inserted at syllable or word boundaries,
        wherever syllabic information is present. Also at the start or end of the resulting string
        They may be suppressed by setting them to an empty string
        :param elisions: bool whether to display elisions or symbol to use instead of the stored elision representations
        :param sylStart: text inserted before the start of a new syllable, if not elisions or no elision text is stored
        :param wordStart: text inserted before start of a new word, if not elisions or no elision text is stored
        :return:
        '''
        # TODO: add some example code to the doc
        rawTxtAccu = ''
        ctxt = None
        for tx in self._textuals:
            if not tx.context is ctxt:
                #  entered a new syllabic context=> prepend spacers as necessary
                ctxt = tx.context
                if ctxt and ctxt.syllabic:
                    if ctxt.syllabic in ['begin', 'single']:
                        if not elisions or not ctxt.elision:
                            rawTxtAccu += wordStart
                        elif ctxt.elision and isinstance(elisions, str):
                            rawTxtAccu += elisions
                        elif ctxt.elision and ctxt.elision.rawText:
                            rawTxtAccu += ctxt.elision.rawText
                        else:
                            rawTxtAccu += '_'
                    elif ctxt.syllabic in ['middle', 'end']:
                        if not elisions or not ctxt.elision:
                            rawTxtAccu += sylStart
                        elif ctxt.elision and isinstance(elisions, str):
                            rawTxtAccu += elisions
                        elif ctxt.elision and ctxt.elision.rawText:
                            rawTxtAccu += ctxt.elision.rawText
                        else:
                            rawTxtAccu += '_'
                elif ctxt and ctxt.elision:
                    # left a previous context with an elision, while the new context does not have a syllabic setting
                    # no official part of music-xml, unsure about other formats
                    # supported as an additional feature and for tolerance of malformed mxml
                    if isinstance(elisions, str):
                        rawTxtAccu += elisions
                    elif elisions and prevCtxt.elision.rawText:
                        rawTxtAccu += prevCtxt.elision.rawText
                    else:
                        rawTxtAccu += wordStart
            prevCtxt = tx.context
            rawTxtAccu += tx.rawText
        return rawTxtAccu

class Lyric(prebase.ProtoM21Object, style.StyleMixin):
    '''
    An object representing a single Lyric as part of a note's .lyrics property.

    The note.lyric property is a simple way of specifying a single lyric, but
    Lyric objects are needed for working with multiple lyrics.

    >>> l = note.Lyric(text='hello')
    >>> l
    <music21.note.Lyric number=1 syllabic=single text='hello'>

    Music21 processes leading and following hyphens intelligently...

    >>> l2 = note.Lyric(text='hel-')
    >>> l2
    <music21.note.Lyric number=1 syllabic=begin text='hel'>

    ...unless applyRaw is set to True

    >>> l3 = note.Lyric(number=3, text='hel-', applyRaw=True)
    >>> l3
    <music21.note.Lyric number=3 syllabic=single text='hel-'>

    Lyrics have four properties: text, number, identifier, syllabic (single,
    begin, middle, end, None)

    >>> l3.text
    'hel-'

    >>> l3.number
    3

    >>> l3.syllabic
    'single'

    Note musicXML only supports one 'identifier' attribute which is called
    'number' but which can be a number or a descriptive identifier like
    'part2verse1.' To preserve lyric ordering, music21 stores a number and a
    descriptive identifier separately. The descriptive identifier is by default
    the same as the number, but in cases where a string identifier is present,
    it will be different.
    '''
    _styleClass = style.TextStylePlacement
    # CLASS VARIABLES #

    __slots__ = (
        '_identifier',
        '_number',
        '_content',
    )

    # INITIALIZER #

    def __init__(self, text=None, number=1, **kwargs):
        super().__init__()
        self._identifier = None
        self._number = None
        self._content = None

        # given as begin, middle, end, or single
        syllabic = kwargs.get('syllabic', None)
        # bolean
        applyRaw = kwargs.get('applyRaw', None)

        if text is not None:
            self._content = LyricText(text, applyRaw=applyRaw, syllabic=syllabic)
        elif syllabic:
            # in general text-less lyrics with a syllabic context seem pointless seem point-less
            # For example in music-XML at least a text entry with value '' is required by the DTD
            # For this reson we also expect the user to specify some text (even if it is '')
            raise ValueError('setting a syllabic type requires a text')

        self.number = number
        self.identifier = kwargs.get('identifier', None)

    # PRIVATE METHODS #

    def _reprInternal(self):
        out = ''
        if self.number is not None:
            out += f'number={self.number} '
        if self._identifier is not None:
            out += f'identifier={self.identifier!r} '
        if self.rawText is not None:
            out += f'text={self.rawText}'
        return out

    # PUBLIC PROPERTIES #

    @property
    def identifier(self):
        '''
        By default, this is the same as self.number. However, if there is a
        descriptive identifier like 'part2verse1', it is stored here and
        will be different from self.number. When converting to musicXML,
        this property will be stored in the lyric 'number' attribute which
        can store a number or a descriptive identifier but not both.

        >>> l = note.Lyric()
        >>> l.number = 12
        >>> l.identifier
        12

        >>> l.identifier = 'Rainbow'
        >>> l.identifier
        'Rainbow'

        :rtype: str
        '''
        if self._identifier is None:
            return self._number
        else:
            return self._identifier

    @identifier.setter
    def identifier(self, value):
        self._identifier = value

    def composeText(self, elisions=True, sylStart='-', wordStart=' ') -> str:
        '''
        composes a text representation of the contained lyrics

        user can set whether and how elisions in the lyrics shall be represented in the returned text:
        if elisions==False, the elisions stored will not be inserted into the output text.
        if elisions==True, the stored elision representation is inserted, and sylStart and wordStart in absence of text
        elisions may also be set to a string, which will overwrite the internal representation.
        This may be used to enforce consistent output or to avoid rare unicode symbols potentially used in elisions
        independent
        if elisions==False, always sylStart and wordStart will be still be inserted at syllable or word boundaries,
        wherever syllabic information is present. Also at the start or end of the resulting string
        They may be suppressed by setting them to an empty string
        :param elisions: bool whether to display elisions or symbol to use instead of the stored elision representations
        :param sylStart: text inserted before the start of a new syllable, if not elisions or no elision text is stored
        :param wordStart: text inserted before start of a new word, if not elisions or no elision text is stored
        :return:
        '''
        # TODO: add some example code to the doc
        if type(self._content) is LyricText:
            return self._content.composeText(elisions, sylStart, wordStart)
        elif type(self._content) is LyricAbstraction:
            return wordStart + str(self._content) + wordStart
        elif type(self._content) is LyricExtension:
            return ''
        elif self._content is None:
            return ''
        else:
            raise NotImplementedError()

    @property
    def rawText(self) -> str:
        '''
        returns the text of the object with semantic annotations and the original elision texts
        '''
        return self.composeText(sylStart='-', wordStart=' ', elisions=True)

    @rawText.setter
    def rawText(self, t):
        self.setTextAndSyllabic(t, applyRaw=True)

    @property
    def text(self):
        '''
        returns the text of the object, without any unncessary syllabic annotations
        :return:
        '''
        # note: lstrip removes potential leading space added if lyrics start with a 'begin' syllabic
        return self.composeText(sylStart='', wordStart=' ', elisions=False).lstrip()

    @property
    def syllabic(self):
        '''
        retrieve the syllabic type of the lyrics, for backwards compatibility
        for complex lyrics composed of several syllables, this will raise an exception,
        # TODO: humming, laughing, extend?
        :return: one of [None, 'single', 'begin', 'middle', 'end']
        '''
        if self._content and type(self._content) is LyricText:
            return self._content.syllabic
        else:
            return None

    @property
    def number(self) -> int:
        '''
        This stores the number of the lyric (which determines the order
        lyrics appear in the score if there are multiple lyrics). Unlike
        the musicXML lyric number attribute, this value must always be a
        number; lyric order is always stored in this form. Descriptive
        identifiers like 'part2verse1' which can be found in the musicXML
        lyric number attribute should be stored in self.identifier.

        >>> l = note.Lyric('Hi')
        >>> l.number = 5
        >>> l.number
        5
        >>> l.number = None
        Traceback (most recent call last):
        music21.note.LyricException: Number best be number
        '''
        return self._number

    @number.setter
    def number(self, value: int) -> None:
        if not common.isNum(value):
            raise LyricException('Number best be number')
        self._number = value

    # PUBLIC METHODS #
    def appendTextual(self, textual : Textual):
        self._textuals.append(textual)

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, newContent):
        if newContent is None or type(newContent)in [LyricText, LyricExtension, LyricAbstraction]:
            self._content = newContent
        else:
            raise RuntimeError('Invalid type for lyrics content')

    def setTextAndSyllabic(self, rawText, applyRaw=False):
        if (not self._content) or type(self._content) is LyricText:
            self._content = LyricText()
        self._content.setTextAndSyllabic(self, rawText, applyRaw=applyRaw)

# ------------------------------------------------------------------------------


class GeneralNote(base.Music21Object):
    '''
    A GeneralNote object is the base class object
    for the :class:`~music21.note.Note`,
    :class:`~music21.note.Rest`, :class:`~music21.chord.Chord`,
    and related objects.

    Keywords can be passed to
    a GeneralNote which are then passed to the
    underlying :class:`~music21.duration.Duration`.
    These keywords might be listed like
    type='16th', dots=2 etc. to create a
    double-dotted sixteenth note.

    In almost every circumstance, you should
    create note.Note() or note.Rest() or note.Chord()
    objects directly, and not use this underlying
    structure.


    >>> gn = note.GeneralNote(type='16th', dots=2)
    >>> gn.quarterLength
    0.4375
    '''
    isNote = False
    isRest = False
    isChord = False
    _styleClass = style.NoteStyle

    # define order to present names in documentation; use strings
    _DOC_ORDER = ['duration', 'quarterLength']
    # documentation for all attributes (not properties or methods)
    _DOC_ATTR = {
        'isChord': 'Boolean read-only value describing if this object is a Chord.',
        'lyrics': 'A list of :class:`~music21.note.Lyric` objects.',
        'tie': 'either None or a :class:`~music21.note.Tie` object.',
        'expressions': '''a list of expressions (such
            as :class:`~music21.expressions.Fermata`, etc.)
            that are stored on this Note.''',
        'articulations': '''a list of articulations such
            as :class:`~music21.articulations.Staccato`, etc.) that are stored on this Note.'''
    }

    def __init__(self, *arguments, **keywords):
        if 'duration' not in keywords:
            # music21base does not automatically create a duration.
            if not keywords:
                tempDuration = duration.Duration(1.0)
            else:
                tempDuration = duration.Duration(**keywords)
                # only apply default if components are empty
                # looking at currentComponents so as not to trigger
                # _updateComponents
                if (tempDuration.quarterLength == 0
                        and not tempDuration.currentComponents()):
                    tempDuration.quarterLength = 1.0
        else:
            tempDuration = keywords['duration']
        # this sets the stored duration defined in Music21Object
        super().__init__(duration=tempDuration)

        self.lyrics = []  # a list of lyric objects
        self.expressions = []
        self.articulations = []

        if 'lyric' in keywords:
            self.addLyric(keywords['lyric'])

        # note: Chords handle ties differently
        self.tie = None  # store a Tie object

    def __eq__(self, other):
        '''
        General Note objects are equal if their durations are equal and
        they have the same articulation and expression classes (in any order)
        and their ties are equal.
        '''

        if other is None or not isinstance(other, GeneralNote):
            return NotImplemented
        # checks type, dots, tuplets, quarterLength, uses Pitch.__eq__
        if self.duration != other.duration:
            return False
        # articulations are a list of Articulation objects
        # converting to sets produces ordered cols that remove duplicate
        # however, must then convert to list to match based on class ==
        # not on class id()
        if (sorted({x.classes[0] for x in self.articulations})
                != sorted({x.classes[0] for x in other.articulations})):
            return False
        if (sorted({x.classes[0] for x in self.expressions})
                != sorted({x.classes[0] for x in other.expressions})):
            return False

        # Tie objects if present compare only type
        if self.tie != other.tie:
            return False
        return True

    # --------------------------------------------------------------------------
    def _getLyric(self) -> Optional[str]:
        if not self.lyrics:
            return None

        allText = [l.text for l in self.lyrics]
        return '\n'.join(allText)

    def _setLyric(self, value: str) -> None:
        self.lyrics = []
        if value in (None, False):
            return

        if not isinstance(value, str):
            value = str(value)

        values = value.split('\n')
        for i, v in enumerate(values):
            self.lyrics.append(Lyric(v, number=i + 1))

    lyric = property(_getLyric,
                     _setLyric,
                     doc=r'''
        The lyric property can
        be used to get and set a lyric for this
        Note, Chord, or Rest. This is a simplified version of the more general
        :meth:`~music21.note.GeneralNote.addLyric` method.

        >>> a = note.Note('A4')
        >>> a.lyrics
        []
        >>> a.lyric = 'hel-'
        >>> a.lyric
        'hel'
        >>> a.lyrics
        [<music21.note.Lyric number=1 syllabic=begin text='hel'>]

        Eliminate Lyrics by setting a.lyric to None

        >>> a.lyric = None
        >>> a.lyric
        >>> a.lyrics
        []

        Set multiple lyrics with \n separated text:

        >>> a.lyric = '1. Hi\n2. Bye'
        >>> a.lyric
        '1. Hi\n2. Bye'
        >>> a.lyrics
        [<music21.note.Lyric number=1 syllabic=single text='1. Hi'>,
         <music21.note.Lyric number=2 syllabic=single text='2. Bye'>]

        ''')

    def addLyric(self,
                 text,
                 lyricNumber=None,
                 *,
                 applyRaw=False,
                 lyricIdentifier=None) -> None:
        '''
        Adds a lyric, or an additional lyric, to a Note, Chord, or Rest's lyric list.
        If `lyricNumber` is not None, a specific line of lyric text can be set.
        The lyricIdentifier can also be set.

        >>> n1 = note.Note()
        >>> n1.addLyric('hello')
        >>> n1.lyrics[0].text
        'hello'
        >>> n1.lyrics[0].number
        1

        An added option gives the lyric number, not the list position

        >>> n1.addLyric('bye', 3)
        >>> n1.lyrics[1].text
        'bye'
        >>> n1.lyrics[1].number
        3
        >>> for lyr in n1.lyrics:
        ...     print(lyr.text)
        hello
        bye

        Replace an existing lyric by specifying the same number:

        >>> n1.addLyric('ciao', 3)
        >>> n1.lyrics[1].text
        'ciao'
        >>> n1.lyrics[1].number
        3

        Giving a lyric with a hyphen at either end will set whether it
        is part of a multisyllable word:

        >>> n1.addLyric('good-')
        >>> n1.lyrics[2].text
        'good'
        >>> n1.lyrics[2].syllabic
        'begin'

        This feature can be overridden by specifying the keyword only argument "applyRaw=True":

        >>> n1.addLyric('-5', applyRaw=True)
        >>> n1.lyrics[3].text
        '-5'
        >>> n1.lyrics[3].syllabic
        'single'
        '''
        if not isinstance(text, str):
            text = str(text)
        if lyricNumber is None:
            maxLyrics = len(self.lyrics) + 1
            self.lyrics.append(Lyric(text, maxLyrics,
                                     applyRaw=applyRaw, identifier=lyricIdentifier))
        else:
            foundLyric = False
            for thisLyric in self.lyrics:
                if thisLyric.number == lyricNumber:
                    thisLyric.text = text
                    foundLyric = True
                    break
            if foundLyric is False:
                self.lyrics.append(Lyric(text, lyricNumber,
                                         applyRaw=applyRaw, identifier=lyricIdentifier))

    def insertLyric(self, text, index=0, *, applyRaw=False, identifier=None):
        '''
        Inserts a lyric into the Note, Chord, or Rest's lyric list in front of
        the index specified (0 by default), using index + 1 as the inserted lyric's
        line number. shifts line numbers of all following lyrics in list

        >>> n1 = note.Note()
        >>> n1.addLyric('second')
        >>> n1.lyrics
        [<music21.note.Lyric number=1 syllabic=single text='second'>]
        >>> n1.insertLyric('first', 0)
        >>> n1.lyrics
        [<music21.note.Lyric number=1 syllabic=single text='first'>,
         <music21.note.Lyric number=2 syllabic=single text='second'>]

        OMIT_FROM_DOCS

        test inserting in the middle.

        >>> n1.insertLyric('newSecond', 1)
        >>> n1.lyrics
        [<music21.note.Lyric number=1 syllabic=single text='first'>,
         <music21.note.Lyric number=2 syllabic=single text='newSecond'>,
         <music21.note.Lyric number=3 syllabic=single text='second'>]

        Test number as lyric...

        >>> n1.insertLyric(0, 3)
        >>> n1.lyrics
        [<music21.note.Lyric number=1 syllabic=single text='first'>,
         <music21.note.Lyric number=2 syllabic=single text='newSecond'>,
         <music21.note.Lyric number=3 syllabic=single text='second'>,
         <music21.note.Lyric number=4 syllabic=single text='0'>]
        '''
        if not isinstance(text, str):
            text = str(text)
        for lyric in self.lyrics[index:]:
            lyric.number += 1
        self.lyrics.insert(index, Lyric(text, (index + 1),
                                        applyRaw=applyRaw, identifier=identifier))

    # --------------------------------------------------------------------------
    # properties common to Notes, Rests,

    # --------------------------------------------------------------------------
    def augmentOrDiminish(self, scalar, *, inPlace=False):
        '''
        Given a scalar greater than zero, return a Note with a scaled Duration.
        If `inPlace` is True, this is done in-place and the method returns None.
        If `inPlace` is False [default], this returns a modified deepcopy.

        Changed -- inPlace is now False as of version 5.

        >>> n = note.Note('g#')
        >>> n.quarterLength = 3
        >>> n.augmentOrDiminish(2, inPlace=True)
        >>> n.quarterLength
        6.0

        >>> c = chord.Chord(['g#', 'a#', 'd'])
        >>> c.quarterLength = 2
        >>> c.augmentOrDiminish(0.25, inPlace=True)
        >>> c.quarterLength
        0.5

        >>> n = note.Note('g#')
        >>> n.augmentOrDiminish(-1)
        Traceback (most recent call last):
        music21.note.NoteException: scalar must be greater than zero

        >>> n = note.Note()
        >>> n.quarterLength = 3
        >>> n2 = n.augmentOrDiminish(1/3, inPlace=False)
        >>> n2.quarterLength
        1.0
        >>> n.quarterLength
        3.0
        '''
        if not scalar > 0:
            raise NoteException('scalar must be greater than zero')

        if inPlace:
            post = self
        else:  # slight speedup could happen by setting duration to Zero before copying.
            post = copy.deepcopy(self)

        # this is never True.
        post.duration = post.duration.augmentOrDiminish(scalar)

        if not inPlace:
            return post
        else:
            return None

    # --------------------------------------------------------------------------
    def getGrace(self, *, appogiatura=False, inPlace=False):
        '''
        Return a grace version of this GeneralNote

        >>> n = note.Note('G4', quarterLength=2)
        >>> n.duration.quarterLength
        2.0
        >>> n.duration.isGrace
        False
        >>> n.duration
        <music21.duration.Duration 2.0>
        >>> n.duration.type
        'half'
        >>> n.duration.components
        (DurationTuple(type='half', dots=0, quarterLength=2.0),)

        >>> ng = n.getGrace()
        >>> ng.duration.quarterLength
        0.0
        >>> ng.duration.isGrace
        True
        >>> ng.duration
        <music21.duration.GraceDuration unlinked type:zero quarterLength:0.0>
        >>> ng.duration.type
        'zero'
        >>> ng.duration.components
        (DurationTuple(type='half', dots=0, quarterLength=0.0),)

        Appogiaturas are still a work in progress...

        >>> ng2 = n.getGrace(appogiatura=True)
        >>> ng2.duration
        <music21.duration.AppogiaturaDuration unlinked type:zero quarterLength:0.0>
        >>> ng2.duration.slash
        False

        Set inPlace to True to change the duration element on the Note.  This can have
        negative consequences if the Note is in a stream.

        >>> r = note.Rest(quarterLength=0.5)
        >>> r.getGrace(inPlace=True)
        >>> r.duration
        <music21.duration.GraceDuration unlinked type:zero quarterLength:0.0>
        '''
        if inPlace is False:
            e = copy.deepcopy(self)
        else:
            e = self

        e.duration = e.duration.getGraceDuration(appogiatura=appogiatura)

        if inPlace is False:
            return e


# ------------------------------------------------------------------------------
class NotRest(GeneralNote):
    '''
    Parent class for Note-like objects that are not rests; that is to say
    they have a stem, can be tied, and volume is important.
    Basically, that's a `Note` or
    `Unpitched` object for now.
    '''
    # unspecified means that there may be a stem, but its orientation
    # has not been declared.

    _DOC_ATTR = {
        'beams': '''
            A :class:`~music21.beam.Beams` object that contains
            information about the beaming of this note.''',
    }

    def __init__(self, *arguments, **keywords):
        super().__init__(**keywords)
        self._notehead = 'normal'
        self._noteheadFill = None
        self._noteheadParenthesis = False
        self._stemDirection = 'unspecified'
        self._volume = None  # created on demand
        # replace
        self.linkage = 'tie'
        if 'beams' in keywords:
            self.beams = keywords['beams']
        else:
            self.beams = beam.Beams()

    # ==============================================================================================
    # Special functions
    # ==============================================================================================
    def __eq__(self, other):
        if not super().__eq__(other):
            return False
        if not isinstance(other, NotRest):
            return False

        if self.notehead != other.notehead:
            return False
        if self.noteheadFill != other.noteheadFill:
            return False
        if self.noteheadParenthesis != other.noteheadParenthesis:
            return False
        # Q: should volume need to be equal?
        if self.beams != other.beams:
            return False
        return True

    def __deepcopy__(self, memo=None):
        '''
        As NotRest objects have a Volume, objects, and Volume objects
        store weak refs to the to client object, need to specialize deep copy handling

        >>> import copy
        >>> n = note.NotRest()
        >>> n.volume = volume.Volume(50)
        >>> m = copy.deepcopy(n)
        >>> m.volume.client is m
        True
        '''
        # environLocal.printDebug(['calling NotRest.__deepcopy__', self])
        new = super().__deepcopy__(memo=memo)
        # after copying, if a Volume exists, it is linked to the old object
        # look at _volume so as not to create object if not already there
        if self._volume is not None:
            new.volume.client = new  # update with new instance
        return new

    def __getstate__(self):
        state = super().__getstate__()
        if '_volume' in state and state['_volume'] is not None:
            state['_volume'].client = None
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        if self._volume is not None:
            self._volume.client = self
    ####

    def _getStemDirection(self) -> str:
        return self._stemDirection

    def _setStemDirection(self, direction):
        if direction is None:
            direction = 'unspecified'  # allow setting to None meaning
        elif direction == 'none':
            direction = 'noStem'  # allow setting to none or None
        elif direction not in stemDirectionNames:
            raise NotRestException('not a valid stem direction name: %s' % direction)
        self._stemDirection = direction

    stemDirection = property(_getStemDirection,
                             _setStemDirection,
                             doc='''
        Get or set the stem direction of this NotRest object.
        Valid stem direction names are found in note.stemDirectionNames (see below).

        >>> note.stemDirectionNames
        ('double', 'down', 'noStem', 'none', 'unspecified', 'up')
        >>> n = note.Note()

        By default a Note's stemDirection is 'unspecified'
        meaning that it is unknown:

        >>> n.stemDirection
        'unspecified'

        >>> n.stemDirection = 'noStem'
        >>> n.stemDirection
        'noStem'

        The alias 'none' (the string) is the same as 'noStem'

        >>> n.stemDirection = 'none'
        >>> n.stemDirection
        'noStem'

        >>> n.stemDirection = 'junk'
        Traceback (most recent call last):
        music21.note.NotRestException: not a valid stem direction name: junk

        Stem direction can be set explicitly to None to remove
        any prior stem information, same as 'unspecified':

        >>> n.stemDirection = None
        >>> n.stemDirection
        'unspecified'
        ''')

    def _getNotehead(self) -> str:
        return self._notehead

    def _setNotehead(self, value):
        if value in ('none', None, ''):
            value = None  # allow setting to none or None
        elif value not in noteheadTypeNames:
            raise NotRestException('not a valid notehead type name: %s' % repr(value))
        self._notehead = value

    notehead = property(_getNotehead,
                        _setNotehead,
                        doc='''
        Get or set the notehead type of this NotRest object.
        Valid notehead type names are found in note.noteheadTypeNames (see below):


        >>> note.noteheadTypeNames
        ('arrow down', 'arrow up', 'back slashed', 'circle dot', 'circle-x', 'circled', 'cluster',
         'cross', 'diamond', 'do', 'fa', 'inverted triangle', 'la', 'left triangle',
         'mi', 'none', 'normal', 'other', 're', 'rectangle', 'slash', 'slashed', 'so',
         'square', 'ti', 'triangle', 'x')
        >>> n = note.Note()
        >>> n.notehead = 'diamond'
        >>> n.notehead
        'diamond'

        >>> n.notehead = 'junk'
        Traceback (most recent call last):
        music21.note.NotRestException: not a valid notehead type name: 'junk'
        ''')

    def _getNoteheadFill(self) -> str:
        return self._noteheadFill

    def _setNoteheadFill(self, value):
        if value in ('none', None, 'default'):
            value = None  # allow setting to none or None
        if value in ('filled', 'yes'):
            value = True
        elif value in ('notfilled', 'no'):
            value = False
        if value not in (True, False, None):
            raise NotRestException('not a valid notehead fill value: %s' % value)
        self._noteheadFill = value

    noteheadFill = property(_getNoteheadFill,
                            _setNoteheadFill,
                            doc='''
        Get or set the note head fill status of this NotRest. Valid note head fill values are
        True, False, or None (meaning default).  "yes" and "no" are converted to True
        and False.

        >>> n = note.Note()
        >>> n.noteheadFill = 'no'
        >>> n.noteheadFill
        False
        >>> n.noteheadFill = 'filled'
        >>> n.noteheadFill
        True

        >>> n.noteheadFill = 'jelly'
        Traceback (most recent call last):
        music21.note.NotRestException: not a valid notehead fill value: jelly
        ''')

    def _getNoteheadParenthesis(self) -> bool:
        return self._noteheadParenthesis

    def _setNoteheadParenthesis(self, value):
        if value in (True, 'yes', 1):
            value = True
        elif value in (False, 'no', 0):
            value = False
        else:
            raise NotRestException('notehead parentheses must be True or False, not %r' % value)
        self._noteheadParenthesis = value

    noteheadParenthesis = property(_getNoteheadParenthesis,
                                   _setNoteheadParenthesis,
                                   doc='''
        Get or set the note head parentheses for this Note/Unpitched/Chord object.

        >>> n = note.Note()
        >>> n.noteheadParenthesis
        False
        >>> n.noteheadParenthesis = True
        >>> n.noteheadParenthesis
        True

        'yes' or 1 equate to True; 'no' or 0 to False

        >>> n.noteheadParenthesis = 'no'
        >>> n.noteheadParenthesis
        False

        Anything else raises an exception:

        >>> n.noteheadParenthesis = 'blah'
        Traceback (most recent call last):
        music21.note.NotRestException: notehead parentheses must be True or False, not 'blah'
        ''')

    # --------------------------------------------------------------------------
    def hasVolumeInformation(self) -> bool:
        '''
        Returns bool whether volume was set -- saving some time for advanced
        users (such as MusicXML exporters) that only want to look at the volume
        if it is already there.

        >>> n = note.Note()
        >>> n.hasVolumeInformation()
        False
        >>> n.volume
         <music21.volume.Volume realized=0.71>
        >>> n.hasVolumeInformation()
        True
        '''
        if self._volume is None:
            return False
        else:
            return True

    def _getVolume(self, forceClient=None) -> volume.Volume:
        # lazy volume creation
        if self._volume is None:
            if forceClient is None:
                # when creating the volume object, set the client as self
                self._volume = volume.Volume(client=self)
            else:
                self._volume = volume.Volume(client=forceClient)
        return self._volume

    def _setVolume(self, value, setClient=True):
        # setParent is only False when Chords bundling Notes
        # test by looking for method
        if value is None:
            self._volume = None
        elif hasattr(value, 'getDynamicContext'):
            if setClient:
                if value.client is not None:
                    value = copy.deepcopy(value)
                value.client = self  # set to self
            self._volume = value
        elif common.isNum(value) and setClient:
            # if we can define the client, we can set from numbers
            # call local getVolume will set client appropriately
            vol = self._getVolume()
            if value < 1:  # assume a scalar
                vol.velocityScalar = value
            else:  # assume velocity
                vol.velocity = value

        else:
            raise Exception('this must be a Volume object, not %s' % value)

    volume = property(_getVolume,
                      _setVolume,
                      doc='''
        Get and set the :class:`~music21.volume.Volume` object of this object.
        Volume objects are created on demand.

        >>> n1 = note.Note()
        >>> n1.volume.velocity = 120
        >>> n2 = note.Note()
        >>> n2.volume = 80  # can directly set a velocity value
        >>> s = stream.Stream()
        >>> s.append([n1, n2])
        >>> [n.volume.velocity for n in s.notes]
        [120, 80]
        ''')


# ------------------------------------------------------------------------------
class Note(NotRest):
    '''
    One of the most important music21 classes, a Note
    stores a single note (that is, not a rest or an unpitched element)
    that can be represented by one or more notational units -- so
    for instance a C quarter-note and a D# eighth-tied-to-32nd are both
    a single Note object.


    A Note knows both its total duration and how to express itself as a set of
    tied notes of different lengths. For instance, a note of 2.5 quarters in
    length could be half tied to eighth or dotted quarter tied to quarter.


    The first argument to the Note is the pitch name (with or without
    octave, see the introduction to :class:`music21.pitch.Pitch`).
    Further arguments can be specified as keywords (such as type, dots, etc.)
    and are passed to the underlying :class:`music21.duration.Duration` element.


    Two notes are considered equal if their most important attributes
    (such as pitch, duration,
    articulations, and ornaments) are equal.  Attributes
    that might change based on the wider context
    of a note (such as offset)
    are not compared. This test presently does not look at lyrics in
    establishing equality.  It may in the future.

    >>> n = note.Note()
    >>> n
    <music21.note.Note C>
    >>> n.pitch
    <music21.pitch.Pitch C4>

    >>> n = note.Note('B-')
    >>> n.name
    'B-'
    >>> n.octave is None
    True
    >>> n.pitch.implicitOctave
    4

    >>> n = note.Note(name='D#')
    >>> n.name
    'D#'
    >>> n = note.Note(nameWithOctave='D#5')
    >>> n.nameWithOctave
    'D#5'
    '''
    isNote = True

    # define order to present names in documentation; use strings
    _DOC_ORDER = ['duration', 'quarterLength', 'nameWithOctave']
    # documentation for all attributes (not properties or methods)
    _DOC_ATTR = {
        'isNote': 'Boolean read-only value describing if this Note is a Note (True).',
        'isRest': 'Boolean read-only value describing if this Note is a Rest (False).',
        'pitch': '''A :class:`~music21.pitch.Pitch` object containing all the
                information about the note's pitch.  Many `.pitch` properties and
                methods are also made `Note` properties also''',
    }

    # Accepts an argument for pitch
    def __init__(self, pitchName=None, **keywords):
        super().__init__(**keywords)

        if 'pitch' in keywords and pitchName is None:
            pitchName = keywords['pitch']
            del keywords['pitch']

        if pitchName is not None:
            if isinstance(pitchName, pitch.Pitch):
                self.pitch = pitchName
            else:  # assume first argument is pitch
                self.pitch = pitch.Pitch(pitchName, **keywords)
        else:  # supply a default pitch
            name = 'C4'
            if 'name' in keywords:
                name = keywords['name']
                del keywords['name']
            elif 'nameWithOctave' in keywords:
                name = keywords['nameWithOctave']
                del keywords['nameWithOctave']
            self.pitch = pitch.Pitch(name, **keywords)

    # --------------------------------------------------------------------------
    # operators, representations, and transformations

    def _reprInternal(self):
        return self.name

    def __eq__(self, other):
        '''
        Tests Equality. See docs under Note above
        (since __eq__'s docs don't display)

        >>> n1 = note.Note()
        >>> n1.pitch.name = 'G#'
        >>> n2 = note.Note()
        >>> n2.pitch.name = 'A-'
        >>> n3 = note.Note()
        >>> n3.pitch.name = 'G#'
        >>> n1 == n2
        False
        >>> n1 == n3
        True
        >>> n3.duration.quarterLength = 3
        >>> n1 == n3
        False

        >>> n1 == 5
        False
        '''
        if other is None or not isinstance(other, Note):
            return NotImplemented

        retVal = super().__eq__(other)
        if retVal is not True:
            return retVal

        # checks pitch.octave, pitch.accidental, uses Pitch.__eq__
        if self.pitch != other.pitch:
            return False
        return True

    def __lt__(self, other):
        '''
        __lt__, __gt__, __le__, __ge__ all use a pitch comparison.

        >>> highE = note.Note('E5')
        >>> lowF = note.Note('F2')
        >>> otherHighE = note.Note('E5')

        >>> highE > lowF
        True
        >>> highE < lowF
        False
        >>> highE >= otherHighE
        True
        >>> highE <= otherHighE
        True

        Notice you cannot compare Notes w/ ints or anything not pitched.

        ::
            `highE < 50`
            Traceback (most recent call last):
            TypeError: '<' not supported between instances of 'Note' and 'int'

        Note also that two objects can be >= and <= without being equal, because
        only pitch-height is being compared in <, <=, >, >= but duration and other
        elements are compared in equality.

        >>> otherHighE.duration.type = 'whole'
        >>> highE >= otherHighE
        True
        >>> highE <= otherHighE
        True
        >>> highE == otherHighE
        False


        OMIT_FROM_DOCS

        The `highE < 50` test fails on Python 3.5, because of a change to the
        TypeError output list.  When m21 becomes Python 3.6 > only, then
        we can add the test back in.
        '''
        try:
            return self.pitch < other.pitch
        except AttributeError:
            return NotImplemented

    # do not factor out into @total_ordering because of the difference between __eq__ and
    # the equal part of __le__ and __ge__
    def __gt__(self, other):
        try:
            return self.pitch > other.pitch
        except AttributeError:
            return NotImplemented

    def __le__(self, other):
        try:
            return self.pitch <= other.pitch
        except AttributeError:
            return NotImplemented

    def __ge__(self, other):
        try:
            return self.pitch >= other.pitch
        except AttributeError:
            return NotImplemented

    # --------------------------------------------------------------------------
    # property access

    def _getName(self) -> str:
        return self.pitch.name

    def _setName(self, value: str):
        self.pitch.name = value

    name = property(_getName,
                    _setName,
                    doc='''
        Return or set the pitch name from the :class:`~music21.pitch.Pitch` object.
        See `Pitch`'s attribute :attr:`~music21.pitch.Pitch.name`.
        ''')

    def _getNameWithOctave(self) -> str:
        return self.pitch.nameWithOctave

    def _setNameWithOctave(self, value: str):
        self.pitch.nameWithOctave = value

    nameWithOctave = property(_getNameWithOctave,
                              _setNameWithOctave,
                              doc='''
        Return or set the pitch name with octave from the :class:`~music21.pitch.Pitch` object.
        See `Pitch`'s attribute :attr:`~music21.pitch.Pitch.nameWithOctave`.
        ''')

    def _getStep(self) -> str:
        return self.pitch.step

    def _setStep(self, value: str):
        self.pitch.step = value

    step = property(_getStep,
                    _setStep,
                    doc='''
        Return or set the pitch step from the :class:`~music21.pitch.Pitch` object.
        See :attr:`~music21.pitch.Pitch.step`.
        ''')

    def _getOctave(self) -> int:
        return self.pitch.octave

    def _setOctave(self, value: int):
        self.pitch.octave = value

    octave = property(_getOctave,
                      _setOctave,
                      doc='''
        Return or set the octave value from the :class:`~music21.pitch.Pitch` object.
        See :attr:`~music21.pitch.Pitch.octave`.
        ''')

    def _getPitches(self):
        return (self.pitch,)

    def _setPitches(self, value):
        if common.isListLike(value):
            self.pitch = value[0]
        else:
            raise NoteException('cannot set pitches with provided object: %s' % value)

    pitches = property(_getPitches,
                       _setPitches,
                       doc='''
        Return the :class:`~music21.pitch.Pitch` object in a tuple.
        This property is designed to provide an interface analogous to
        that found on :class:`~music21.chord.Chord` so that `[c.pitches for c in s.notes]`
        provides a consistent interface for all objects.

        >>> n = note.Note('g#')
        >>> n.nameWithOctave
        'G#'
        >>> n.pitches
        (<music21.pitch.Pitch G#>,)

        Since this is a Note, not a chord, from the list or tuple,
        only the first one will be used:

        >>> n.pitches = [pitch.Pitch('c2'), pitch.Pitch('g2')]
        >>> n.nameWithOctave
        'C2'
        >>> n.pitches
        (<music21.pitch.Pitch C2>,)

        The value for setting must be a list or tuple:

        >>> n.pitches = pitch.Pitch('C4')
        Traceback (most recent call last):
        music21.note.NoteException: cannot set pitches with provided object: C4

        For setting a single one, use `n.pitch` instead.

        Don't use strings, or you will get a string back!

        >>> n.pitches = ('C4', 'D4')
        >>> n.pitch
        'C4'
        >>> n.pitch.diatonicNoteNum
        Traceback (most recent call last):
        AttributeError: 'str' object has no attribute 'diatonicNoteNum'
        ''')

    def transpose(self, value, *, inPlace=False):
        '''
        Transpose the Note by the user-provided
        value. If the value is an integer, the transposition is treated in half steps.

        If the value is a string, any Interval string specification can be provided.

        >>> a = note.Note('g4')
        >>> b = a.transpose('m3')
        >>> b
        <music21.note.Note B->
        >>> aInterval = interval.Interval(-6)
        >>> b = a.transpose(aInterval)
        >>> b
        <music21.note.Note C#>

        >>> c = b.transpose(interval.GenericInterval(2))
        >>> c
        <music21.note.Note D#>

        >>> a.transpose(aInterval, inPlace=True)
        >>> a
        <music21.note.Note C#>


        If the transposition value is an integer, take the KeySignature or Key context
        into account...

        >>> s = stream.Stream()
        >>> s.append(key.Key('D'))
        >>> s.append(note.Note('F'))
        >>> s.append(key.Key('b-', 'minor'))
        >>> s.append(note.Note('F'))
        >>> s.show('text')
        {0.0} <music21.key.Key of D major>
        {0.0} <music21.note.Note F>
        {1.0} <music21.key.Key of b- minor>
        {1.0} <music21.note.Note F>
        >>> for n in s.notes:
        ...     n.transpose(1, inPlace=True)
        >>> s.show('text')
        {0.0} <music21.key.Key of D major>
        {0.0} <music21.note.Note F#>
        {1.0} <music21.key.Key of b- minor>
        {1.0} <music21.note.Note G->

        '''
        if hasattr(value, 'classes') and 'IntervalBase' in value.classes:
            intervalObj = value
        else:  # try to process
            intervalObj = interval.Interval(value)

        if not inPlace:
            post = copy.deepcopy(self)
        else:
            post = self

        # use inPlace, b/c if we are inPlace, we operate on self;
        # if we are not inPlace, post is a copy
        post.pitch.transpose(intervalObj, inPlace=True)
        if (post.pitch.accidental is not None
                and isinstance(value, (int, interval.ChromaticInterval))):
            ksContext = self.getContextByClass('KeySignature')
            if ksContext is not None:
                for alteredPitch in ksContext.alteredPitches:
                    if (post.pitch.pitchClass == alteredPitch.pitchClass
                            and post.pitch.accidental.alter != alteredPitch.accidental.alter):
                        post.pitch.getEnharmonic(inPlace=True)

        if not inPlace:
            post.derivation.method = 'transpose'
            return post
        else:
            return None

    @property
    def fullName(self) -> str:
        '''
        Return the most complete representation of this Note,
        providing duration and pitch information.


        >>> n = note.Note('A-', quarterLength=1.5)
        >>> n.fullName
        'A-flat Dotted Quarter Note'

        >>> n = note.Note('E~3', quarterLength=2)
        >>> n.fullName
        'E-half-sharp in octave 3 Half Note'

        >>> n = note.Note('D', quarterLength=0.25)
        >>> n.pitch.microtone = 25
        >>> n.fullName
        'D (+25c) 16th Note'
        '''
        msg = []
        msg.append('%s ' % self.pitch.fullName)
        msg.append(self.duration.fullName)
        msg.append(' Note')
        return ''.join(msg)


# ------------------------------------------------------------------------------
# convenience classes


# ------------------------------------------------------------------------------
class Unpitched(NotRest):
    '''
    A General class of unpitched objects which appear at different places
    on the staff.  Examples: percussion notation.

    The `Unpitched` object does not currently do anything and should
    not be used.

    >>> unp = note.Unpitched()

    Unpitched elements have displayStep and displayOctave
    which shows where they should be displayed, but they do not have pitch
    objects:

    >>> unp.displayStep
    'C'
    >>> unp.displayOctave
    4
    >>> unp.displayStep = 'G'
    >>> unp.pitch
    Traceback (most recent call last):
    AttributeError: 'Unpitched' object has no attribute 'pitch'
    '''

    def __init__(self):
        super().__init__()
        self.displayStep = 'C'
        self.displayOctave = 4
        self._storedInstrument = None

    def __eq__(self, other):
        if not super().__eq__(other):
            return False
        if not isinstance(other, Unpitched):
            return False
        if self.displayStep != other.displayStep:
            return False
        if self.displayOctave != other.displayOctave:
            return False
        return True

    def _getStoredInstrument(self):
        return self._storedInstrument

    def _setStoredInstrument(self, newValue):
        self._storedInstrument = newValue

    storedInstrument = property(_getStoredInstrument, _setStoredInstrument)

    def displayPitch(self) -> pitch.Pitch:
        '''
        returns a pitch object that is the same as the displayStep and displayOctave.
        it will never have an accidental.

        >>> unp = note.Unpitched()
        >>> unp.displayStep = 'E'
        >>> unp.displayOctave = 4
        >>> unp.displayPitch()
        <music21.pitch.Pitch E4>
        '''
        p = pitch.Pitch()
        p.step = self.displayStep
        p.octave = self.displayOctave
        return p


# ------------------------------------------------------------------------------
class Rest(GeneralNote):
    '''
    Rests are represented in music21 as GeneralNote objects that do not have
    a pitch object attached to them.  By default they have length 1.0 (Quarter Rest)

    Calling :attr:`~music21.stream.Stream.notes` on a Stream does not get rests.
    However, the property :attr:`~music21.stream.Stream.notesAndRests` of Streams
    gets rests as well.


    >>> r = note.Rest()
    >>> r.isRest
    True
    >>> r.isNote
    False
    >>> r.duration.quarterLength = 2.0
    >>> r.duration.type
    'half'

    All Rests have the name property 'rest':

    >>> r.name
    'rest'
    '''
    isRest = True
    name = 'rest'

    _DOC_ATTR = {
        'isNote': 'Boolean read-only value describing if this Rest is a Note (False).',
        'isRest': 'Boolean read-only value describing if this Rest is a Rest (True, obviously).',
        'name': '''returns "rest" always.  It is here so that you can get
               `x.name` on all `.notesAndRests` objects''',
        'stepShift': 'number of lines/spaces to shift the note upwards or downwards for display.',
        'fullMeasure': '''does this rest last a full measure (thus display as whole, center, etc.)
                Options are False, True, "always", "auto" (default)

                False means do not set as full measure, no matter what.

                True keeps the set duration, but will always display as a full measure rest.

                "always" means the duration will (EVENTUALLY, not yet!)
                update automatically to match the time signature context; and is True.
                Does not work yet -- functions as True.

                # TODO: get it to work.

                "auto" is the default, where if the rest value happens to match the current
                time signature context, then display it as a whole note, centered, etc.
                otherwise will display normally.

                See examples in :meth:`music21.musicxml.m21ToXml.MeasureExporter.restToXml`
                ''',
    }

    def __init__(self, *arguments, **keywords):
        super().__init__(**keywords)
        self.stepShift = 0  # display line
        self.fullMeasure = 'auto'  # see docs; True, False, 'always',

    def _reprInternal(self):
        return self.name

    def __eq__(self, other):
        '''
        A Music21 rest is equal to another object if that object is also a rest which
        has the same duration.


        >>> r1 = note.Rest()
        >>> r2 = note.Rest()
        >>> r1 == r2
        True
        >>> r1 != r2
        False

        >>> r2.duration.quarterLength = 4.0/3
        >>> r1 == r2
        False
        >>> r1 == note.Note()
        False
        '''
        if not isinstance(other, Rest):
            return NotImplemented

        return super().__eq__(other)

    @property
    def fullName(self) -> str:
        '''
        Return the most complete representation of this Rest,
        providing duration information.

        >>> r = note.Rest(quarterLength=1.5)
        >>> r.fullName
        'Dotted Quarter Rest'

        >>> note.Rest(type='whole').fullName
        'Whole Rest'
        '''
        return self.duration.fullName + ' Rest'


class SpacerRest(Rest):
    '''
    This is exactly the same as a rest, but it is a SpacerRest.
    This object should only be used for making hidden space in a score in lilypond.

    This may become deprecated at some point...

    >>> sr = note.SpacerRest(type='whole')
    >>> sr
    <music21.note.SpacerRest rest duration=4.0>
    '''

    def __init__(self, *arguments, **keywords):
        super().__init__(**keywords)

    def _reprInternal(self):
        return f'{self.name} duration={self.duration.quarterLength}'


# ------------------------------------------------------------------------------
# test methods and classes

class TestExternal(unittest.TestCase):  # pragma: no cover
    '''
    These are tests that open windows and rely on external software
    '''

    def runTest(self):
        pass

    def testSingle(self):
        '''Need to test direct meter creation w/o stream
        '''
        a = Note('d-3')
        a.quarterLength = 2.25
        a.show()

    def testBasic(self):
        from music21 import stream
        a = stream.Stream()

        for pitchName, qLen in [('d-3', 2.5), ('c#6', 3.25), ('a--5', 0.5),
                                ('f', 1.75), ('g3', 1.5), ('d##4', 1.25),
                                ('d-3', 2.5), ('c#6', 3.25), ('a--5', 0.5),
                                ('f#2', 1.75), ('g-3', 1.33333), ('d#6', 0.6666)
                                ]:
            b = Note()
            b.quarterLength = qLen
            b.name = pitchName
            b.style.color = '#FF00FF'
            a.append(b)

        a.show()


# ------------------------------------------------------------------------------
class Test(unittest.TestCase):

    def runTest(self):
        pass

    def testCopyAndDeepcopy(self):
        '''
        Test copying all objects defined in this module
        '''
        import sys
        import types
        for part in sys.modules[self.__module__].__dict__:
            match = False
            for skip in ['_', '__', 'Test', 'Exception']:
                if part.startswith(skip) or part.endswith(skip):
                    match = True
            if match:
                continue
            name = getattr(sys.modules[self.__module__], part)
            if callable(name) and not isinstance(name, types.FunctionType):
                try:  # see if obj can be made w/ args
                    obj = name()
                except TypeError:  # pragma: no cover
                    continue
                a = copy.copy(obj)
                b = copy.deepcopy(obj)
                self.assertNotEqual(id(a), id(b))

    def testLyricRepr(self):
        from music21 import note
        ly = note.Lyric()
        self.assertEqual(repr(ly), '<music21.note.Lyric number=1>')
        ly.text = 'hi'
        self.assertEqual(repr(ly), "<music21.note.Lyric number=1 text='hi'>")
        ly.identifier = 'verse'
        self.assertEqual(repr(ly), "<music21.note.Lyric number=1 identifier='verse' text='hi'>")
        ly.text = None
        self.assertEqual(repr(ly), "<music21.note.Lyric number=1 identifier='verse'>")

    def testComplex(self):
        note1 = Note()
        note1.duration.clear()
        d1 = duration.DurationTuple('whole', 0, 4.0)
        d2 = duration.DurationTuple('quarter', 0, 1.0)
        note1.duration.addDurationTuple(d1)
        note1.duration.addDurationTuple(d2)
        self.assertEqual(note1.duration.quarterLength, 5.0)
        self.assertEqual(note1.duration.componentIndexAtQtrPosition(2), 0)
        self.assertEqual(note1.duration.componentIndexAtQtrPosition(4), 1)
        self.assertEqual(note1.duration.componentIndexAtQtrPosition(4.5), 1)
        note1.duration.sliceComponentAtPosition(1.0)

        matchStr = "c'4~\nc'2.~\nc'4"
        from music21.lily.translate import LilypondConverter
        conv = LilypondConverter()
        conv.appendM21ObjectToContext(note1)
        outStr = str(conv.context).replace(' ', '').strip()
        # print(outStr)
        self.assertEqual(matchStr, outStr)
        i = 0
        for thisNote in note1.splitAtDurations():
            matchSub = matchStr.split('\n')[i]
            conv = LilypondConverter()
            conv.appendM21ObjectToContext(thisNote)
            outStr = str(conv.context).replace(' ', '').strip()
            self.assertEqual(matchSub, outStr)
            i += 1

    def testNote(self):
        note2 = Rest()
        self.assertTrue(note2.isRest)
        note3 = Note()
        note3.pitch.name = 'B-'
        # not sure how to test not None
        # self.assertFalse (note3.pitch.accidental, None)
        self.assertEqual(note3.pitch.accidental.name, 'flat')
        self.assertEqual(note3.pitch.pitchClass, 10)

        a5 = Note()
        a5.name = 'A'
        a5.octave = 5
        self.assertAlmostEqual(a5.pitch.frequency, 880.0)
        self.assertEqual(a5.pitch.pitchClass, 9)

    def testCopyNote(self):
        a = Note()
        a.quarterLength = 3.5
        a.name = 'D'
        b = copy.deepcopy(a)
        self.assertEqual(b.name, a.name)

    def testMusicXMLFermata(self):
        from music21 import corpus
        a = corpus.parse('bach/bwv5.7')
        found = []
        for n in a.flat.notesAndRests:
            for obj in n.expressions:
                if isinstance(obj, expressions.Fermata):
                    found.append(obj)
        self.assertEqual(len(found), 24)

    def testNoteBeatProperty(self):
        from music21 import stream, meter

        data = [
            ['3/4', 0.5, 6, [1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
             [1.0] * 6, ],
            ['3/4', 0.25, 8, [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75],
             [1.0] * 8],
            ['3/2', 0.5, 8, [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75],
             [2.0] * 8],

            ['6/8', 0.5, 6, [1.0, 1.3333, 1.66666, 2.0, 2.3333, 2.666666],
             [1.5] * 6],
            ['9/8', 0.5, 6, [1.0, 1.3333, 1.66666, 2.0, 2.3333, 2.666666],
             [1.5] * 6],
            ['12/8', 0.5, 6, [1.0, 1.3333, 1.66666, 2.0, 2.3333, 2.666666],
             [1.5] * 6],

            ['6/16', 0.25, 6, [1.0, 1.3333, 1.66666, 2.0, 2.3333, 2.666666],
             [0.75] * 6],

            ['5/4', 1, 5, [1.0, 2.0, 3.0, 4.0, 5.0],
             [1.] * 5],

            ['2/8+3/8+2/8', 0.5, 6, [1.0, 1.5, 2.0, 2.33333, 2.66666, 3.0],
             [1., 1., 1.5, 1.5, 1.5, 1.]],

        ]

        # one measure case
        for tsStr, nQL, nCount, matchBeat, matchBeatDur in data:
            n = Note()  # need fully qualified name
            n.quarterLength = nQL
            m = stream.Measure()
            m.timeSignature = meter.TimeSignature(tsStr)
            m.repeatAppend(n, nCount)

            self.assertEqual(len(m), nCount + 1)

            # test matching beat proportion value
            post = [m.notesAndRests[i].beat for i in range(nCount)]
            for i in range(len(matchBeat)):
                self.assertAlmostEqual(post[i], matchBeat[i], 4)

            # test getting beat duration
            post = [m.notesAndRests[i].beatDuration.quarterLength for i in range(nCount)]

            for i in range(len(matchBeat)):
                self.assertAlmostEqual(post[i], matchBeatDur[i], 4)

        # two measure case
        for tsStr, nQL, nCount, matchBeat, matchBeatDur in data:
            p = stream.Part()
            n = Note()
            n.quarterLength = nQL

            # m1 has time signature
            m1 = stream.Measure()
            m1.timeSignature = meter.TimeSignature(tsStr)
            p.append(m1)

            # m2 does not have time signature
            m2 = stream.Measure()
            m2.repeatAppend(n, nCount)
            self.assertEqual(len(m2), nCount)
            self.assertEqual(len(m2.notesAndRests), nCount)

            p.append(m2)

            # test matching beat proportion value
            post = [m2.notesAndRests[i].beat for i in range(nCount)]
            for i in range(len(matchBeat)):
                self.assertAlmostEqual(post[i], matchBeat[i], 4)
            # test getting beat duration
            post = [m2.notesAndRests[i].beatDuration.quarterLength for i in range(nCount)]
            for i in range(len(matchBeat)):
                self.assertAlmostEqual(post[i], matchBeatDur[i], 4)

    def testNoteBeatPropertyCorpus(self):
        data = [['bach/bwv255', [4.0, 1.0, 2.5, 3.0, 4.0, 4.5, 1.0, 1.5]],
                ['bach/bwv153.9', [1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 1.0, 3.0, 1.0]]
                ]

        for work, match in data:
            from music21 import corpus
            s = corpus.parse(work)
            # always use tenor line
            found = []
            for n in s.parts[2].flat.notesAndRests:
                n.lyric = n.beatStr
                found.append(n.beat)

            for i in range(len(match)):
                self.assertEqual(match[i], found[i])

            # s.show()

    def testNoteEquality(self):
        from music21 import articulations

        n1 = Note('a#')
        n2 = Note('g')
        n3 = Note('a-')
        n4 = Note('a#')

        self.assertNotEqual(n1, n2)
        self.assertNotEqual(n1, n3)
        self.assertEqual(n1, n4)

        # test durations with the same pitch
        for x, y, match in [
            (1, 1, True),
            (1, 0.5, False),
            (1, 2, False),
            (1, 1.5, False)
        ]:
            n1.quarterLength = x
            n4.quarterLength = y
            self.assertEqual(n1 == n4, match)  # sub1

        # test durations with different pitch
        for x, y, match in [(1, 1, False), (1, 0.5, False),
                            (1, 2, False), (1, 1.5, False)]:
            n1.quarterLength = x
            n2.quarterLength = y
            self.assertEqual(n1 == n2, match)  # sub2

        # same pitches different octaves
        n1.quarterLength = 1.0
        n4.quarterLength = 1.0
        for x, y, match in [(4, 4, True), (3, 4, False), (2, 4, False)]:
            n1.pitch.octave = x
            n4.pitch.octave = y
            self.assertEqual(n1 == n4, match)  # sub4

        # with and without ties
        n1.pitch.octave = 4
        n4.pitch.octave = 4
        t1 = tie.Tie()
        t2 = tie.Tie()
        for x, y, match in [(t1, None, False), (t1, t2, True)]:
            n1.tie = x
            n4.tie = y
            self.assertEqual(n1 == n4, match)  # sub4

        # with ties but different pitches
        for n in [n1, n2, n3, n4]:
            n.quarterLength = 1.0
        t1 = tie.Tie()
        t2 = tie.Tie()
        for a, b, match in [(n1, n2, False), (n1, n3, False),
                            (n2, n3, False), (n1, n4, True)]:
            a.tie = t1
            b.tie = t2
            self.assertEqual(a == b, match)  # sub5

        # articulation groups
        a1 = [articulations.Accent()]
        a2 = [articulations.Accent(), articulations.StrongAccent()]
        a3 = [articulations.StrongAccent(), articulations.Accent()]
        a4 = [articulations.StrongAccent(), articulations.Accent(),
              articulations.Tenuto()]
        a5 = [articulations.Accent(), articulations.Tenuto(),
              articulations.StrongAccent()]

        for a, b, c, d, match in [(n1, n4, a1, a1, True),
                                      (n1, n2, a1, a1, False), (n1, n3, a1, a1, False),
                                  # same pitch different orderings
                                  (n1, n4, a2, a3, True), (n1, n4, a4, a5, True),
                                  # different pitch same orderings
                                  (n1, n2, a2, a3, False), (n1, n3, a4, a5, False),
                                  ]:
            a.articulations = c
            b.articulations = d
            self.assertEqual(a == b, match)  # sub6

    def testMetricalAccent(self):
        from music21 import meter, stream
        data = [
            ('4/4', 8, 0.5, [1.0, 0.125, 0.25, 0.125, 0.5, 0.125, 0.25, 0.125]),
            ('3/4', 6, 0.5, [1.0, 0.25, 0.5, 0.25, 0.5, 0.25]),
            ('6/8', 6, 0.5, [1.0, 0.25, 0.25, 0.5, 0.25, 0.25]),

            ('12/32', 12, 0.125, [1.0, 0.125, 0.125, 0.25, 0.125, 0.125,
                                  0.5, 0.125, 0.125, 0.25, 0.125, 0.125]),

            ('5/8', 10, 0.25, [1.0, 0.25, 0.5, 0.25, 0.5, 0.25, 0.5, 0.25, 0.5, 0.25]),

            # test notes that do not have defined accents
            ('4/4', 16, 0.25, [1.0, 0.0625, 0.125, 0.0625, 0.25, 0.0625, 0.125, 0.0625,
                               0.5, 0.0625, 0.125, 0.0625, 0.25, 0.0625, 0.125, 0.0625]),
            ('4/4', 32, 0.125, [1.0, 0.0625, 0.0625, 0.0625, 0.125, 0.0625, 0.0625, 0.0625,
                                0.25, 0.0625, 0.0625, 0.0625, 0.125, 0.0625, 0.0625, 0.0625,
                                0.5, 0.0625, 0.0625, 0.0625, 0.125, 0.0625, 0.0625, 0.0625,
                                0.25, 0.0625, 0.0625, 0.0625, 0.125, 0.0625, 0.0625, 0.0625]),
        ]

        for tsStr, nCount, dur, match in data:

            m = stream.Measure()
            m.timeSignature = meter.TimeSignature(tsStr)
            n = Note()
            n.quarterLength = dur
            m.repeatAppend(n, nCount)

            self.assertEqual([n.beatStrength for n in m.notesAndRests], match)

    def testTieContinue(self):
        from music21 import stream

        n1 = Note()
        n1.tie = tie.Tie()
        n1.tie.type = 'start'

        n2 = Note()
        n2.tie = tie.Tie()
        n2.tie.type = 'continue'

        n3 = Note()
        n3.tie = tie.Tie()
        n3.tie.type = 'stop'

        s = stream.Stream()
        s.append([n1, n2, n3])

        # need to test that this gets us a continue tie, but hard to test
        # post musicxml processing
        # s.show()

    def testVolumeA(self):
        v1 = volume.Volume()

        n1 = Note()
        n2 = Note()

        n1.volume = v1  # can set as v1 has no client
        self.assertEqual(n1.volume, v1)
        self.assertEqual(n1.volume.client, n1)

        # object is created on demand
        self.assertIsNot(n2.volume, v1)
        self.assertIsNotNone(n2.volume)

    def testVolumeB(self):
        # manage deepcopying properly
        n1 = Note()

        n1.volume.velocity = 100
        self.assertEqual(n1.volume.velocity, 100)
        self.assertEqual(n1.volume.client, n1)

        n1Copy = copy.deepcopy(n1)
        self.assertEqual(n1Copy.volume.velocity, 100)
        self.assertEqual(n1Copy.volume.client, n1Copy)


# ------------------------------------------------------------------------------
# define presented order in documentation
_DOC_ORDER = [Note, Rest, SpacerRest, Unpitched, NotRest, GeneralNote, Lyric]

if __name__ == '__main__':
    # sys.arg test options will be used in mainTest()
    import music21
    music21.mainTest(Test)
