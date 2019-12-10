#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# based on the sunfish uci code from Thomas Ahle & Contributors  - https://github.com/thomasahle/sunfish
# 

from __future__ import print_function
from __future__ import division
import importlib
import re
import sys
import time
import logging

import chess.pgn
import chess

from random import shuffle

logging.basicConfig(filename='uci.log', level=logging.DEBUG)


# Disable buffering
class Unbuffered(object):
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        #sys.stderr.write(data)
        #sys.stderr.flush()
        logging.debug(f'<<< {data} ')
    def __getattr__(self, attr):
        return getattr(self.stream, attr)

def main():
    chessboard = chess.Board()

    out = Unbuffered(sys.stdout)
    # out = sys.stdout
    def output(line):
        print(line, file=out)
        # print('\n', file=out)
        sys.stdout.flush()
        # logging.debug(line)

    stack = []
    while True:
        if stack:
            smove = stack.pop()
        else: smove = input()

        logging.debug(f'>>> {smove} ')

        if smove == 'quit':
            break

        elif smove == 'uci':
            output('id name CERTABO physical board')
            output('id author Harald Klein (based on work from Thomas Ahle & Contributors)')
            output('uciok')

        elif smove == 'isready':
            output('readyok')

        elif smove == 'ucinewgame':
            logging.debug("new game")
            # stack.append('position fen ...')

        elif smove.startswith('position fen'):
            _, _, fen = smove.split(' ', 2)
            logging.debug("fen: ", fen)

        elif smove.startswith('position startpos'):
            parameters = smove.split(' ')
            logging.debug(f'startpos received {parameters}')

            chessboard.reset()
            if parameters[2] == 'moves':
                for move in parameters[3:]:
                    logging.debug(f'move: {move}')
                    chessboard.push_uci(move)
            board_state = chessboard.fen()
            logging.debug(f'board state: {board_state}')


        elif smove.startswith('go'):
            logging.debug("go...")
            # output('resign')
            possible_moves = list(chessboard.legal_moves)
            logging.debug(f'legal moves: {possible_moves}')
            logging.debug(f'legal move: {possible_moves[0]}')
            #output('currmove e7e5')
            shuffle(possible_moves)
            output(f'bestmove {possible_moves[0]}')

        else:
            logging.debug(f'unandled: {smove}')
            pass

if __name__ == '__main__':
    main()

