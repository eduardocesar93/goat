# -*- coding: utf-8 -*-
#
#    Copyright (C) 2014 Rodrigo Silva (MestreLion) <linux@rodrigosilva.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. See <http://www.gnu.org/licenses/gpl.html>

'''Go Game, Board, Moves classes wrappers'''

import os
import logging
import json

import gomill.sgf
import gomill.sgf_moves
import gomill.sgf_properties

import globals as g
import utils


log = logging.getLogger(__name__)

EMPTY = ' '
BLACK = '#'
WHITE = 'O'


class GoGameError(Exception):
    pass


class GoGame(object):
    '''Class representing a Go game
        Attributes populated after loading the SGF file (when object is instantiated):
        - sgffile: Full path to the SGF source file
        - sgfgame: Gomill Sgf_game instance
        - header: Root of sgfgame containing game headers
        - size: Board size
        - winner: color of game winner

        Attributes populated after .setup():
        - id: 12 char string uniquely identifying the game (letter coords of moves 20, 40, 60, 31, 51, 71)
            may be passed to constructor
        - description: String of player names and ranks, game result and date
            requires all such headers to be present
        - initialboard: Board instance of initial board layout. Empty if game has no handicap
        - moves: List of all moves. Each move is a (color, (row, col)) tuple
        - sgfboard: Gomill Board instance after initial setup and before first move

        Attributes populated after .play()
        - boards: List of boards

    '''
    def __init__(self, sgffile, id="", autosetup=True, autoplay=True):
        self.sgffile = sgffile
        self.sgfgame = self._sgfgame(self.sgffile)
        self.header = self.sgfgame.get_root()
        self.size = self.sgfgame.get_size()

        try:
            self.winner = self.sgfgame.get_winner()
        except ValueError as e:
            raise GoGameError("No winner: %s" % e)

        self.id = id
        self.description = ""
        self.initialboard = None
        self.moves = []
        self.sgfboard = None
        if autosetup:
            self.setup()

        self.boards = []
        if autoplay:
            self.play()

    def _sgfgame(self, sgffile):
        with open(sgffile, 'r') as fp:
            try:
                return gomill.sgf.Sgf_game.from_string(fp.read())
            except ValueError as e:
                raise GoGameError(e)

    def _gameid(self, moves, size):
        id = ""
        maxmoves = len(moves)
        for move in [20, 40, 60, 31, 51, 71]:
            if move <= maxmoves:
                id += gomill.sgf_properties.serialise_go_point(moves[move-1][1], size)
            else:
                id += "--"
        return id

    def setup(self):
        sgfmovemap = {
            None  : EMPTY,
            "b"   : BLACK,
            "w"   : WHITE,
        }

        try:
            self.sgfboard, sgfmoves = gomill.sgf_moves.get_setup_and_moves(self.sgfgame)
            self.moves = tuple((sgfmovemap[color], coord) for color, coord in sgfmoves)
            self.initialboard = Board(self.size, self.sgfboard.copy().board)   # FIXME: Boards are no longer compatible!
            if not self.id:
                self.id = self._gameid(self.moves, self.size)
            self.description = "%s(%s) vs %s(%s) %s %s" % (self.header.get("PB"),
                                                           self.header.get("BR"),
                                                           self.header.get("PW"),
                                                           self.header.get("WR"),
                                                           self.header.get("RE"),
                                                           self.header.get("DT"),)
        except ValueError as e:
            raise GoGameError(e)

    def play(self):
        if not self.id:
            self.setup()

        boardfile = os.path.join(g.USERDIR, 'boards', self.id[:2], "%s.json" % self.id)

        try:
            with open(boardfile, 'r') as fp:
                # id, board size, description, moves count, initial board, moves list
                _, size, _, _, initialboard, moves = json.load(fp)

            self.initialboard = Board.from_ascii(size, initialboard)

            # play index, move, ascii board
            for _, _, asciiboard in moves:
                self.boards.append(Board.from_ascii(size, asciiboard))

        except IOError:
            # Play the SGF game
            jsonplays = []
            sgfboard = self.sgfboard.copy()

            for m, move in enumerate(self.moves, 1):
                color, coord = move
                if coord is not None:
                    row, col = coord
                    try:
                        sgfboard.play(row, col, color)
                    except Exception:
                        raise GoGameError("Invalid move #%d: %s[%s]" % (
                            m,
                            color.upper(),
                            gomill.sgf_properties.serialise_go_point(coord, self.size)))

                board = Board(self.size, sgfboard.copy().board)  # FIXME: Boards are no longer compatible!
                self.boards.append(board)
                jsonplays.append('[%d, ["%s", %s], %s]' % (m,
                                                          color,
                                                          'null' if coord is None else list(coord),
                                                          board.dumpjson()))

            # Save the boards to JSON
            utils.safemakedirs(os.path.dirname(boardfile))
            with open(boardfile, 'w') as fp:
                fp.write('["%s", %d, "%s", %d, %s, [\n%s\n]]\n' % (
                   self.id,
                   self.size,
                   self.description,
                   len(self.moves),
                   self.initialboard.dumpjson(),
                   ",\n".join(jsonplays)))


class Board(object):

    _to_ascii = {
        EMPTY : " ",
        BLACK : "x",
        WHITE : "o",
    }

    @classmethod
    def from_ascii(cls, size, asciiboard):
        board = list(reversed(asciiboard))
        return cls(size, board)

    def __init__(self, size=0, board=None):
        self.size = size

        if board is None:
            self.board = []
            for _ in range(self.size):
                self.board.append([EMPTY] * self.size)
        else:
            self.board = board

    def get(self, row, col):
        return self.board[row][col]

    def set(self, color, row, col):
        self.board[row][col] = color

    def points(self):
        for row in xrange(self.size):
            for col in xrange(self.size):
                yield self.board[row][col]

    def dumpjson(self, indent=0):
        spc = indent * " "
        sep = '",\n%s"' % spc
        return '[\n%s"%s"\n]' % (spc, sep.join(self.asciilines()))

    def asciilines(self):
        for row in xrange(self.size - 1, -1, -1):
            line = ""
            for col in xrange(self.size):
                line += self._to_ascii[self.board[row][col]]
            yield line

    def ascii(self, black="#", white="o", empty=" "):
        # TODO: could be vastly improved by exploiting board internal format

        mapping = {
            EMPTY : " " + empty,
            BLACK : " " + black,
            WHITE : " " + white,
            }

        def format_pt(row, col):
            return mapping.get(self.get(row, col), " ?")

        def grid(point_formatter, size):
            column_header_string = " ".join("%02d" % i for i in xrange(size))
            result = []
            if size > 9:
                rowstart = "%2d "
                padding = " "
            else:
                rowstart = "%d "
                padding = ""
            for row in range(size-1, -1, -1):
                result.append(rowstart % (row) +
                              " ".join(point_formatter(row, col)
                              for col in range(size)))
            result.append(padding + "  " + column_header_string)
            return result

        return "\n".join(grid(format_pt, self.size))

    def stonecount(self):
        chars = ''.join(self.board)
        return (chars.count(BLACK),
                chars.count(WHITE))

    @classmethod
    def paintboard(cls, size, width=1, points=None):
        if points is None:
            points = cls.perimeters(size, width)
        board = cls(size)
        for i, perimeter in enumerate(points):
            assert len(perimeter) == len(set(perimeter))
            color = [BLACK, WHITE][i % 2]
            for point in perimeter:
                board.set(color, *point)
        print board.ascii()

    @classmethod
    def square(cls, size, corner=(0,0)):
        return cls.perimeters(size=size, width=size, maxperimeters=1, corner=corner)

    @classmethod
    def perimeters(cls, size, width=1, maxperimeters=0, corner=(0,0)):
        if width <= 0:
            return []

        perimeterslist = []

        for _ in xrange(maxperimeters or size):  # actually, math.ceil(size / (2.0 * width))
            if size <= 0:
                break

            points = []
            for w in xrange(width):
                side = size - 2 * w
                length = side - 1
                xstart, ystart = corner[0] + w, corner[1] + w

                if side <= 0:
                    break

                elif side == 1: # 1x1 center
                    points.append((xstart, ystart))
                    break

                for i in xrange(length):
                    points.append((xstart + i,      ystart))
                    points.append((xstart + i + 1,  ystart + length))
                    points.append((xstart + length, ystart + i))
                    points.append((xstart,          ystart + i + 1))

            perimeterslist.append(points)

            size = size - 2 * width
            corner = (corner[0] + width,
                      corner[1] + width)

        return perimeterslist
