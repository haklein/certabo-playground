#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 by Harald Klein <hari@vt100.at> - All rights reserved
# 

import sys
import time
import logging
import logging.handlers
import traceback
import os
import argparse
import threading

import chess.pgn
import chess

import berserk
import certabo
from certabo.certabo import CERTABO_DATA_PATH as CERTABO_DATA_PATH

parser = argparse.ArgumentParser()
parser.add_argument("--port")
parser.add_argument("--calibrate", action="store_true")
parser.add_argument("--devmode", action="store_true")
parser.add_argument("--quiet", action="store_true")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

portname = 'auto'
if args.port is not None:
    portname = args.port

calibrate = False
if args.calibrate:
    calibrate = True

DEBUG=False
if args.debug:
    DEBUG = True

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(module)s %(message)s')

filehandler = logging.handlers.TimedRotatingFileHandler(
    os.path.join(CERTABO_DATA_PATH, "certabo-lichess.log"), backupCount=12
)
filehandler.setFormatter(formatter)
logger.addHandler(filehandler)

if not args.quiet:
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)

# log unhandled exceptions to the log file
def my_excepthook(excType, excValue, traceback, logger=logger):
    logger.error("Uncaught exception",
                 exc_info=(excType, excValue, traceback))
sys.excepthook = my_excepthook

logging.info("certabo-lichess.py startup")

def main():
    mycertabo = certabo.certabo.Certabo(port=portname, calibrate=calibrate)

    try:
        with open('./lichess.token') as f:
            token = f.read().strip()
    except FileNotFoundError:
        print(f'ERROR: cannot find token file')
        sys.exit(-1)
    except PermissionError:
        print(f'ERROR: permission denied on token file')
        sys.exit(-1)

    try:
        session = berserk.TokenSession(token)
    except:
        e = sys.exc_info()[0]
        print(f"cannot create session: {e}")
        logging.info(f'cannot create session {e}')
        sys.exit(-1)

    try:
        if args.devmode:
            client = berserk.Client(session, base_url="https://lichess.dev")
        else:
            client = berserk.Client(session)
    except:
        e = sys.exc_info()[0]
        logging.info(f'cannot create lichess client: {e}')
        print(f"cannot create lichess client: {e}")
        sys.exit(-1)

    tmp_chessboard = chess.Board()
    logging.info(f'final FEN: {tmp_chessboard.fen()}')

    board = chess.Board()
    game = chess.pgn.Game()
    node = game
    while True:
        while mycertabo.has_user_move() == []:
            time.sleep(0.1)
        try:
            node = node.add_variation(chess.Move.from_uci(mycertabo.has_user_move()[0]))
            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
            pgn_string = pgn_string = game.accept(exporter)
            client.broadcasts.push_pgn_update('M6aFOEQh', [pgn_string])
            board.push_uci(mycertabo.has_user_move()[0])
            mycertabo.set_board_from_fen(board.fen())

        except berserk.exceptions.ResponseError as e:
            print(f'ERROR: Invalid server response: {e}')
            logging.info('Invalid server response: {e}')
            if 'Too Many Requests for url' in str(e):
                time.sleep(10)
        time.sleep(5)
if __name__ == '__main__':
    main()

